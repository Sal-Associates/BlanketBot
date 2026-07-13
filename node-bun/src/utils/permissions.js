import { PermissionFlagsBits } from 'discord.js';
import { getModRoles, getAdminRoles } from '../database/db.js';
import { error } from './helpers.js';

const SUPERUSER_IDS = new Set(
  (process.env.SUPERUSER_IDS ?? '')
    .split(',')
    .map((id) => id.trim())
    .filter(Boolean)
);

export const MODERATION_DENIAL = {
  SELF: 'You cannot moderate yourself.',
  TARGET_IS_OWNER: 'You cannot moderate the server owner.',
  TARGET_ABOVE_ISSUER: 'Your highest role must be above the target\'s highest role.',
  BOT_CANNOT_ACT: 'My highest role must be above the target\'s highest role.',
  NOT_A_MEMBER: 'That user is not currently a member of this server.',
};

export function isSuperuser(userId) {
  return SUPERUSER_IDS.has(userId);
}

export async function isModerator(member) {
  if (!member) return false;
  if (isSuperuser(member.id)) return true;
  if (member.permissions.has(PermissionFlagsBits.Administrator)) return true;
  if (member.permissions.has(PermissionFlagsBits.ModerateMembers)) return true;
  if (member.permissions.has(PermissionFlagsBits.ManageMessages)) return true;
  const modRoles = await getModRoles(member.guild.id);
  return member.roles.cache.some((role) => modRoles.includes(role.id));
}

export async function isAdmin(member) {
  if (!member) return false;
  if (isSuperuser(member.id)) return true;
  if (member.permissions.has(PermissionFlagsBits.Administrator)) return true;
  const adminRoles = await getAdminRoles(member.guild.id);
  return member.roles.cache.some((role) => adminRoles.includes(role.id));
}

function getTargetId(target) {
  return target?.id ?? target?.user?.id ?? null;
}

function isGuildMember(target) {
  return Boolean(target?.roles?.highest);
}

export function checkBotCanActOn(guild, target) {
  if (!isGuildMember(target)) {
    return { allowed: false, reason: MODERATION_DENIAL.NOT_A_MEMBER };
  }

  if (target.id === guild.ownerId) {
    return { allowed: false, reason: MODERATION_DENIAL.TARGET_IS_OWNER };
  }

  const bot = guild.members.me;
  if (!bot || bot.roles.highest.position <= target.roles.highest.position) {
    return { allowed: false, reason: MODERATION_DENIAL.BOT_CANNOT_ACT };
  }

  return { allowed: true, reason: null };
}

export function checkModerationTarget(guild, issuer, target, { requireMember = true } = {}) {
  const targetId = getTargetId(target);
  if (!issuer || !targetId) {
    return { allowed: false, reason: MODERATION_DENIAL.NOT_A_MEMBER };
  }

  const memberTarget = isGuildMember(target);

  if (requireMember && !memberTarget) {
    return { allowed: false, reason: MODERATION_DENIAL.NOT_A_MEMBER };
  }

  if (issuer.id === targetId) {
    return { allowed: false, reason: MODERATION_DENIAL.SELF };
  }

  if (targetId === guild.ownerId) {
    return { allowed: false, reason: MODERATION_DENIAL.TARGET_IS_OWNER };
  }

  if (memberTarget) {
    const botCheck = checkBotCanActOn(guild, target);
    if (!botCheck.allowed) return botCheck;

    if (issuer.id !== guild.ownerId && issuer.roles.highest.position <= target.roles.highest.position) {
      return { allowed: false, reason: MODERATION_DENIAL.TARGET_ABOVE_ISSUER };
    }
  }

  return { allowed: true, reason: null };
}

export function getModerationDenied(guild, issuer, target, options = {}) {
  const result = checkModerationTarget(guild, issuer, target, options);
  if (result.allowed) return null;
  return error(result.reason);
}
