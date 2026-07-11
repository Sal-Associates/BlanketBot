import { resolveChannel, resolveRole } from './helpers.js';

export function isAutomodEligibleChannel(channel) {
  return Boolean(channel?.isTextBased?.());
}

export function resolveChannelTarget(guild, input) {
  if (!input?.trim()) return null;
  const trimmed = input.trim();
  const mention = trimmed.match(/^<#(\d+)>$/);
  if (mention) {
    const id = mention[1];
    return { id, channel: guild.channels.cache.get(id) ?? null };
  }
  if (/^\d{17,20}$/.test(trimmed)) {
    return { id: trimmed, channel: guild.channels.cache.get(trimmed) ?? null };
  }
  const channel = resolveChannel(guild, trimmed);
  return channel ? { id: channel.id, channel } : null;
}

export function resolveRoleTarget(guild, input) {
  if (!input?.trim()) return null;
  const trimmed = input.trim();
  const mention = trimmed.match(/^<@&(\d+)>$/);
  if (mention) {
    const id = mention[1];
    return { id, role: guild.roles.cache.get(id) ?? null };
  }
  if (/^\d{17,20}$/.test(trimmed)) {
    return { id: trimmed, role: guild.roles.cache.get(trimmed) ?? null };
  }
  const role = resolveRole(guild, trimmed);
  return role ? { id: role.id, role } : null;
}

export function formatIgnoredChannelLine(guild, channelId) {
  const channel = guild.channels.cache.get(channelId);
  if (channel) {
    return `${channel} — \`${channelId}\``;
  }
  return `Deleted or inaccessible channel — \`${channelId}\``;
}

export function formatIgnoredRoleLine(guild, roleId) {
  const role = guild.roles.cache.get(roleId);
  if (role) {
    return `${role.name} (${role}) — \`${roleId}\``;
  }
  return `Deleted or inaccessible role — \`${roleId}\``;
}
