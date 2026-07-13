import {
  getGuildSettings, getBannedWords, getAutomodLinks,
  getIgnoredChannels, getIgnoredRoles, isModuleDisabled,
} from '../database/db.js';
import { isModerator } from '../utils/permissions.js';
import { LINK_REGEX, INVITE_REGEX } from '../utils/helpers.js';
import { findBannedWordMatch, formatBannedWordReason } from '../utils/bannedWords.js';
import {
  resolveAutomodThresholds,
  capsPercentage,
  isMassMention,
} from '../utils/automodThresholds.js';
import { sendToModQueue } from './modQueue.js';

const spamTracker = new Map();
const SPAM_TRACKER_MAX_AGE_MS = 120_000;

function getSpamKey(guildId, userId) {
  return `${guildId}:${userId}`;
}

export function pruneSpamTracker(now = Date.now()) {
  for (const [key, entry] of spamTracker) {
    if (now - entry.first > SPAM_TRACKER_MAX_AGE_MS) {
      spamTracker.delete(key);
    }
  }
}

export function trackSpam(guildId, userId, threshold, interval) {
  const key = getSpamKey(guildId, userId);
  const now = Date.now();
  const existing = spamTracker.get(key);

  if (!existing || now - existing.first > interval) {
    spamTracker.set(key, { count: 1, first: now });
    if (spamTracker.size % 50 === 0) {
      pruneSpamTracker(now);
    }
    return false;
  }

  existing.count++;
  spamTracker.set(key, existing);
  return existing.count >= threshold;
}

export function resetSpamTracker() {
  spamTracker.clear();
}

function checkLinks(content, blacklist, whitelist) {
  const links = [...content.matchAll(new RegExp(LINK_REGEX.source, 'gi'))].map((m) => m[0]);
  if (!links.length) return null;

  for (const link of links) {
    const lower = link.toLowerCase();
    const isWhitelisted = whitelist.some((w) => lower.includes(w));
    if (isWhitelisted) continue;

    if (blacklist.length === 0 || blacklist.some((b) => lower.includes(b))) {
      return link;
    }
  }
  return null;
}

export async function handleAutomod(message) {
  if (!message.guild || message.author.bot) return false;

  if (await isModuleDisabled(message.guild.id, 'Automod')) return false;

  const ignoredChannels = await getIgnoredChannels(message.guild.id);
  if (ignoredChannels.includes(message.channel.id)) return false;

  const member = message.member;
  if (!member) return false;

  const ignoredRoles = await getIgnoredRoles(message.guild.id);
  if (member.roles.cache.some((r) => ignoredRoles.includes(r.id))) return false;

  if (await isModerator(member)) return false;

  const settings = resolveAutomodThresholds(await getGuildSettings(message.guild.id));
  const content = message.content;
  let reason = null;

  const bannedWords = await getBannedWords(message.guild.id);
  const bannedMatch = findBannedWordMatch(content, bannedWords);
  if (bannedMatch) reason = formatBannedWordReason(bannedMatch);

  if (!reason && settings.anti_invite && INVITE_REGEX.test(content)) {
    reason = 'Discord invite link';
  }

  if (!reason && settings.anti_mention && isMassMention(message, settings.mention_threshold)) {
    reason = 'Mass mention';
  }

  if (!reason) {
    const blacklist = await getAutomodLinks(message.guild.id, 'blacklist');
    const whitelist = await getAutomodLinks(message.guild.id, 'whitelist');
    const badLink = checkLinks(content, blacklist, whitelist);
    if (badLink) reason = `Blocked link: ${badLink}`;
  }

  if (!reason && settings.anti_caps && capsPercentage(content) >= settings.caps_threshold) {
    reason = 'Excessive caps';
  }

  if (!reason && settings.anti_spam) {
    const isSpam = trackSpam(
      message.guild.id,
      message.author.id,
      settings.spam_threshold,
      settings.spam_interval,
    );
    if (isSpam) reason = 'Spam detected';
  }

  if (!reason) return false;

  if (settings.mod_queue_enabled && settings.mod_queue_channel) {
    const queued = await sendToModQueue(message, reason);
    if (queued) return true;
  }

  await message.delete().catch(() => {});
  const warning = await message.channel.send(
    `${message.author}, your message was removed: **${reason}**`,
  );
  setTimeout(() => warning.delete().catch(() => {}), 5000);

  return true;
}
