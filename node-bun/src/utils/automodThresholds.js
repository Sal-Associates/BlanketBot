import { formatDuration } from './time.js';

export const CAPS_MIN_LETTERS = 8;

export const AUTOMOD_THRESHOLD_DEFAULTS = {
  caps_threshold: 70,
  spam_threshold: 5,
  spam_interval: 5000,
  mention_threshold: 5,
};

export const THRESHOLD_KEYS = Object.keys(AUTOMOD_THRESHOLD_DEFAULTS);

const INTEGER_KEYS = new Set(['caps_threshold', 'spam_threshold', 'mention_threshold']);

export const THRESHOLD_RANGES = {
  caps_threshold: { min: 50, max: 100 },
  spam_threshold: { min: 3, max: 20 },
  spam_interval: { min: 1000, max: 60000 },
  mention_threshold: { min: 2, max: 50 },
};

function parseInteger(raw) {
  if (typeof raw === 'number' && Number.isInteger(raw)) return raw;
  if (typeof raw === 'string' && /^\d+$/.test(raw.trim())) return parseInt(raw.trim(), 10);
  return null;
}

function parseMs(raw) {
  if (typeof raw === 'number' && Number.isFinite(raw)) return Math.round(raw);
  if (typeof raw === 'string' && /^\d+$/.test(raw.trim())) return parseInt(raw.trim(), 10);
  return null;
}

export function coerceThresholdValue(key, raw, defaultValue = AUTOMOD_THRESHOLD_DEFAULTS[key]) {
  const range = THRESHOLD_RANGES[key];
  if (!range) return { value: defaultValue, replaced: false };

  if (raw === undefined || raw === null) {
    return { value: defaultValue, replaced: false };
  }

  let parsed;
  if (key === 'spam_interval') {
    parsed = parseMs(raw);
  } else {
    parsed = parseInteger(raw);
    if (parsed !== null && !INTEGER_KEYS.has(key)) {
      parsed = null;
    }
  }

  if (parsed === null || !Number.isFinite(parsed)) {
    return { value: defaultValue, replaced: true };
  }

  if (INTEGER_KEYS.has(key) && !Number.isInteger(parsed)) {
    return { value: defaultValue, replaced: true };
  }

  if (parsed < range.min || parsed > range.max) {
    return { value: defaultValue, replaced: true };
  }

  return { value: parsed, replaced: false };
}

export function normalizeAutomodThresholds(settings, { log } = {}) {
  const normalized = { ...settings };
  for (const key of THRESHOLD_KEYS) {
    const { value, replaced } = coerceThresholdValue(key, settings[key], AUTOMOD_THRESHOLD_DEFAULTS[key]);
    if (replaced && settings[key] !== undefined && settings[key] !== value && log) {
      log(`[automod] Invalid ${key}=${JSON.stringify(settings[key])}; using ${value}`);
    }
    normalized[key] = value;
  }
  return normalized;
}

export function resolveAutomodThresholds(settings) {
  return normalizeAutomodThresholds(settings);
}

export function validateCapsThresholdInput(input) {
  const trimmed = input?.trim();
  if (!trimmed || !/^\d+$/.test(trimmed)) {
    return { ok: false, error: 'Caps threshold must be a whole number percentage.' };
  }
  const value = parseInt(trimmed, 10);
  const range = THRESHOLD_RANGES.caps_threshold;
  if (value < range.min || value > range.max) {
    return { ok: false, error: `Caps threshold must be between ${range.min} and ${range.max}.` };
  }
  return { ok: true, value };
}

export function validateSpamCountInput(input) {
  const trimmed = input?.trim();
  if (!trimmed || !/^\d+$/.test(trimmed)) {
    return { ok: false, error: 'Spam count must be a whole number.' };
  }
  const value = parseInt(trimmed, 10);
  const range = THRESHOLD_RANGES.spam_threshold;
  if (value < range.min || value > range.max) {
    return { ok: false, error: `Spam count must be between ${range.min} and ${range.max} messages.` };
  }
  return { ok: true, value };
}

export function validateSpamWindowInput(input, parseDuration) {
  const trimmed = input?.trim();
  if (!trimmed) {
    return { ok: false, error: 'Provide a duration such as `5s` or `1m`.' };
  }

  let msValue;
  if (/^\d+$/.test(trimmed)) {
    msValue = parseInt(trimmed, 10);
  } else {
    msValue = parseDuration(trimmed);
  }

  if (!msValue || !Number.isFinite(msValue)) {
    return { ok: false, error: 'Spam window must be a duration such as `5s` or `1m`.' };
  }

  const range = THRESHOLD_RANGES.spam_interval;
  if (msValue < range.min || msValue > range.max) {
    return { ok: false, error: `Spam window must be between 1 second and 60 seconds.` };
  }

  return { ok: true, value: Math.round(msValue) };
}

export function validateMentionThresholdInput(input) {
  const trimmed = input?.trim();
  if (!trimmed || !/^\d+$/.test(trimmed)) {
    return { ok: false, error: 'Mention threshold must be a whole number.' };
  }
  const value = parseInt(trimmed, 10);
  const range = THRESHOLD_RANGES.mention_threshold;
  if (value < range.min || value > range.max) {
    return { ok: false, error: `Mention threshold must be between ${range.min} and ${range.max}.` };
  }
  return { ok: true, value };
}

export function capsPercentage(content) {
  const letters = content.replace(/[^a-zA-Z]/g, '');
  if (letters.length < CAPS_MIN_LETTERS) return 0;
  const caps = letters.replace(/[^A-Z]/g, '').length;
  return (caps / letters.length) * 100;
}

export function countMentionTargets(message) {
  return message.mentions.users.size + message.mentions.roles.size;
}

export function isMassMention(message, mentionThreshold) {
  if (message.mentions.everyone) return true;
  return countMentionTargets(message) >= mentionThreshold;
}

export function formatSpamWindow(msValue) {
  return formatDuration(msValue);
}

export function formatThresholdShow(settings, { moduleDisabled = false } = {}) {
  const thresholds = resolveAutomodThresholds(settings);
  const inactive = moduleDisabled ? ' (saved, inactive — Automod module disabled)' : '';

  const lines = [
    `**Caps:** ${thresholds.caps_threshold}% at ${CAPS_MIN_LETTERS}+ letters — anti-caps ${settings.anti_caps ? 'enabled' : 'disabled'}${inactive}`,
    `**Spam:** ${thresholds.spam_threshold} messages within ${formatSpamWindow(thresholds.spam_interval)} — anti-spam ${settings.anti_spam ? 'enabled' : 'disabled'}${inactive}`,
    `**Mentions:** ${thresholds.mention_threshold} user/role mentions per message (@everyone/@here always flagged) — anti-mention ${settings.anti_mention ? 'enabled' : 'disabled'}${inactive}`,
    '',
    '_Minimum caps length is fixed at 8 letters (not configurable)._',
    '_Use `?automod threshold reset <caps|spam|mentions|all>` to restore defaults._',
  ];

  return lines.join('\n');
}

export function getThresholdResetUpdates(target) {
  switch (target) {
    case 'caps':
      return { caps_threshold: AUTOMOD_THRESHOLD_DEFAULTS.caps_threshold };
    case 'spam':
      return {
        spam_threshold: AUTOMOD_THRESHOLD_DEFAULTS.spam_threshold,
        spam_interval: AUTOMOD_THRESHOLD_DEFAULTS.spam_interval,
      };
    case 'mentions':
      return { mention_threshold: AUTOMOD_THRESHOLD_DEFAULTS.mention_threshold };
    case 'all':
      return { ...AUTOMOD_THRESHOLD_DEFAULTS };
    default:
      return null;
  }
}
