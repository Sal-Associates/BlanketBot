import { PermissionFlagsBits } from 'discord.js';
import {
  completeTimedAction,
  recordTimedActionRetry,
  markTimedActionFailed,
} from '../database/db.js';
import { getOrCreateMuteRole, sendModLog } from '../utils/modLog.js';
import { isConfiguredGuild } from '../utils/guild.js';
import { checkBotCanActOn } from '../utils/permissions.js';
import {
  channelPermissionMatches,
  getPermissionState,
} from '../utils/channelPermissions.js';
import { restoreChannelFromTimedAction } from '../utils/channelTimedUnlock.js';
import {
  MAX_CHANNEL_UNLOCK_ATTEMPTS,
  getRetryDelayMs,
  sanitizeTimedActionError,
} from '../utils/timedActionRetry.js';

export async function executeTimedAction(client, action) {
  if (!isConfiguredGuild(action.guild_id)) {
    return { outcome: 'terminal', reason: 'guild_not_configured' };
  }

  if (action.action === 'unban') {
    return executeUnban(client, action);
  }
  if (action.action === 'unmute') {
    return executeUnmute(client, action);
  }
  if (action.action === 'channel_unlock') {
    return executeChannelUnlock(client, action);
  }
  if (action.action === 'lockdown_channel_restore') {
    return executeLockdownChannelRestore(client, action);
  }

  console.warn(`[scheduler] Unknown timed action type: ${action.action}`);
  return { outcome: 'terminal', reason: 'unknown_action' };
}

async function executeUnban(client, action) {
  const guild = await client.guilds.fetch(action.guild_id).catch(() => null);
  if (!guild) {
    console.warn(`[scheduler] Timed unban skipped — guild missing (${action.guild_id})`);
    return { outcome: 'terminal', reason: 'guild_missing' };
  }

  try {
    await guild.members.unban(action.user_id, 'Timed ban expired');
    return { outcome: 'completed' };
  } catch (err) {
    console.error(`[scheduler] Timed unban failed for user ${action.user_id}:`, err.message);
    return { outcome: 'retryable', reason: 'api_error', error: err };
  }
}

async function executeUnmute(client, action) {
  const guild = await client.guilds.fetch(action.guild_id).catch(() => null);
  if (!guild) {
    console.warn(`[scheduler] Timed unmute skipped — guild missing (${action.guild_id})`);
    return { outcome: 'terminal', reason: 'guild_missing' };
  }

  const member = await guild.members.fetch(action.user_id).catch(() => null);
  if (!member) {
    console.warn(`[scheduler] Timed unmute skipped — member missing (${action.user_id})`);
    return { outcome: 'terminal', reason: 'member_missing' };
  }

  const botCheck = checkBotCanActOn(guild, member);
  if (!botCheck.allowed) {
    console.warn(`[scheduler] Timed unmute skipped — bot cannot act on ${action.user_id}`);
    return { outcome: 'retryable', reason: 'bot_cannot_act' };
  }

  try {
    const muteRole = await getOrCreateMuteRole(guild);
    await member.roles.remove(muteRole);
    return { outcome: 'completed' };
  } catch (err) {
    console.error(`[scheduler] Timed unmute failed for user ${action.user_id}:`, err.message);
    return { outcome: 'retryable', reason: 'api_error', error: err };
  }
}

function validateChannelUnlockAction(action) {
  if (!action.channel_id || !action.permission) return false;
  const previousState = action.previous_state ?? 'unset';
  if (!['allow', 'deny', 'unset'].includes(previousState)) return false;
  return true;
}

async function executeLockdownChannelRestore(client, action) {
  return executeChannelUnlock(client, {
    ...action,
    action: 'channel_unlock',
    applied_state: action.applied_state ?? 'deny',
  });
}

async function executeChannelUnlock(client, action) {
  if (!validateChannelUnlockAction(action)) {
    console.error(`[scheduler] Malformed channel_unlock action ${action.id}`);
    return { outcome: 'terminal', reason: 'malformed' };
  }

  const permission = action.permission || 'SendMessages';
  const guild = await client.guilds.fetch(action.guild_id).catch((err) => ({
    fetchError: err,
  }));

  if (!guild || guild.fetchError) {
    console.warn(`[scheduler] Channel unlock retry — guild fetch failed (${action.guild_id})`);
    return {
      outcome: 'retryable',
      reason: 'fetch_failed',
      error: guild?.fetchError ?? new Error('guild_fetch_failed'),
    };
  }

  const channel = await guild.channels.fetch(action.channel_id).catch((err) => ({ fetchError: err }));
  if (!channel?.permissionOverwrites) {
    if (channel?.fetchError) {
      console.warn(`[scheduler] Channel unlock retry — channel fetch failed (${action.channel_id})`);
      return { outcome: 'retryable', reason: 'fetch_failed', error: channel.fetchError };
    }
    console.warn(`[scheduler] Channel unlock removed — channel missing (${action.channel_id})`);
    await logChannelTimedAction(guild, action, {
      action: 'channel_unlock_skipped',
      reason: 'Channel no longer exists; timed unlock removed.',
    }).catch(() => {});
    return { outcome: 'terminal', reason: 'channel_missing' };
  }

  const roleId = action.role_id ?? guild.roles.everyone.id;
  if (roleId !== guild.roles.everyone.id) {
    const role = guild.roles.cache.get(roleId) ?? await guild.roles.fetch(roleId).catch(() => null);
    if (!role) {
      console.warn(`[scheduler] Channel unlock removed — role missing (${roleId})`);
      return { outcome: 'terminal', reason: 'role_missing' };
    }
  }

  const me = guild.members.me ?? await guild.members.fetchMe().catch(() => null);
  if (!me?.permissions.has(PermissionFlagsBits.ManageChannels)) {
    console.warn(`[scheduler] Channel unlock retry — missing ManageChannels (${action.channel_id})`);
    return { outcome: 'retryable', reason: 'missing_permissions' };
  }

  const overwrite = channel.permissionOverwrites.cache.get(roleId);
  const appliedState = action.applied_state ?? 'deny';

  if (!channelPermissionMatches(overwrite, permission, appliedState)) {
    const currentState = getPermissionState(overwrite, permission);
    console.warn(
      `[scheduler] Channel unlock skipped — manual change in ${action.channel_id} `
      + `(expected ${appliedState}, found ${currentState})`,
    );
    await logChannelTimedAction(guild, action, {
      action: 'channel_unlock_skipped',
      reason: `Timed unlock skipped: ${permission} was changed manually (now ${currentState}).`,
      channel,
    }).catch(() => {});
    return { outcome: 'terminal', reason: 'manual_change' };
  }

  try {
    const result = await restoreChannelFromTimedAction(channel, roleId, action);
    if (result.type === 'conflict') {
      return { outcome: 'terminal', reason: 'manual_change' };
    }

    await logChannelTimedAction(guild, action, {
      action: 'unlock',
      reason: `Timed lock expired; restored ${permission} to ${result.previousState}.`,
      channel,
    }).catch(() => {});
    return { outcome: 'completed', previousState: result.previousState };
  } catch (err) {
    console.error(`[scheduler] Channel unlock retry — API error for ${action.channel_id}:`, err.message);
    return { outcome: 'retryable', reason: 'api_error', error: err };
  }
}

async function logChannelTimedAction(guild, action, { action: logAction, reason, channel }) {
  const targetChannel = channel ?? { id: action.channel_id, toString: () => `<#${action.channel_id}>` };
  const moderator = action.moderator_id
    ? { id: action.moderator_id, toString: () => `<@${action.moderator_id}>` }
    : { id: '0', toString: () => 'Scheduler' };

  await sendModLog(guild, {
    action: logAction,
    target: targetChannel,
    moderator,
    reason,
  });
}

function shouldLogChannelFailure(action, sanitizedError) {
  const attemptCount = action.attempt_count ?? 0;
  if (attemptCount === 0) return true;
  if (action.last_logged_error !== sanitizedError) return true;
  if (attemptCount + 1 >= MAX_CHANNEL_UNLOCK_ATTEMPTS) return true;
  return false;
}

async function handleChannelUnlockRetry(client, action, result) {
  const attemptCount = (action.attempt_count ?? 0) + 1;
  const sanitizedError = sanitizeTimedActionError(result.error ?? result.reason);

  if (attemptCount >= MAX_CHANNEL_UNLOCK_ATTEMPTS) {
    await markTimedActionFailed(action.id, { lastError: sanitizedError, attemptCount });
    const guild = await client.guilds.fetch(action.guild_id).catch(() => null);
    if (guild) {
      await logChannelTimedAction(guild, action, {
        action: 'channel_unlock_failed',
        reason: `Timed unlock abandoned after ${MAX_CHANNEL_UNLOCK_ATTEMPTS} attempts. Manual intervention required. Last error: ${sanitizedError}`,
      }).catch(() => {});
    }
    console.error(
      `[scheduler] Channel unlock ${action.id} marked failed after ${MAX_CHANNEL_UNLOCK_ATTEMPTS} attempts`,
    );
    return { outcome: 'failed_max' };
  }

  const nextRetryAt = Date.now() + getRetryDelayMs(attemptCount);
  const shouldLog = shouldLogChannelFailure(action, sanitizedError);
  await recordTimedActionRetry(action.id, {
    attemptCount,
    lastError: sanitizedError,
    nextRetryAt,
    lastLoggedError: shouldLog ? sanitizedError : undefined,
  });

  if (shouldLog) {
    console.warn(
      `[scheduler] Channel unlock ${action.id} attempt ${attemptCount} failed (${sanitizedError}); `
      + `retry at ${new Date(nextRetryAt).toISOString()}`,
    );
  } else {
    console.warn(
      `[scheduler] Channel unlock ${action.id} attempt ${attemptCount} failed (${sanitizedError}); retry scheduled`,
    );
  }

  return { outcome: 'retryable' };
}

export async function handleTimedActionResult(client, action, result) {
  if (result.outcome === 'completed' || result.outcome === 'terminal') {
    const removed = await completeTimedAction(action.id);
    if (!removed) {
      console.error(
        `[scheduler] Permission change succeeded but timed action ${action.id} could not be removed`,
      );
    }
    return;
  }

  if (result.outcome === 'failed_max') {
    return;
  }

  if (result.outcome === 'retryable' && (action.action === 'channel_unlock' || action.action === 'lockdown_channel_restore')) {
    const retryResult = await handleChannelUnlockRetry(client, action, result);
    if (retryResult.outcome === 'failed_max') {
      return;
    }
    return;
  }

  if (result.outcome === 'retryable') {
    const attemptCount = (action.attempt_count ?? 0) + 1;
    const sanitizedError = sanitizeTimedActionError(result.error ?? result.reason);
    const nextRetryAt = Date.now() + getRetryDelayMs(attemptCount);
    await recordTimedActionRetry(action.id, {
      attemptCount,
      lastError: sanitizedError,
      nextRetryAt,
    });
  }
}

export async function processDueTimedActions(client) {
  const { getDueTimedActions } = await import('../database/db.js');
  let actions;
  try {
    actions = await getDueTimedActions();
  } catch (err) {
    console.error('[scheduler] Database read failed:', err.message);
    return;
  }

  for (const action of actions) {
    let result;
    try {
      result = await executeTimedAction(client, action);
    } catch (err) {
      console.error('[scheduler] Action failed:', err.message);
      result = { outcome: 'retryable', reason: 'unexpected', error: err };
    }

    try {
      await handleTimedActionResult(client, action, result);
    } catch (err) {
      console.error('[scheduler] Failed to persist timed action result:', err.message);
    }
  }
}
