export async function rollbackTemporaryMute(target, muteRole) {
  try {
    await target.roles.remove(muteRole, 'Rollback: moderation record could not be saved');
    return { success: true };
  } catch (err) {
    console.error('[moderation] Mute rollback failed:', err.message);
    return { success: false, error: err.message };
  }
}

export async function rollbackTemporaryBan(guild, userId) {
  try {
    await guild.members.unban(userId, 'Rollback: moderation record could not be saved');
    return { success: true };
  } catch (err) {
    console.error('[moderation] Ban rollback failed:', err.message);
    return { success: false, error: err.message };
  }
}

export function persistenceRollbackMessage(actionLabel, rollback) {
  if (rollback.success) {
    return `The ${actionLabel} was applied but could not be safely scheduled. The ${actionLabel} was reversed.`;
  }
  return `The ${actionLabel} was applied but recordkeeping failed. Rollback also failed—manual intervention required.`;
}

export function persistenceLoggingFailureMessage(actionLabel) {
  return `The user was ${actionLabel}, but the moderation record could not be saved.`;
}
