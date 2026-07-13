import { getGuildSettings, getWarnings, createCase } from '../database/db.js';
import { sendModLog, getOrCreateMuteRole } from './modLog.js';
import { checkBotCanActOn } from './permissions.js';
import { error, success } from './helpers.js';
import { persistenceLoggingFailureMessage } from './moderationCompensation.js';

async function recordStrikeFailure(guild, target, moderator, action, reason, logAction) {
  try {
    const caseNum = await createCase(guild.id, target.id, moderator.id, action, reason, {
      source: 'strike',
      status: 'failed',
    });
    const notified = await sendModLog(guild, {
      action: logAction,
      target,
      moderator,
      reason,
      caseNumber: caseNum,
    });
    if (!notified) {
      console.error(`[strikes] Mod-log channel notification failed for ${action} case #${caseNum}`);
    }
    return caseNum;
  } catch (err) {
    console.error(`[strikes] Failed to record ${action}:`, err.message);
    return null;
  }
}

export async function checkStrikeEscalation(guild, target, moderator) {
  const settings = await getGuildSettings(guild.id);
  if (!settings.strike_enabled) return null;

  const warnCount = (await getWarnings(guild.id, target.id)).length;
  const muteAt = settings.strike_mute_at ?? 3;
  const banAt = settings.strike_ban_at ?? 5;

  if (warnCount >= banAt) {
    const botCheck = checkBotCanActOn(guild, target);
    if (!botCheck.allowed) {
      await recordStrikeFailure(
        guild,
        target,
        moderator,
        'strike_ban_failed',
        `Auto-ban failed at ${warnCount} warnings: ${botCheck.reason}`,
        'strike_ban_failed',
      );
      return error(`Strike escalation failed: ${botCheck.reason}`);
    }

    try {
      await target.ban({ reason: `Strike escalation: ${warnCount} warnings`, deleteMessageSeconds: 0 });
    } catch {
      await recordStrikeFailure(
        guild,
        target,
        moderator,
        'strike_ban_failed',
        `Auto-ban failed at ${warnCount} warnings: Discord rejected the ban`,
        'strike_ban_failed',
      );
      return error('Strike escalation failed: could not ban that user.');
    }

    try {
      const caseNum = await createCase(guild.id, target.id, moderator.id, 'strike_ban', `Auto-ban at ${warnCount} warnings`, {
        source: 'strike',
        status: 'success',
      });
      const notified = await sendModLog(guild, {
        action: 'strike_ban',
        target,
        moderator,
        reason: `Auto-ban at ${warnCount} warnings (threshold: ${banAt})`,
        caseNumber: caseNum,
      });
      if (!notified) {
        console.error(`[strikes] Mod-log channel notification failed for strike_ban case #${caseNum}`);
      }
      return success(`**${target.user.tag}** auto-banned — reached **${warnCount}** warnings (ban threshold: ${banAt}). Case #${caseNum}`);
    } catch (err) {
      console.error('[strikes] Ban succeeded but case logging failed:', err.message);
      return error(persistenceLoggingFailureMessage('auto-banned'));
    }
  }

  if (warnCount >= muteAt) {
    const muteRole = await getOrCreateMuteRole(guild);
    if (!target.roles.cache.has(muteRole.id)) {
      const botCheck = checkBotCanActOn(guild, target);
      if (!botCheck.allowed) {
        await recordStrikeFailure(
          guild,
          target,
          moderator,
          'strike_mute_failed',
          `Auto-mute failed at ${warnCount} warnings: ${botCheck.reason}`,
          'strike_mute_failed',
        );
        return error(`Strike escalation failed: ${botCheck.reason}`);
      }

      try {
        await target.roles.add(muteRole, `Strike escalation: ${warnCount} warnings`);
      } catch {
        await recordStrikeFailure(
          guild,
          target,
          moderator,
          'strike_mute_failed',
          `Auto-mute failed at ${warnCount} warnings: Discord rejected the mute`,
          'strike_mute_failed',
        );
        return error('Strike escalation failed: could not mute that user.');
      }

      try {
        const caseNum = await createCase(guild.id, target.id, moderator.id, 'strike_mute', `Auto-mute at ${warnCount} warnings`, {
          source: 'strike',
          status: 'success',
        });
        const notified = await sendModLog(guild, {
          action: 'strike_mute',
          target,
          moderator,
          reason: `Auto-mute at ${warnCount} warnings (threshold: ${muteAt})`,
          caseNumber: caseNum,
        });
        if (!notified) {
          console.error(`[strikes] Mod-log channel notification failed for strike_mute case #${caseNum}`);
        }
        return success(`**${target.user.tag}** auto-muted — reached **${warnCount}** warnings (mute threshold: ${muteAt}). Case #${caseNum}`);
      } catch (err) {
        console.error('[strikes] Mute succeeded but case logging failed:', err.message);
        return error(persistenceLoggingFailureMessage('auto-muted'));
      }
    }
  }

  return null;
}
