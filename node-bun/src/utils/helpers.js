import { EmbedBuilder } from 'discord.js';

export function success(message) {
  return `✅ ${message}`;
}

export function error(message) {
  return `❌ ${message}`;
}

export function info(message) {
  return `ℹ️ ${message}`;
}

export function resolveMember(message, input) {
  if (!input) return message.member;
  const mention = input.match(/^<@!?(\d+)>$/);
  if (mention) return message.guild.members.cache.get(mention[1]) ?? null;
  const byId = message.guild.members.cache.get(input);
  if (byId) return byId;
  const byName = message.guild.members.cache.find(
    (m) => m.user.username.toLowerCase() === input.toLowerCase() ||
      m.displayName.toLowerCase() === input.toLowerCase()
  );
  return byName ?? null;
}

export function resolveUserTarget(message, input) {
  const member = resolveMember(message, input);
  if (member) return { member, userId: member.id };

  if (!input) return null;
  const mention = input.match(/^<@!?(\d+)>$/);
  if (mention) return { member: null, userId: mention[1] };
  if (/^\d{17,20}$/.test(input)) return { member: null, userId: input };
  return null;
}

export function resolveRole(guild, input) {
  if (!input) return null;
  const mention = input.match(/^<@&(\d+)>$/);
  if (mention) return guild.roles.cache.get(mention[1]) ?? null;
  const byId = guild.roles.cache.get(input);
  if (byId) return byId;
  return guild.roles.cache.find((r) => r.name.toLowerCase() === input.toLowerCase()) ?? null;
}

export function resolveChannel(guild, input) {
  if (!input) return null;
  const mention = input.match(/^<#(\d+)>$/);
  if (mention) return guild.channels.cache.get(mention[1]) ?? null;
  const byId = guild.channels.cache.get(input);
  if (byId) return byId;
  return guild.channels.cache.find((c) => c.name.toLowerCase() === input.toLowerCase()) ?? null;
}

export function parseArgs(content, prefix) {
  const withoutPrefix = content.slice(prefix.length).trim();
  const match = withoutPrefix.match(/^(\S+)\s*(.*)?$/s);
  if (!match) return { command: '', args: '', subcommand: '', subargs: '' };

  const parts = withoutPrefix.split(/\s+/);
  const command = parts[0]?.toLowerCase() ?? '';
  const rest = parts.slice(1).join(' ');

  const subParts = rest.split(/\s+/);
  const subcommand = subParts[0]?.toLowerCase() ?? '';
  const subargs = subParts.slice(1).join(' ');

  return { command, args: rest, subcommand, subargs };
}

export function basicEmbed(title, description, color = 0x5865f2) {
  return new EmbedBuilder().setTitle(title).setDescription(description).setColor(color);
}

export const LINK_REGEX = /https?:\/\/[^\s]+/i;
export const INVITE_REGEX = /(?:https?:\/\/)?(?:www\.)?(?:discord\.(?:gg|io|me|li)|discordapp\.com\/invite)\/[^\s]+/i;
