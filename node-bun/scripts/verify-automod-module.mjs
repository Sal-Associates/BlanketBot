import assert from 'node:assert/strict';
import { readFile, writeFile, mkdtemp, rm } from 'fs/promises';
import { join } from 'path';
import { tmpdir } from 'os';

process.env.GUILD_ID = process.env.GUILD_ID || '123456789012345678';
process.env.SUPERUSER_IDS = '';

async function withTempDatabase(run) {
  const dir = await mkdtemp(join(tmpdir(), 'modbot-automod-'));
  const dbPath = join(dir, 'store.json');
  try {
    await run(dbPath);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

function emptyStore(guildSettings = {}) {
  return {
    guild_settings: guildSettings,
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
  };
}

function createMockMessage({ guildId, channelId, userId, content }) {
  let deleted = false;
  let warningSent = false;

  return {
    guild: { id: guildId },
    author: { id: userId, bot: false },
    content,
    member: {
      id: userId,
      guild: { id: guildId },
      permissions: { has: () => false },
      roles: { cache: { some: () => false } },
    },
    channel: {
      id: channelId,
      send: async () => {
        warningSent = true;
        return { delete: async () => {} };
      },
    },
    mentions: { users: { size: 0 }, roles: { size: 0 }, everyone: false },
    delete: async () => { deleted = true; },
    wasDeleted: () => deleted,
    warningSent: () => warningSent,
  };
}

async function masterStatusFromSources(db, guildId) {
  const moduleDisabled = await db.isModuleDisabled(guildId, 'Automod');
  const settings = await db.getGuildSettings(guildId);
  const disabled = JSON.parse(settings.disabled_modules || '[]');
  const modulesStatus = disabled.includes('Automod') ? 'disabled' : 'enabled';
  const automodStatus = moduleDisabled ? 'disabled' : 'enabled';
  return { modulesStatus, automodStatus };
}

console.log('Running Automod module master-switch tests...');

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await import('../src/database/db.js');
  db.configureDatabase({ path: dbPath, hooks: {} });
  await db.initializeDatabase();

  const guildId = '123456789012345678';
  const channelId = 'channel-1';
  const userId = 'user-1';

  await db.addBannedWord(guildId, 'badword', 'contains', 'mod-1');
  await db.updateGuildSetting(guildId, 'anti_spam', 1);
  await db.toggleModule(guildId, 'Automod');

  const { handleAutomod } = await import('../src/handlers/automodHandler.js');
  const blocked = createMockMessage({ guildId, channelId, userId, content: 'contains badword here' });
  const acted = await handleAutomod(blocked);

  assert.equal(acted, false);
  assert.equal(blocked.wasDeleted(), false);
  assert.equal(blocked.warningSent(), false);
  const queue = await db.readDatabase();
  assert.equal(queue.mod_queue.length, 0);
  console.log('module disabled blocks automod: PASS');

  await db.toggleModule(guildId, 'Automod');
  const active = createMockMessage({ guildId, channelId, userId, content: 'contains badword here' });
  const actedOn = await handleAutomod(active);

  assert.equal(actedOn, true);
  assert.equal(active.wasDeleted(), true);
  console.log('module enabled enforces automod: PASS');
});

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await import('../src/database/db.js');
  db.configureDatabase({ path: dbPath, hooks: {} });

  const guildId = 'legacy-enabled';
  await writeFile(dbPath, JSON.stringify(emptyStore({
    [guildId]: { guild_id: guildId, automod_enabled: 1, disabled_modules: '[]' },
  }), null, 2));

  await db.initializeDatabase();
  const settings = await db.getGuildSettings(guildId);
  assert.equal(await db.isModuleDisabled(guildId, 'Automod'), false);
  assert.equal(JSON.parse(settings.disabled_modules).includes('Automod'), false);
  assert.equal(settings._automod_module_migrated, 1);

  const persisted = JSON.parse(await readFile(dbPath, 'utf8'));
  assert.equal(persisted.guild_settings[guildId]._automod_module_migrated, 1);

  await db.addBannedWord(guildId, 'legacybad', 'contains', 'mod-1');
  const { handleAutomod } = await import('../src/handlers/automodHandler.js');
  const msg = createMockMessage({ guildId, channelId: 'c1', userId: 'u1', content: 'legacybad word' });
  assert.equal(await handleAutomod(msg), true);
  assert.equal(msg.wasDeleted(), true);
  console.log('legacy automod_enabled:1 migration: PASS');
});

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await import('../src/database/db.js');
  db.configureDatabase({ path: dbPath, hooks: {} });

  const guildId = 'legacy-disabled';
  await writeFile(dbPath, JSON.stringify(emptyStore({
    [guildId]: { guild_id: guildId, automod_enabled: 0, disabled_modules: '[]' },
  }), null, 2));

  await db.initializeDatabase();
  assert.equal(await db.isModuleDisabled(guildId, 'Automod'), true);

  await db.addBannedWord(guildId, 'legacybad', 'contains', 'mod-1');
  const { handleAutomod } = await import('../src/handlers/automodHandler.js');
  const msg = createMockMessage({ guildId, channelId: 'c1', userId: 'u1', content: 'legacybad word' });
  assert.equal(await handleAutomod(msg), false);
  assert.equal(msg.wasDeleted(), false);
  console.log('legacy automod_enabled:0 migration: PASS');
});

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await import('../src/database/db.js');
  db.configureDatabase({ path: dbPath, hooks: {} });

  const guildId = 'explicit-module-wins';
  await writeFile(dbPath, JSON.stringify(emptyStore({
    [guildId]: {
      guild_id: guildId,
      automod_enabled: 0,
      disabled_modules: '["Automod"]',
      _automod_module_migrated: 1,
    },
  }), null, 2));

  await db.initializeDatabase();
  assert.equal(await db.isModuleDisabled(guildId, 'Automod'), true);

  await db.toggleModule(guildId, 'Automod');
  assert.equal(await db.isModuleDisabled(guildId, 'Automod'), false);

  await db.toggleModule(guildId, 'Automod');
  assert.equal(await db.isModuleDisabled(guildId, 'Automod'), true);
  console.log('explicit module state wins over legacy setting: PASS');
});

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await import('../src/database/db.js');
  db.configureDatabase({ path: dbPath, hooks: {} });
  await db.initializeDatabase();

  const guildId = '123456789012345678';
  const before = await masterStatusFromSources(db, guildId);
  assert.equal(before.modulesStatus, before.automodStatus);

  await db.toggleModule(guildId, 'Automod');
  const afterDisable = await masterStatusFromSources(db, guildId);
  assert.equal(afterDisable.modulesStatus, 'disabled');
  assert.equal(afterDisable.automodStatus, 'disabled');

  await db.toggleModule(guildId, 'Automod');
  const afterEnable = await masterStatusFromSources(db, guildId);
  assert.equal(afterEnable.modulesStatus, 'enabled');
  assert.equal(afterEnable.automodStatus, 'enabled');
  console.log('status consistency across module sources: PASS');
});

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await import('../src/database/db.js');
  db.configureDatabase({ path: dbPath, hooks: {} });
  await db.initializeDatabase();
  const settings = await db.getGuildSettings('new-guild');
  assert.equal('automod_enabled' in settings, false);
  console.log('default settings omit automod_enabled: PASS');
});

const srcRoot = join(import.meta.dirname, '../src');
async function grepSrc(pattern) {
  const { readdir } = await import('fs/promises');
  const hits = [];
  async function walk(dir) {
    for (const entry of await readdir(dir, { withFileTypes: true })) {
      const full = join(dir, entry.name);
      if (entry.isDirectory()) await walk(full);
      else if (entry.name.endsWith('.js') && (await readFile(full, 'utf8')).includes(pattern)) {
        hits.push(full);
      }
    }
  }
  await walk(srcRoot);
  return hits;
}

const hits = await grepSrc('automod_enabled');
const runtimeHits = hits.filter((file) => !file.replace(/\\/g, '/').endsWith('src/database/db.js'));
assert.equal(runtimeHits.length, 0, `automod_enabled still referenced in: ${runtimeHits.join(', ')}`);
console.log('runtime automod_enabled removal: PASS');

console.log('All Automod module master-switch tests passed');
