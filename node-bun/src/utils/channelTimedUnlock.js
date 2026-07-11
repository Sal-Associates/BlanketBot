import {
  applyPermissionState,
  channelPermissionMatches,
  getPermissionState,
} from './channelPermissions.js';

/**
 * Restore a channel permission from a pending channel_unlock action.
 * @returns {{ type: 'restored', previousState: string } | { type: 'conflict', currentState: string }}
 */
export async function restoreChannelFromTimedAction(channel, roleId, timedAction) {
  const permission = timedAction.permission || 'SendMessages';
  const appliedState = timedAction.applied_state ?? 'deny';
  const previousState = timedAction.previous_state ?? 'unset';
  const overwrite = channel.permissionOverwrites.cache.get(roleId);

  if (!channelPermissionMatches(overwrite, permission, appliedState)) {
    return {
      type: 'conflict',
      currentState: getPermissionState(overwrite, permission),
    };
  }

  await applyPermissionState(channel, roleId, permission, previousState);
  return { type: 'restored', previousState };
}
