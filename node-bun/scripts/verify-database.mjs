import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, writeFile, rename, readdir } from 'fs/promises';
import { existsSync } from 'fs';
import { join } from 'path';
import { tmpdir } from 'os';

async function withTempDatabase(run) {
  const dir = await mkdtemp(join(tmpdir(), 'modbot-db-'));
  const dbPath = join(dir, 'store.json');
  try {
    await run(dbPath, dir);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

async function importDbFresh() {
  return import(`../src/database/db.js?ts=${Date.now()}`);
}

function findCorruptCopy(dir) {
  return readdir(dir).then((files) => files.find((f) => f.startsWith('store.json.corrupt-')));
}

console.log('Running database hardening tests...');

await withTempDatabase(async (dbPath, dir) => {
  const db = await importDbFresh();
  db.configureDatabase({ path: dbPath });

  assert.equal(existsSync(dbPath), false);
  await db.initializeDatabase();
  assert.equal(existsSync(dbPath), true);
  JSON.parse(await readFile(dbPath, 'utf8'));
  console.log('missing file test: PASS');

  await db.updateGuildSetting('guild-1', 'prefix', '!');
  const settings = await db.getGuildSettings('guild-1');
  assert.equal(settings.prefix, '!');
  console.log('first-time guild settings: PASS');

  await writeFile(dbPath, JSON.stringify({
    guild_settings: { 'legacy-guild': { guild_id: 'legacy-guild', prefix: 'x' } },
    mod_roles: [], admin_roles: [], warnings: [], notes: [], mod_logs: [],
    automod_words: [], banned_words: [], automod_links: [], automod_ignored_channels: [], automod_ignored_roles: [],
    timed_actions: [], cases: [], mod_queue: [], case_counters: {},
    _counters: { warnings: 0, notes: 0, mod_logs: 0, timed_actions: 0, mod_queue: 0, banned_words: 0 },
  }, null, 2));
  const legacy = await db.getGuildSettings('legacy-guild');
  assert.equal(legacy.prefix, 'x');
  assert.equal(legacy.strike_enabled, 1);
  console.log('legacy guild default backfill: PASS');

  await Promise.all(Array.from({ length: 50 }, (_, i) =>
    db.mutateDatabase((data) => {
      data.mod_roles.push({ guild_id: 'g', role_id: `role-${i}` });
    })
  ));
  const data = await db.readDatabase();
  assert.equal(data.mod_roles.length, 50);
  JSON.parse(await readFile(dbPath, 'utf8'));
  console.log('concurrent update test: PASS');

  const warnIds = await Promise.all(Array.from({ length: 50 }, (_, i) =>
    db.addWarning('g', `user-${i}`, 'mod', 'reason')
  ));
  assert.equal(new Set(warnIds).size, 50);
  console.log('concurrent ID test: PASS');

  for (let i = 0; i < 20; i++) {
    await db.updateGuildSetting('g', 'prefix', `?${i}`);
    JSON.parse(await readFile(dbPath, 'utf8'));
  }
  assert.ok(existsSync(`${dbPath}.bak`));
  console.log('atomic-write valid JSON test: PASS');

  const before = await readFile(dbPath, 'utf8');
  const beforeParsed = JSON.parse(before);
  let renameAttempts = 0;
  const db2 = await importDbFresh();
  db2.configureDatabase({
    path: dbPath,
    hooks: {
      rename: async (from, to) => {
        renameAttempts++;
        if (renameAttempts === 1 && to === dbPath) {
          throw new Error('simulated rename failure');
        }
        return rename(from, to);
      },
    },
  });
  let saveFailed = false;
  try {
    await db2.updateGuildSetting('g', 'prefix', '?fail');
  } catch {
    saveFailed = true;
  }
  assert.equal(saveFailed, true);
  assert.equal(await readFile(dbPath, 'utf8'), before);
  assert.deepEqual(JSON.parse(await readFile(dbPath, 'utf8')), beforeParsed);
  console.log('atomic-write failure preserves main file: PASS');

  await writeFile(dbPath, '{not-json');
  let rejected = false;
  try {
    await db.initializeDatabase();
  } catch (err) {
    rejected = err.name === 'DatabaseFatalError';
    assert.match(err.message, /Invalid JSON/);
  }
  assert.equal(rejected, true);
  assert.equal(await readFile(dbPath, 'utf8'), '{not-json');
  assert.ok(await findCorruptCopy(dir));
  console.log('invalid JSON test: PASS');

  await writeFile(dbPath, before);
  await db.initializeDatabase();
});

await import('./verify-regex.mjs');
await import('./verify-moderation.mjs');

console.log('All database and regression tests passed');
