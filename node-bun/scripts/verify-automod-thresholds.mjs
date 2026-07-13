import assert from 'node:assert/strict';

process.env.GUILD_ID = process.env.GUILD_ID || '123456789012345678';
process.env.SUPERUSER_IDS = '';

import { mkdtemp, rm, writeFile } from 'fs/promises';
import { join } from 'path';
import { tmpdir } from 'os';
import {
  AUTOMOD_THRESHOLD_DEFAULTS,
  CAPS_MIN_LETTERS,
  coerceThresholdValue,
  normalizeAutomodThresholds,
  validateCapsThresholdInput,
  validateSpamCountInput,
  validateSpamWindowInput,
  validateMentionThresholdInput,
  capsPercentage,
  isMassMention,
  countMentionTargets,
  getThresholdResetUpdates,
  formatThresholdShow,
} from '../src/utils/automodThresholds.js';
import { parseDuration } from '../src/utils/time.js';
import {
  trackSpam,
  pruneSpamTracker,
  resetSpamTracker,
} from '../src/handlers/automodHandler.js';

async function withTempDatabase(run) {
  const dir = await mkdtemp(join(tmpdir(), 'modbot-automod-threshold-'));
  const dbPath = join(dir, 'store.json');
  try {
    await run(dbPath, dir);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

function createMockMessage({
  content = '',
  users = 0,
  roles = 0,
  everyone = false,
}) {
  return {
    content,
    mentions: {
      users: { size: users },
      roles: { size: roles },
      everyone,
    },
  };
}

console.log('Running Automod threshold tests...');

assert.deepEqual(AUTOMOD_THRESHOLD_DEFAULTS, {
  caps_threshold: 70,
  spam_threshold: 5,
  spam_interval: 5000,
  mention_threshold: 5,
});
console.log('canonical defaults: PASS');

const fresh = normalizeAutomodThresholds({});
assert.equal(fresh.caps_threshold, 70);
assert.equal(fresh.mention_threshold, 5);
console.log('fresh guild defaults: PASS');

assert.equal(validateCapsThresholdInput('75').value, 75);
assert.equal(validateCapsThresholdInput('50').ok, true);
assert.equal(validateCapsThresholdInput('100').ok, true);
assert.equal(validateCapsThresholdInput('49').ok, false);
assert.equal(validateCapsThresholdInput('101').ok, false);
assert.equal(validateCapsThresholdInput('75.5').ok, false);
assert.equal(validateCapsThresholdInput('abc').ok, false);
console.log('caps validation: PASS');

const upper = 'A'.repeat(CAPS_MIN_LETTERS);
assert.equal(capsPercentage(upper), 100);
assert.equal(capsPercentage('A'.repeat(CAPS_MIN_LETTERS - 1)), 0);
console.log('caps runtime minimum length: PASS');

assert.equal(validateSpamCountInput('3').ok, true);
assert.equal(validateSpamCountInput('20').ok, true);
assert.equal(validateSpamCountInput('2').ok, false);
assert.equal(validateSpamCountInput('21').ok, false);
assert.equal(validateSpamWindowInput('5s', parseDuration).value, 5000);
assert.equal(validateSpamWindowInput('1m', parseDuration).value, 60000);
assert.equal(validateSpamWindowInput('500', parseDuration).ok, false);
assert.equal(validateSpamWindowInput('61s', parseDuration).ok, false);
assert.equal(validateSpamWindowInput('0s', parseDuration).ok, false);
console.log('spam validation: PASS');

assert.equal(validateMentionThresholdInput('2').ok, true);
assert.equal(validateMentionThresholdInput('50').ok, true);
assert.equal(validateMentionThresholdInput('1').ok, false);
assert.equal(validateMentionThresholdInput('51').ok, false);
console.log('mentions validation: PASS');

assert.equal(isMassMention(createMockMessage({ users: 4, roles: 0 }), 5), false);
assert.equal(isMassMention(createMockMessage({ users: 4, roles: 1 }), 5), true);
assert.equal(isMassMention(createMockMessage({ users: 0, roles: 0, everyone: true }), 5), true);
assert.equal(countMentionTargets(createMockMessage({ users: 2, roles: 1 })), 3);
console.log('mention runtime semantics: PASS');

resetSpamTracker();
const guildId = 'g1';
const userId = 'u1';
assert.equal(trackSpam(guildId, userId, 3, 5000), false);
assert.equal(trackSpam(guildId, userId, 3, 5000), false);
assert.equal(trackSpam(guildId, userId, 3, 5000), true);
console.log('spam tracker threshold: PASS');

resetSpamTracker();
for (let i = 0; i < 100; i++) {
  trackSpam('g2', `user-${i}`, 5, 5000);
}
pruneSpamTracker(Date.now() + 121_000);
assert.equal(trackSpam('g2', 'user-new', 5, 5000), false);
console.log('spam tracker cleanup: PASS');

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await import('../src/database/db.js');
  db.configureDatabase({ path: dbPath, hooks: {} });
  await db.initializeDatabase();

  const guildIdDb = '123456789012345678';
  const settings = await db.getGuildSettings(guildIdDb);
  assert.equal(settings.caps_threshold, AUTOMOD_THRESHOLD_DEFAULTS.caps_threshold);
  assert.equal(settings.mention_threshold, AUTOMOD_THRESHOLD_DEFAULTS.mention_threshold);
  console.log('database default thresholds: PASS');

  await db.updateGuildSetting(guildIdDb, 'caps_threshold', 85);
  await db.updateGuildSetting(guildIdDb, 'anti_caps', 0);
  const afterCaps = await db.getGuildSettings(guildIdDb);
  assert.equal(afterCaps.caps_threshold, 85);
  assert.equal(afterCaps.anti_caps, 0);
  console.log('toggle independence (caps): PASS');

  await db.updateGuildSetting(guildIdDb, 'anti_caps', 1);
  const reenabled = await db.getGuildSettings(guildIdDb);
  assert.equal(reenabled.caps_threshold, 85);
  console.log('re-enable preserves threshold: PASS');

  await db.updateGuildSettings(guildIdDb, getThresholdResetUpdates('spam'));
  const resetSpam = await db.getGuildSettings(guildIdDb);
  assert.equal(resetSpam.spam_threshold, 5);
  assert.equal(resetSpam.spam_interval, 5000);
  assert.equal(resetSpam.caps_threshold, 85);
  console.log('reset spam only: PASS');

  await db.updateGuildSettings(guildIdDb, getThresholdResetUpdates('all'));
  const resetAll = await db.getGuildSettings(guildIdDb);
  assert.equal(resetAll.caps_threshold, 70);
  assert.equal(resetAll.mention_threshold, 5);
  assert.equal(resetAll.anti_caps, 1);
  console.log('reset all thresholds preserves toggles: PASS');
});

await withTempDatabase(async (dbPath, dir) => {
  const guildIdLegacy = 'legacy-guild';
  await writeFile(dbPath, JSON.stringify({
    guild_settings: {
      [guildIdLegacy]: {
        guild_id: guildIdLegacy,
        caps_threshold: '80',
        spam_interval: '10000',
        mention_threshold: '7',
      },
    },
    mod_roles: [],
    admin_roles: [],
    warnings: [],
    notes: [],
    mod_logs: [],
    automod_words: [],
    banned_words: [],
    automod_links: [],
    automod_ignored_channels: [],
    automod_ignored_roles: [],
    timed_actions: [],
    cases: [],
    mod_queue: [],
    case_counters: {},
    _counters: { warnings: 0, notes: 0, mod_logs: 0, timed_actions: 0, mod_queue: 0, banned_words: 0 },
  }, null, 2));

  process.env.STORE_PATH = dbPath;
  const db = await import('../src/database/db.js');
  db.configureDatabase({ path: dbPath, hooks: {} });
  await db.initializeDatabase();

  const settings = await db.getGuildSettings(guildIdLegacy);
  assert.equal(settings.caps_threshold, 80);
  assert.equal(settings.spam_interval, 10000);
  assert.equal(settings.mention_threshold, 7);
  console.log('legacy numeric string normalization: PASS');

  const invalid = normalizeAutomodThresholds({
    caps_threshold: 200,
    spam_threshold: 'bad',
    spam_interval: 999999,
    mention_threshold: 1,
  });
  assert.equal(invalid.caps_threshold, 70);
  assert.equal(invalid.spam_threshold, 5);
  assert.equal(invalid.spam_interval, 5000);
  assert.equal(invalid.mention_threshold, 5);
  console.log('invalid values fall back to defaults: PASS');

  const show = formatThresholdShow({
    anti_caps: 1,
    anti_spam: 0,
    anti_mention: 1,
    caps_threshold: 80,
    spam_threshold: 5,
    spam_interval: 10000,
    mention_threshold: 7,
  });
  assert.match(show, /80%/);
  assert.match(show, /10s/);
  assert.match(show, /7 user\/role mentions/);
  console.log('threshold show formatting: PASS');

  await db.addBannedWord(guildIdLegacy, 'badword', 'contains', 'mod-1');
  await db.updateGuildSetting(guildIdLegacy, 'anti_caps', 1);
  await db.updateGuildSetting(guildIdLegacy, 'caps_threshold', 50);

  const { handleAutomod } = await import('../src/handlers/automodHandler.js');
  let deleted = false;
  const msg = {
    guild: { id: guildIdLegacy },
    author: { id: 'user-1', bot: false },
    content: 'A'.repeat(CAPS_MIN_LETTERS),
    member: {
      id: 'user-1',
      guild: { id: guildIdLegacy },
      permissions: { has: () => false },
      roles: { cache: { some: () => false } },
    },
    channel: { id: 'ch-1', send: async () => ({ delete: async () => {} }) },
    mentions: { users: { size: 0 }, roles: { size: 0 }, everyone: false },
    delete: async () => { deleted = true; },
  };

  assert.equal(await handleAutomod(msg), true);
  assert.equal(deleted, true);
  console.log('runtime uses updated caps threshold: PASS');
});

console.log('All Automod threshold tests passed.');
