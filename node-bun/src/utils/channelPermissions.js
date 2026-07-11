import { PermissionFlagsBits } from 'discord.js';

export const CHANNEL_PERMISSION_FLAGS = {
  SendMessages: PermissionFlagsBits.SendMessages,
};

export function resolvePermissionFlag(permission) {
  const bit = CHANNEL_PERMISSION_FLAGS[permission] ?? PermissionFlagsBits[permission];
  if (!bit) {
    throw new Error(`Unsupported channel permission: ${permission}`);
  }
  return bit;
}

/** @returns {'allow' | 'deny' | 'unset'} */
export function getPermissionState(overwrite, permission) {
  const bit = resolvePermissionFlag(permission);
  if (!overwrite) return 'unset';
  if (overwrite.allow.has(bit)) return 'allow';
  if (overwrite.deny.has(bit)) return 'deny';
  return 'unset';
}

export function permissionStateToOverwriteValue(state) {
  if (state === 'allow') return true;
  if (state === 'deny') return false;
  return null;
}

export async function applyPermissionState(channel, roleId, permission, state) {
  const value = permissionStateToOverwriteValue(state);
  await channel.permissionOverwrites.edit(roleId, { [permission]: value });
}

export function channelPermissionMatches(overwrite, permission, expectedState) {
  return getPermissionState(overwrite, permission) === expectedState;
}
