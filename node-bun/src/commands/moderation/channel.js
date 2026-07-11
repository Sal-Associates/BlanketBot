import {
  createCase,
  upsertChannelTimedAction,
  cancelChannelTimedActions,
  getPendingChannelTimedActions,
  completeTimedAction,
  addLockdownChannel,
  removeLockdownChannel,
  getLockdownChannels,
} from '../../database/db.js';
import { resolveChannel, success, error, basicEmbed } from '../../utils/helpers.js';
import { checkMod, checkAdmin } from '../../utils/checks.js';
import { sendModLog } from '../../utils/modLog.js';
import { parseDuration, formatDuration } from '../../utils/time.js';
import {
  applyPermissionState,
  getPermissionState,
} from '../../utils/channelPermissions.js';
import { restoreChannelFromTimedAction } from '../../utils/channelTimedUnlock.js';
import {
  enableLockdown,
  disableLockdown,
  buildLockdownStatus,
  botHasManageChannels,
  isLockdownEligibleChannel,
} from '../../handlers/lockdownHandler.js';

const CHANNEL_LOCK_PERMISSION = 'SendMessages';
const CHANNEL_UNLOCK_ACTION = 'channel_unlock';

async function handleLockdownSubcommand(message, rest) {
  const denied = await checkAdmin(message);
  if (denied) return message.reply(denied);

  if (!botHasManageChannels(message.guild)) {
    return message.reply(error('I need the **Manage Channels** permission for lockdown commands.'));
  }

  const parts = rest.trim().split(/\s+/);
  const action = parts[0]?.toLowerCase() ?? '';

  if (action === 'channel') {
    const channelAction = parts[1]?.toLowerCase();
    const channelArg = parts.slice(2).join(' ').trim();

    if (channelAction === 'add') {
      const channel = resolveChannel(message.guild, channelArg);
      if (!channel) return message.reply(error('Usage: `?channel lockdown channel add #channel`'));
      if (!isLockdownEligibleChannel(channel)) {
        return message.reply(error('That channel type does not support SendMessages permission overwrites.'));
      }
      try {
        await addLockdownChannel(message.guild.id, channel.id);
      } catch (err) {
        if (err.message === 'duplicate_lockdown_channel') {
          return message.reply(error(`${channel} is already in the lockdown channel list.`));
        }
        throw err;
      }
      return message.reply(success(`Added ${channel} to lockdown channels.`));
    }

    if (channelAction === 'remove') {
      const channel = resolveChannel(message.guild, channelArg);
      if (!channel) return message.reply(error('Usage: `?channel lockdown channel remove #channel`'));
      const result = await removeLockdownChannel(message.guild.id, channel.id);
      if (!result.removed) {
        return message.reply(error(`${channel} is not in the lockdown channel list.`));
      }
      return message.reply(success(`Removed ${channel} from lockdown channels.`));
    }

    if (channelAction === 'list') {
      const configured = await getLockdownChannels(message.guild.id);
      if (!configured.length) {
        return message.reply(error('No lockdown channels configured.'));
      }
      const lines = configured.map((id) => {
        const ch = message.guild.channels.cache.get(id);
        return ch ? `• ${ch} (\`${id}\`)` : `• ~~deleted~~ (\`${id}\`)`;
      });
      return message.reply({ embeds: [basicEmbed('Lockdown Channels', lines.join('\n'))] });
    }

    return message.reply(error('Usage: `?channel lockdown channel add|remove|list`'));
  }

  if (action === 'enable' || action === '') {
    const reason = action === 'enable' ? parts.slice(1).join(' ') : rest.trim();
    const result = await enableLockdown(message.guild, message.author, reason);
    return message.reply(result.reply);
  }

  if (action === 'disable' || action === 'end') {
    const reason = parts.slice(1).join(' ');
    const result = await disableLockdown(message.guild, message.author, reason);
    return message.reply(result.reply);
  }

  if (action === 'status') {
    const status = await buildLockdownStatus(message.guild);
    return message.reply({ embeds: [basicEmbed('Lockdown Status', status)] });
  }

  return message.reply(error(
    'Usage: `?channel lockdown channel add|remove|list`, `enable [reason]`, `disable [reason]`, or `status`',
  ));
}

export default {
  name: 'channel',
  description: 'Channel controls: lock, unlock, slowmode, lockdown',
  category: 'Moderation',
  usage: '?channel lock|unlock|slowmode|lockdown [args]',
  async execute(message, args, subcommand, subargs) {
    const action = subcommand?.toLowerCase();
    const rest = subargs || args.trim();

    if (action === 'lockdown') {
      return handleLockdownSubcommand(message, rest);
    }

    const denied = await checkMod(message);
    if (denied) return message.reply(denied);

    switch (action) {
      case 'lock': {
        const parts = rest.split(/\s+/);
        let channel = message.channel;
        let timeArg = parts[0];
        if (parts[0]?.match(/^<#\d+>$/)) {
          channel = resolveChannel(message.guild, parts[0]) ?? channel;
          timeArg = parts[1];
        }

        const duration = parseDuration(timeArg);
        const everyoneRole = message.guild.roles.everyone;
        const previousState = getPermissionState(
          channel.permissionOverwrites.cache.get(everyoneRole.id),
          CHANNEL_LOCK_PERMISSION,
        );

        try {
          await channel.permissionOverwrites.edit(everyoneRole, { [CHANNEL_LOCK_PERMISSION]: false });
        } catch {
          return message.reply(error('Could not lock that channel.'));
        }

        if (duration) {
          try {
            await upsertChannelTimedAction({
              guildId: message.guild.id,
              channelId: channel.id,
              roleId: everyoneRole.id,
              action: CHANNEL_UNLOCK_ACTION,
              permission: CHANNEL_LOCK_PERMISSION,
              previousState,
              appliedState: 'deny',
              endsAt: Date.now() + duration,
              moderatorId: message.author.id,
            });
          } catch (err) {
            console.error('[channel] Timed unlock persistence failed:', err.message);
            try {
              await applyPermissionState(channel, everyoneRole.id, CHANNEL_LOCK_PERMISSION, previousState);
            } catch (rollbackErr) {
              console.error('[channel] Lock rollback failed:', rollbackErr.message);
            }
            return message.reply(error('Channel was locked briefly but auto-unlock could not be scheduled. The lock was rolled back.'));
          }
        }

        try {
          const caseNum = await createCase(message.guild.id, channel.id, message.author.id, 'lock', 'Channel locked', { source: 'moderation' });
          const notified = await sendModLog(message.guild, {
            action: 'lock',
            target: { id: channel.id, toString: () => channel.toString() },
            moderator: message.author,
            reason: duration ? `Channel locked (${formatDuration(duration)})` : 'Channel locked',
            caseNumber: caseNum,
          });
          if (!notified) {
            console.error(`[channel] Mod-log channel notification failed for lock case #${caseNum}`);
          }
          return message.reply(success(
            `Locked ${channel} — Case #${caseNum}${duration ? ` (auto-unlock in ${timeArg})` : ''}.`,
          ));
        } catch (err) {
          console.error('[channel] Case logging failed after lock:', err.message);
          return message.reply(error('Channel was locked but the case could not be saved.'));
        }
      }
      case 'unlock': {
        const channel = resolveChannel(message.guild, rest.trim()) ?? message.channel;
        const everyoneRole = message.guild.roles.everyone;
        const overwrite = channel.permissionOverwrites.cache.get(everyoneRole.id);
        const currentState = getPermissionState(overwrite, CHANNEL_LOCK_PERMISSION);
        const pending = await getPendingChannelTimedActions(
          message.guild.id,
          channel.id,
          CHANNEL_UNLOCK_ACTION,
          CHANNEL_LOCK_PERMISSION,
        );

        let unlockReason;
        let restoredState = null;

        if (pending.length > 0) {
          const timedAction = pending[0];
          let restoreResult;
          try {
            restoreResult = await restoreChannelFromTimedAction(channel, everyoneRole.id, timedAction);
          } catch {
            return message.reply(error('Could not restore channel permissions.'));
          }

          if (restoreResult.type === 'conflict') {
            const cancelled = await cancelChannelTimedActions(
              message.guild.id,
              channel.id,
              CHANNEL_UNLOCK_ACTION,
              CHANNEL_LOCK_PERMISSION,
            );
            return message.reply(success(
              `Cancelled pending timed unlock (${cancelled.removed}). `
              + `${CHANNEL_LOCK_PERMISSION} was already changed manually (now ${restoreResult.currentState}); no overwrite was modified.`,
            ));
          }

          restoredState = restoreResult.previousState;
          const removed = await completeTimedAction(timedAction.id);
          if (!removed) {
            console.error(`[channel] Restored ${channel.id} but failed to remove pending timed action ${timedAction.id}`);
          }
          unlockReason = `Manual unlock restored ${CHANNEL_LOCK_PERMISSION} to ${restoredState} (cancelled pending timed unlock)`;
        } else {
          if (currentState !== 'deny') {
            return message.reply(error('That channel is not locked.'));
          }
          try {
            await channel.permissionOverwrites.edit(everyoneRole, { [CHANNEL_LOCK_PERMISSION]: null });
          } catch {
            return message.reply(error('Could not unlock that channel.'));
          }
          unlockReason = 'Channel unlocked (no pending timed lock)';
          restoredState = 'unset';
        }

        const caseNum = await createCase(message.guild.id, channel.id, message.author.id, 'unlock', unlockReason, { source: 'moderation' });
        await sendModLog(message.guild, {
          action: 'unlock',
          target: { id: channel.id, toString: () => channel.toString() },
          moderator: message.author,
          reason: unlockReason,
          caseNumber: caseNum,
        });

        return message.reply(success(
          `Unlocked ${channel} — Case #${caseNum}. Restored ${CHANNEL_LOCK_PERMISSION} to **${restoredState ?? 'inherit'}**.`,
        ));
      }
      case 'slowmode': {
        const seconds = parseInt(rest.trim(), 10);
        if (isNaN(seconds) || seconds < 0 || seconds > 21600) {
          return message.reply(error('Provide seconds between 0 and 21600.'));
        }
        await message.channel.setRateLimitPerUser(seconds);
        return message.reply(success(seconds === 0 ? 'Slowmode disabled.' : `Slowmode set to **${seconds}s**.`));
      }
      default:
        return message.reply(error('Usage: `?channel lock|unlock|slowmode|lockdown`'));
    }
  },
};
