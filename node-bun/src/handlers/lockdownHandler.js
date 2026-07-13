import { PermissionFlagsBits } from 'discord.js';
import {
  getLockdownChannels,
  getLockdownState,
  acquireLockdownEnable,
  acquireLockdownDisable,
  clearLockdownState,
  finalizeLockdownEnable,
  finalizeLockdownDisable,
  addLockdownRestoreAction,
  getLockdownRestoreDiagnostics,
  createCase,
} from '../database/db.js';
import { sendModLog } from '../utils/modLog.js';
import {
  applyPermissionState,
  getPermissionState,
} from '../utils/channelPermissions.js';
import { restoreChannelFromTimedAction } from '../utils/channelTimedUnlock.js';
import { success, error } from '../utils/helpers.js';

const LOCKDOWN_PERMISSION = 'SendMessages';

export function botHasManageChannels(guild) {
  const me = guild.members.me;
  return Boolean(me?.permissions.has(PermissionFlagsBits.ManageChannels));
}

export function isLockdownEligibleChannel(channel) {
  return Boolean(channel?.isTextBased?.() && channel.permissionOverwrites);
}

export async function buildLockdownStatus(guild) {
  const configured = await getLockdownChannels(guild.id);
  const state = await getLockdownState(guild.id);
  const restores = await getLockdownRestoreDiagnostics(guild.id);

  const channelLines = configured.map((id) => {
    const ch = guild.channels.cache.get(id);
    return ch ? `• ${ch} (\`${id}\`)` : `• ~~deleted~~ (\`${id}\`)`;
  });

  const applied = (state?.channels ?? []).filter((c) => c.result === 'applied');
  const failed = (state?.channels ?? []).filter((c) => c.result === 'failed');

  const lines = [
    `**Active:** ${state?.active ? 'Yes' : 'No'}`,
    state?.active ? `**Started:** <t:${Math.floor(state.started_at / 1000)}:R> by <@${state.started_by}>` : null,
    state?.active ? `**Reason:** ${state.reason}` : null,
    !state?.active && state?.last_disabled_at
      ? `**Last disabled:** <t:${Math.floor(state.last_disabled_at / 1000)}:R> by <@${state.last_disabled_by}>`
      : null,
    `**Configured channels:** ${configured.length}`,
    state?.channels ? `**Active snapshot:** ${state.channels.length} channel(s)` : null,
    state?.active ? `**Locked successfully:** ${applied.length}` : null,
    state?.active ? `**Lock failures:** ${failed.length}` : null,
    `**Pending restorations:** ${restores.pending.length}`,
    `**Failed restorations:** ${restores.failed.length}`,
    channelLines.length ? `\n**Channel list:**\n${channelLines.join('\n')}` : '\n**Channel list:** none configured',
  ].filter(Boolean);

  return lines.join('\n');
}

async function rollbackAppliedChannels(guild, appliedResults, roleId) {
  const rollbacks = [];
  for (const entry of appliedResults) {
    const channel = guild.channels.cache.get(entry.channel_id);
    if (!channel) continue;
    try {
      await applyPermissionState(channel, roleId, LOCKDOWN_PERMISSION, entry.previous_state);
      rollbacks.push({ channel_id: entry.channel_id, ok: true });
    } catch (err) {
      rollbacks.push({ channel_id: entry.channel_id, ok: false, error: err.message });
    }
  }
  return rollbacks;
}

async function applyLockToChannel(channel, roleId) {
  const overwrite = channel.permissionOverwrites.cache.get(roleId);
  const previousState = getPermissionState(overwrite, LOCKDOWN_PERMISSION);
  await applyPermissionState(channel, roleId, LOCKDOWN_PERMISSION, 'deny');
  return { channel_id: channel.id, previous_state: previousState, applied_state: 'deny', result: 'applied' };
}

export async function enableLockdown(guild, moderator, reason) {
  if (!botHasManageChannels(guild)) {
    return { reply: error('I need the **Manage Channels** permission to run lockdown.') };
  }

  const existing = await getLockdownState(guild.id);
  if (existing?.active) {
    return { reply: error('Lockdown is already active. Use `?channel lockdown disable` to end it.') };
  }

  const configuredIds = await getLockdownChannels(guild.id);
  if (!configuredIds.length) {
    return { reply: error('No lockdown channels configured. Use `?channel lockdown channel add #channel` first.') };
  }

  const roleId = guild.roles.everyone.id;
  const acquire = await acquireLockdownEnable(guild.id, {
    moderatorId: moderator.id,
    reason: reason?.trim() || 'No reason provided',
    roleId,
    permission: LOCKDOWN_PERMISSION,
  });

  if (!acquire.ok) {
    return { reply: error('Lockdown is already active.') };
  }

  const results = [];
  const applied = [];

  for (const channelId of configuredIds) {
    const channel = guild.channels.cache.get(channelId);
    if (!channel) {
      results.push({ channel_id: channelId, previous_state: null, applied_state: 'deny', result: 'failed', error: 'channel_missing' });
      continue;
    }
    if (!isLockdownEligibleChannel(channel)) {
      results.push({ channel_id: channelId, previous_state: null, applied_state: 'deny', result: 'failed', error: 'unsupported_channel' });
      continue;
    }
    try {
      const entry = await applyLockToChannel(channel, roleId);
      results.push(entry);
      applied.push(entry);
    } catch (err) {
      results.push({
        channel_id: channelId,
        previous_state: null,
        applied_state: 'deny',
        result: 'failed',
        error: err.message,
      });
    }
  }

  const successCount = results.filter((r) => r.result === 'applied').length;
  const failCount = results.length - successCount;

  if (successCount === 0) {
    await clearLockdownState(guild.id);
    return {
      reply: error(`Lockdown failed — none of the ${results.length} configured channel(s) could be locked.`),
    };
  }

  let caseNumber;
  try {
    await finalizeLockdownEnable(guild.id, results);
    const caseAction = failCount > 0 ? 'lockdown_enable_partial' : 'lockdown_enable';
    caseNumber = await createCase(
      guild.id,
      guild.id,
      moderator.id,
      caseAction,
      reason?.trim() || 'Server lockdown enabled',
      {
        source: 'lockdown',
        configured: results.length,
        applied: successCount,
        failed: failCount,
      },
    );
  } catch (err) {
    console.error('[lockdown] Persistence failed after permission changes:', err.message);
    const rollbacks = await rollbackAppliedChannels(guild, applied, roleId);
    await clearLockdownState(guild.id);
    const rollbackFailed = rollbacks.some((r) => !r.ok);
    return {
      reply: error(
        rollbackFailed
          ? 'Lockdown persistence failed and rollback was incomplete. Manual permission review is required.'
          : 'Lockdown persistence failed. Permission changes were rolled back.',
      ),
    };
  }

  const summary = failCount > 0
    ? `Lockdown enabled in ${successCount} of ${results.length} configured channels. ${failCount} channel(s) failed and require review.`
    : `Lockdown enabled on ${successCount} configured channel(s).`;

  await sendModLog(guild, {
    action: failCount > 0 ? 'lockdown_enable_partial' : 'lockdown_enable',
    target: { id: guild.id, toString: () => guild.name },
    moderator,
    reason: summary,
    caseNumber,
  }).catch((err) => console.error('[lockdown] Mod-log notification failed:', err.message));

  return { reply: success(`${summary} — Case #${caseNumber}.`) };
}

export async function disableLockdown(guild, moderator, reason) {
  if (!botHasManageChannels(guild)) {
    return { reply: error('I need the **Manage Channels** permission to run lockdown.') };
  }

  const acquired = await acquireLockdownDisable(guild.id);
  if (!acquired.ok) {
    return { reply: error('No active lockdown to disable.') };
  }

  const state = acquired.state;

  const roleId = state.role_id ?? guild.roles.everyone.id;
  const permission = state.permission ?? LOCKDOWN_PERMISSION;
  const appliedEntries = (state.channels ?? []).filter((c) => c.result === 'applied');

  const summary = {
    restored: 0,
    manual_change: 0,
    missing: 0,
    failed: 0,
    scheduled_retry: 0,
  };
  const channelResults = [];

  for (const entry of appliedEntries) {
    const channel = guild.channels.cache.get(entry.channel_id);
    if (!channel) {
      summary.missing++;
      channelResults.push({ ...entry, disable_result: 'missing' });
      continue;
    }

    const timedAction = {
      permission,
      applied_state: entry.applied_state ?? 'deny',
      previous_state: entry.previous_state ?? 'unset',
    };

    let restoreResult;
    try {
      restoreResult = await restoreChannelFromTimedAction(channel, roleId, timedAction);
    } catch (err) {
      summary.failed++;
      channelResults.push({ ...entry, disable_result: 'failed', error: err.message });
      await addLockdownRestoreAction({
        guildId: guild.id,
        channelId: entry.channel_id,
        roleId,
        permission,
        previousState: entry.previous_state ?? 'unset',
        appliedState: entry.applied_state ?? 'deny',
      });
      summary.scheduled_retry++;
      continue;
    }

    if (restoreResult.type === 'conflict') {
      summary.manual_change++;
      channelResults.push({
        ...entry,
        disable_result: 'manual_change',
        current_state: restoreResult.currentState,
      });
      continue;
    }

    summary.restored++;
    channelResults.push({ ...entry, disable_result: 'restored' });
  }

  let caseNumber;
  try {
    await finalizeLockdownDisable(guild.id, {
      moderatorId: moderator.id,
      reason: reason?.trim() || 'Server lockdown disabled',
      roleId,
      summary,
      channelResults,
    });
    const caseAction = summary.failed > 0 || summary.scheduled_retry > 0
      ? 'lockdown_restore_failed'
      : 'lockdown_disable';
    caseNumber = await createCase(
      guild.id,
      guild.id,
      moderator.id,
      caseAction,
      reason?.trim() || 'Server lockdown disabled',
      {
        source: 'lockdown',
        ...summary,
      },
    );
  } catch (err) {
    console.error('[lockdown] Disable persistence failed:', err.message);
    return { reply: error('Lockdown was processed but the final state could not be saved.') };
  }

  const parts = [
    `restored ${summary.restored}`,
    summary.manual_change ? `${summary.manual_change} manual change(s) preserved` : null,
    summary.missing ? `${summary.missing} missing` : null,
    summary.scheduled_retry ? `${summary.scheduled_retry} pending retry` : null,
    summary.failed ? `${summary.failed} failed` : null,
  ].filter(Boolean);

  const summaryText = `Lockdown disabled — ${parts.join(', ')}.`;

  await sendModLog(guild, {
    action: summary.failed > 0 || summary.scheduled_retry > 0 ? 'lockdown_restore_failed' : 'lockdown_disable',
    target: { id: guild.id, toString: () => guild.name },
    moderator,
    reason: summaryText,
    caseNumber,
  }).catch((err) => console.error('[lockdown] Mod-log notification failed:', err.message));

  return { reply: success(`${summaryText} — Case #${caseNumber}.`) };
}
