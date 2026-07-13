import assert from 'node:assert/strict';
import { writeFile, mkdtemp, rm } from 'fs/promises';
import { join } from 'path';
import { tmpdir } from 'os';
import {
  findBannedWordMatch,
  matchBannedWordEntry,
  formatBannedWordReason,
} from '../src/utils/bannedWords.js';

process.env.GUILD_ID = process.env.GUILD_ID || '123456789012345678';

async function withTempDatabase(run) {
  const dir = await mkdtemp(join(tmpdir(), 'modbot-banned-words-'));
  const dbPath = join(dir, 'store.json');
  try {
    await run(dbPath);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

function emptyStore(overrides = {}) {
  return {
    guild_settings: {},
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
    ...overrides,
  };
}

function entry(id, guildId, value, matchMode) {
  return { id, guild_id: guildId, value, match_mode: matchMode, created_at: Date.now(), created_by: null };
}

console.log('Running banned-word consolidation tests...');

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await import('../src/database/db.js');
  db.configureDatabase({ path: dbPath, hooks: {} });

  const guildId = 'guild-migrate';
  await writeFile(dbPath, JSON.stringify(emptyStore({
    automod_words: [
      { guild_id: guildId, word: 'substring', exact: 0 },
      { guild_id: guildId, word: 'token', exact: 1 },
      { guild_id: guildId, word: 'both', exact: 0 },
      { guild_id: guildId, word: 'both', exact: 1 },
    ],
  }), null, 2));

  await db.initializeDatabase();
  const words = await db.getBannedWords(guildId);
  assert.equal(words.length, 4);
  assert.equal(words.filter((w) => w.match_mode === 'contains').length, 2);
  assert.equal(words.filter((w) => w.match_mode === 'exact').length, 2);
  assert.ok(words.some((w) => w.value === 'both' && w.match_mode === 'contains'));
  assert.ok(words.some((w) => w.value === 'both' && w.match_mode === 'exact'));

  await db.initializeDatabase();
  const again = await db.getBannedWords(guildId);
  assert.equal(again.length, 4);
  console.log('legacy migration preserves modes: PASS');
});

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await import('../src/database/db.js');
  db.configureDatabase({ path: dbPath, hooks: {} });

  const guildId = 'guild-new-format';
  await writeFile(dbPath, JSON.stringify(emptyStore({
    banned_words: [
      { id: 1, guild_id: guildId, value: 'kept', match_mode: 'exact', created_at: 1, created_by: 'mod-1' },
    ],
    _banned_words_migrated: true,
    automod_words: [{ guild_id: guildId, word: 'legacy', exact: 0 }],
  }), null, 2));

  await db.initializeDatabase();
  const words = await db.getBannedWords(guildId);
  assert.equal(words.length, 1);
  assert.equal(words[0].value, 'kept');
  assert.equal(words[0].match_mode, 'exact');
  console.log('explicit new-format records not overwritten: PASS');
});

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await import('../src/database/db.js');
  db.configureDatabase({ path: dbPath, hooks: {} });
  await db.initializeDatabase();

  const guildId = 'guild-dup';
  await db.addBannedWord(guildId, 'spam', 'contains', 'mod-1');
  let threw = false;
  try {
    await db.addBannedWord(guildId, 'spam', 'contains', 'mod-1');
  } catch (err) {
    threw = err.message === 'duplicate_banned_word';
  }
  assert.equal(threw, true);

  const secondId = await db.addBannedWord(guildId, 'spam', 'exact', 'mod-1');
  const words = await db.getBannedWords(guildId);
  assert.equal(words.length, 2);
  assert.ok(words.some((w) => w.id === secondId && w.match_mode === 'exact'));
  console.log('duplicate handling: PASS');
});

const guildId = 'match-guild';
const containsEntry = entry(1, guildId, 'bad', 'contains');
const exactEntry = entry(2, guildId, 'bad', 'exact');

assert.equal(findBannedWordMatch('this is bad stuff', [containsEntry, exactEntry])?.match_mode, 'contains');
assert.equal(findBannedWordMatch('this is bad stuff', [exactEntry, containsEntry])?.match_mode, 'exact');
assert.equal(findBannedWordMatch('bad', [exactEntry, containsEntry])?.match_mode, 'exact');
assert.equal(findBannedWordMatch('xxbadxx', [containsEntry])?.value, 'bad');
assert.equal(findBannedWordMatch('xxbadxx', [exactEntry]), null);
assert.equal(findBannedWordMatch('BAD WORD', [containsEntry])?.value, 'bad');
assert.equal(findBannedWordMatch('word, bad!', [exactEntry])?.match_mode, 'exact');
assert.equal(findBannedWordMatch('wordbad', [exactEntry]), null);
assert.equal(findBannedWordMatch('first bad then worse', [entry(3, guildId, 'bad', 'contains'), entry(4, guildId, 'worse', 'contains')])?.value, 'bad');
assert.equal(formatBannedWordReason({ value: 'bad', match_mode: 'exact' }), 'Banned word (exact): bad');
console.log('matching behavior: PASS');

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await import('../src/database/db.js');
  db.configureDatabase({ path: dbPath, hooks: {} });
  await db.initializeDatabase();

  const guildId = 'guild-list';
  const id1 = await db.addBannedWord(guildId, 'alpha', 'contains', 'mod');
  const id2 = await db.addBannedWord(guildId, 'beta', 'exact', 'mod');
  const words = await db.getBannedWords(guildId);
  assert.equal(words.length, 2);
  assert.ok(words.every((w) => Number.isInteger(w.id)));
  assert.ok(words.some((w) => w.id === id1 && w.match_mode === 'contains'));
  assert.ok(words.some((w) => w.id === id2 && w.match_mode === 'exact'));
  console.log('unified list data: PASS');
});

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await import('../src/database/db.js');
  db.configureDatabase({ path: dbPath, hooks: {} });
  await db.initializeDatabase();

  const guildId = 'guild-remove';
  const containsId = await db.addBannedWord(guildId, 'dual', 'contains', 'mod');
  await db.addBannedWord(guildId, 'dual', 'exact', 'mod');

  const removed = await db.removeBannedWord(guildId, containsId);
  assert.equal(removed.removed, 1);
  const remaining = await db.getBannedWords(guildId);
  assert.equal(remaining.length, 1);
  assert.equal(remaining[0].match_mode, 'exact');

  const missing = await db.removeBannedWord(guildId, 9999);
  assert.equal(missing.removed, 0);
  console.log('removal by ID: PASS');
});

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await import('../src/database/db.js');
  db.configureDatabase({ path: dbPath, hooks: {} });
  await db.initializeDatabase();

  const guildId = '123456789012345678';
  await db.addBannedWord(guildId, 'aliasword', 'contains', 'mod');

  const { handleAutomod } = await import('../src/handlers/automodHandler.js');
  let deleted = false;
  const msg = {
    guild: { id: guildId },
    author: { id: 'user-1', bot: false },
    content: 'contains aliasword here',
    member: {
      id: 'user-1',
      guild: { id: guildId },
      permissions: { has: () => false },
      roles: { cache: { some: () => false } },
    },
    channel: {
      id: 'channel-1',
      send: async () => ({ delete: async () => {} }),
    },
    mentions: { users: { size: 0 }, roles: { size: 0 }, everyone: false },
    delete: async () => { deleted = true; },
  };

  assert.equal(await handleAutomod(msg), true);
  assert.equal(deleted, true);
  const data = await db.readDatabase();
  assert.equal(data.automod_words.length, 0);
  console.log('runtime uses banned_words only: PASS');
});

assert.equal(matchBannedWordEntry('test', { value: '', match_mode: 'contains' }), null);
assert.equal(matchBannedWordEntry('test', { value: 'ok', match_mode: 'invalid' }), null);
console.log('malformed entry handling: PASS');

console.log('All banned-word consolidation tests passed');
