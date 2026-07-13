import { getModerationDenied } from '../../utils/permissions.js';
import { resolveMember, resolveUserTarget, success, error } from '../../utils/helpers.js';
import { checkMod } from '../../utils/checks.js';
import { sendModLog, getOrCreateMuteRole } from '../../utils/modLog.js';
import { createCase, createTemporaryPunishmentRecords } from '../../database/db.js';
import {
  rollbackTemporaryBan,
  rollbackTemporaryMute,
  persistenceRollbackMessage,
  persistenceLoggingFailureMessage,
} from '../../utils/moderationCompensation.js';
import { parseDuration, formatDuration } from '../../utils/time.js';

const ACTIONS = ['ban', 'unban', 'kick', 'mute', 'unmute', 'softban', 'deafen', 'undeafen'];

async function persistPermanentCase(message, { target, action, reason, successText }) {
  try {
    const caseNum = await createCase(message.guild.id, target.id, message.author.id, action, reason, {
      source: 'moderation',
    });
    const notified = await sendModLog(message.guild, {
      action,
      target,
      moderator: message.author,
      reason,
      caseNumber: caseNum,
    });
    if (!notified) {
      console.error(`[mod] Mod-log channel notification failed for ${action} case #${caseNum}`);
    }
    return message.reply(success(`${successText} — Case #${caseNum}.`));
  } catch (err) {
    console.error(`[mod] Case persistence failed for ${action}:`, err.message);
    return message.reply(error(persistenceLoggingFailureMessage(action)));
  }
}

export default {
  name: 'mod',
  description: 'Moderation actions: ban, kick, mute, etc.',
  category: 'Moderation',
  usage: '?mod <ban|unban|kick|mute|unmute|softban|deafen|undeafen> [args]',
  async execute(message, args, subcommand, subargs) {
    const denied = await checkMod(message);
    if (denied) return message.reply(denied);

    const action = subcommand?.toLowerCase();
    if (!action || !ACTIONS.includes(action)) {
      return message.reply(error(`Usage: \`?mod ${ACTIONS.join('|')}\` followed by user and optional args.`));
    }

    const rest = subargs || args.trim();
    const parts = rest.split(/\s+/);

    switch (action) {
      case 'ban': {
        const resolved = resolveUserTarget(message, parts[0]);
        if (!resolved) return message.reply(error('Usage: `?mod ban <user> [time] [reason]`'));

        const hierarchyDenied = getModerationDenied(
          message.guild,
          message.member,
          resolved.member ?? { id: resolved.userId },
          { requireMember: false },
        );
        if (hierarchyDenied) return message.reply(hierarchyDenied);

        let duration = null;
        let reasonStart = 1;
        const maybeDuration = parseDuration(parts[1]);
        if (maybeDuration) { duration = maybeDuration; reasonStart = 2; }
        const reason = parts.slice(reasonStart).join(' ') || 'No reason provided';
        const displayName = resolved.member?.user?.tag ?? resolved.userId;
        const target = resolved.member ?? { id: resolved.userId, toString: () => `<@${resolved.userId}>` };

        try {
          await message.guild.members.ban(resolved.userId, {
            reason: `${message.author.tag}: ${reason}`,
            deleteMessageSeconds: 86400,
          });
        } catch {
          return message.reply(error('Could not ban that user.'));
        }

        if (duration) {
          try {
            const { caseNumber } = await createTemporaryPunishmentRecords({
              guildId: message.guild.id,
              userId: resolved.userId,
              moderatorId: message.author.id,
              caseAction: 'ban',
              caseReason: reason,
              timedAction: 'unban',
              endsAt: Date.now() + duration,
            });
            const notified = await sendModLog(message.guild, {
              action: 'ban',
              target,
              moderator: message.author,
              reason,
              caseNumber,
            });
            if (!notified) {
              console.error(`[mod] Mod-log channel notification failed for ban case #${caseNumber}`);
            }
            return message.reply(success(
              `Banned **${displayName}** — Case #${caseNumber}. Reason: ${reason} (expires in ${formatDuration(duration)})`,
            ));
          } catch (err) {
            console.error('[mod] Temporary ban persistence failed:', err.message);
            const rollback = await rollbackTemporaryBan(message.guild, resolved.userId);
            return message.reply(error(persistenceRollbackMessage('ban', rollback)));
          }
        }

        try {
          const caseNum = await createCase(message.guild.id, resolved.userId, message.author.id, 'ban', reason, {
            source: 'moderation',
          });
          const notified = await sendModLog(message.guild, { action: 'ban', target, moderator: message.author, reason, caseNumber: caseNum });
          if (!notified) {
            console.error(`[mod] Mod-log channel notification failed for ban case #${caseNum}`);
          }
          return message.reply(success(`Banned **${displayName}** — Case #${caseNum}. Reason: ${reason}`));
        } catch (err) {
          console.error('[mod] Ban case persistence failed:', err.message);
          return message.reply(error(persistenceLoggingFailureMessage('banned')));
        }
      }
      case 'unban': {
        const userId = parts[0]?.replace(/[<@!>]/g, '');
        if (!userId) return message.reply(error('Usage: `?mod unban <userId> [reason]`'));
        if (message.member.id === userId) return message.reply(error('You cannot moderate yourself.'));
        const reason = parts.slice(1).join(' ') || 'No reason provided';
        try {
          await message.guild.members.unban(userId, `${message.author.tag}: ${reason}`);
        } catch {
          return message.reply(error('Could not unban that user.'));
        }
        return persistPermanentCase(message, {
          target: { id: userId, toString: () => `<@${userId}>` },
          action: 'unban',
          reason,
          successText: `Unbanned \`${userId}\``,
        });
      }
      case 'softban': {
        const target = resolveMember(message, parts[0]);
        if (!target) return message.reply(error('That user is not currently a member of this server.'));
        const hierarchyDenied = getModerationDenied(message.guild, message.member, target);
        if (hierarchyDenied) return message.reply(hierarchyDenied);
        const reason = parts.slice(1).join(' ') || 'No reason provided';
        try {
          await target.ban({ reason: `Softban: ${reason}`, deleteMessageSeconds: 604800 });
          await message.guild.members.unban(target.id, 'Softban complete');
        } catch {
          return message.reply(error('Could not softban that user.'));
        }
        return persistPermanentCase(message, {
          target,
          action: 'softban',
          reason,
          successText: `Softbanned **${target.user.tag}**`,
        });
      }
      case 'kick': {
        const target = resolveMember(message, parts[0]);
        if (!target) return message.reply(error('That user is not currently a member of this server.'));
        const hierarchyDenied = getModerationDenied(message.guild, message.member, target);
        if (hierarchyDenied) return message.reply(hierarchyDenied);
        const reason = parts.slice(1).join(' ') || 'No reason provided';
        try {
          await target.kick(`${message.author.tag}: ${reason}`);
        } catch {
          return message.reply(error('Could not kick that user.'));
        }
        return persistPermanentCase(message, {
          target,
          action: 'kick',
          reason,
          successText: `Kicked **${target.user.tag}**`,
        });
      }
      case 'mute': {
        const target = resolveMember(message, parts[0]);
        if (!target) return message.reply(error('That user is not currently a member of this server.'));
        const hierarchyDenied = getModerationDenied(message.guild, message.member, target);
        if (hierarchyDenied) return message.reply(hierarchyDenied);
        let duration = null;
        let reasonStart = 1;
        const maybeDuration = parseDuration(parts[1]);
        if (maybeDuration) { duration = maybeDuration; reasonStart = 2; }
        const reason = parts.slice(reasonStart).join(' ') || 'No reason provided';
        const muteRole = await getOrCreateMuteRole(message.guild);

        try {
          await target.roles.add(muteRole, reason);
        } catch {
          return message.reply(error('Could not mute that user.'));
        }

        if (duration) {
          try {
            const { caseNumber } = await createTemporaryPunishmentRecords({
              guildId: message.guild.id,
              userId: target.id,
              moderatorId: message.author.id,
              caseAction: 'mute',
              caseReason: reason,
              timedAction: 'unmute',
              endsAt: Date.now() + duration,
            });
            const notified = await sendModLog(message.guild, {
              action: 'mute',
              target,
              moderator: message.author,
              reason,
              caseNumber,
            });
            if (!notified) {
              console.error(`[mod] Mod-log channel notification failed for mute case #${caseNumber}`);
            }
            return message.reply(success(
              `Muted **${target.user.tag}** — Case #${caseNumber}. (expires in ${formatDuration(duration)})`,
            ));
          } catch (err) {
            console.error('[mod] Temporary mute persistence failed:', err.message);
            const rollback = await rollbackTemporaryMute(target, muteRole);
            return message.reply(error(persistenceRollbackMessage('mute', rollback)));
          }
        }

        return persistPermanentCase(message, {
          target,
          action: 'mute',
          reason,
          successText: `Muted **${target.user.tag}**`,
        });
      }
      case 'unmute': {
        const target = resolveMember(message, parts[0]);
        if (!target) return message.reply(error('That user is not currently a member of this server.'));
        const hierarchyDenied = getModerationDenied(message.guild, message.member, target);
        if (hierarchyDenied) return message.reply(hierarchyDenied);
        const reason = parts.slice(1).join(' ') || 'No reason provided';
        const muteRole = await getOrCreateMuteRole(message.guild);
        if (!target.roles.cache.has(muteRole.id)) return message.reply(error('That user is not muted.'));
        try {
          await target.roles.remove(muteRole, reason);
        } catch {
          return message.reply(error('Could not unmute that user.'));
        }
        return persistPermanentCase(message, {
          target,
          action: 'unmute',
          reason,
          successText: `Unmuted **${target.user.tag}**`,
        });
      }
      case 'deafen': {
        const target = resolveMember(message, parts[0]);
        if (!target) return message.reply(error('That user is not currently a member of this server.'));
        const hierarchyDenied = getModerationDenied(message.guild, message.member, target);
        if (hierarchyDenied) return message.reply(hierarchyDenied);
        if (!target.voice.channel) return message.reply(error('User is not in a voice channel.'));
        try {
          await target.voice.setDeaf(true, parts.slice(1).join(' ') || 'Deafened');
        } catch {
          return message.reply(error('Could not deafen that user.'));
        }
        return message.reply(success(`Deafened **${target.user.tag}**.`));
      }
      case 'undeafen': {
        const target = resolveMember(message, parts[0]);
        if (!target) return message.reply(error('That user is not currently a member of this server.'));
        const hierarchyDenied = getModerationDenied(message.guild, message.member, target);
        if (hierarchyDenied) return message.reply(hierarchyDenied);
        try {
          await target.voice.setDeaf(false);
        } catch {
          return message.reply(error('Could not undeafen that user.'));
        }
        return message.reply(success(`Undeafened **${target.user.tag}**.`));
      }
      default:
        return message.reply(error('Unknown mod action.'));
    }
  },
};
