import assert from 'node:assert/strict';
import { readFile, writeFile, mkdtemp, rm } from 'fs/promises';
import { join } from 'path';
import { tmpdir } from 'os';
import { existsSync } from 'fs';

async function importDbFresh() {
  return import(`../src/database/db.js?ts=${Date.now()}`);
}

async function withTempDatabase(run) {
  const dir = await mkdtemp(join(tmpdir(), 'modbot-cleanup-'));
  const dbPath = join(dir, 'store.json');
  try {
    await run(dbPath);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

console.log('Running dead-code cleanup verification...');

// Default guild settings omit anti_duplicate
await withTempDatabase(async (dbPath) => {
  const db = await importDbFresh();
  db.configureDatabase({ path: dbPath });
  await db.initializeDatabase();
  const settings = await db.getGuildSettings('fresh-guild');
  assert.equal('anti_duplicate' in settings, false, 'new guild settings should not include anti_duplicate');
  console.log('anti_duplicate default omission: PASS');
});

// Legacy databases with anti_duplicate still load
await withTempDatabase(async (dbPath) => {
  const db = await importDbFresh();
  db.configureDatabase({ path: dbPath });
  await writeFile(dbPath, JSON.stringify({
    guild_settings: { 'legacy-guild': { guild_id: 'legacy-guild', prefix: '?', anti_duplicate: 1 } },
    mod_roles: [], admin_roles: [], warnings: [], notes: [], mod_logs: [],
    automod_words: [], banned_words: [], automod_ignored_channels: [], automod_ignored_roles: [],
    timed_actions: [], cases: [], mod_queue: [], case_counters: {},
    _counters: { warnings: 0, notes: 0, mod_logs: 0, timed_actions: 0, mod_queue: 0, banned_words: 0 },
  }, null, 2));
  await db.initializeDatabase();
  const settings = await db.getGuildSettings('legacy-guild');
  assert.equal(settings.anti_duplicate, 1, 'legacy anti_duplicate key should be preserved on load');
  console.log('legacy anti_duplicate tolerance: PASS');
});

// Purge parser no longer advertises or accepts after
const purgeSource = await readFile(join(import.meta.dirname, '../src/commands/purge/purge.js'), 'utf8');
assert.match(purgeSource, /const PURGE_FILTERS = \[[^\]]+\];/);
const filtersMatch = purgeSource.match(/const PURGE_FILTERS = (\[[^\]]+\]);/);
assert(filtersMatch, 'PURGE_FILTERS declaration not found');
assert.equal(filtersMatch[1].includes("'after'"), false, 'PURGE_FILTERS must not include after');
assert.equal(purgeSource.includes('after'), false, 'purge help must not mention after filter');
assert.match(purgeSource, /case 'user':/);
console.log('purge after filter removal: PASS');

// Runtime does not reference CLIENT_ID or DEFAULT_PREFIX
const srcRoot = join(import.meta.dirname, '../src');
async function grepSrcFiles(pattern) {
  const { readdir } = await import('fs/promises');
  const hits = [];
  async function walk(dir) {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) await walk(full);
      else if (entry.name.endsWith('.js')) {
        const text = await readFile(full, 'utf8');
        if (text.includes(pattern)) hits.push(full);
      }
    }
  }
  await walk(srcRoot);
  return hits;
}

const clientIdHits = await grepSrcFiles('CLIENT_ID');
const prefixHits = await grepSrcFiles('DEFAULT_PREFIX');
assert.equal(clientIdHits.length, 0, `CLIENT_ID referenced in: ${clientIdHits.join(', ')}`);
assert.equal(prefixHits.length, 0, `DEFAULT_PREFIX referenced in: ${prefixHits.join(', ')}`);
console.log('unused env var references: PASS');

// Client intents: GuildMessageReactions removed; required intents remain
const indexSource = await readFile(join(srcRoot, 'index.js'), 'utf8');
assert.equal(indexSource.includes('GuildMessageReactions'), false);
assert.equal(indexSource.includes('Partials'), false);
for (const intent of ['Guilds', 'GuildMessages', 'GuildMembers', 'MessageContent']) {
  assert.match(indexSource, new RegExp(`GatewayIntentBits\\.${intent}`));
}
console.log('gateway intent configuration: PASS');

// Removed exports have zero remaining references
const db = await importDbFresh();
assert.equal(db.addModLog, undefined);
assert.equal(db.getModLogs, undefined);
assert.equal(db.updateModQueueStatus, undefined);

const checks = await import(`../src/utils/checks.js?ts=${Date.now()}`);
assert.equal(checks.checkModule, undefined);

const perms = await import(`../src/utils/permissions.js?ts=${Date.now()}`);
assert.equal(perms.MOD_PERMS, undefined);
assert.equal(perms.ADMIN_PERMS, undefined);

const retry = await import(`../src/utils/timedActionRetry.js?ts=${Date.now()}`);
assert.equal(retry.isDiscordRateLimitError, undefined);
assert.equal(retry.isDiscordMissingPermissionsError, undefined);

for (const symbol of ['addModLog', 'getModLogs', 'updateModQueueStatus', 'checkModule', 'MOD_PERMS', 'ADMIN_PERMS', 'isDiscordRateLimitError', 'isDiscordMissingPermissionsError']) {
  const hits = [];
  async function walk(dir) {
    for (const entry of await import('fs/promises').then((m) => m.readdir(dir, { withFileTypes: true }))) {
      const full = join(dir, entry.name);
      if (entry.isDirectory() && entry.name !== 'node_modules') await walk(full);
      else if (entry.name.endsWith('.js') || entry.name.endsWith('.mjs')) {
        const text = await readFile(full, 'utf8');
        if (text.includes(symbol)) hits.push(full);
      }
    }
  }
  await walk(join(import.meta.dirname, '..'));
  const filtered = hits.filter((h) => !h.includes('node_modules') && !h.includes('verify-cleanup.mjs') && !h.includes('FEATURE_INVENTORY') && !h.includes('SIMPLIFICATION_REVIEW'));
  assert.equal(filtered.length, 0, `${symbol} still referenced in: ${filtered.join(', ')}`);
}
console.log('removed export references: PASS');

// Retained DB API for ignored channel/role removal
assert.equal(typeof db.removeIgnoredChannel, 'function');
assert.equal(typeof db.removeIgnoredRole, 'function');
console.log('retained removeIgnored* exports: PASS');

console.log('All dead-code cleanup verification passed');
