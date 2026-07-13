import assert from 'node:assert/strict';
import { writeFile, readFile, mkdtemp, rm } from 'fs/promises';
import { join } from 'path';
import { tmpdir } from 'os';

process.env.GUILD_ID = process.env.GUILD_ID || '123456789012345678';

async function withTempDatabase(run) {
  const dir = await mkdtemp(join(tmpdir(), 'modbot-cases-'));
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

console.log('Running case consolidation tests...');

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await import('../src/database/db.js');
  db.configureDatabase({ path: dbPath, hooks: {} });
  await db.initializeDatabase();

  const guildId = 'guild-1';
  await db.createCase(guildId, 'user-1', 'mod-1', 'kick', 'test kick', { source: 'moderation' });
  const data = await db.readDatabase();
  assert.equal(data.cases.length, 1);
  assert.equal(data.mod_logs.length, 0);
  console.log('single persistent record: PASS');
});

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await import('../src/database/db.js');
  db.configureDatabase({ path: dbPath, hooks: {} });

  const legacyLog = {
    id: 1,
    guild_id: 'legacy-guild',
    user_id: 'user-old',
    moderator_id: 'mod-old',
    action: 'warn',
    reason: 'legacy entry',
    case_number: 1,
    created_at: 1,
  };

  await writeFile(dbPath, JSON.stringify(emptyStore({
    guild_settings: { 'legacy-guild': { guild_id: 'legacy-guild', prefix: '?' } },
    mod_logs: [legacyLog],
    _counters: { warnings: 0, notes: 0, mod_logs: 1, timed_actions: 0, mod_queue: 0 },
  }), null, 2));

  await db.initializeDatabase();
  const before = await db.readDatabase();
  assert.equal(before.mod_logs.length, 1);
  assert.equal(before.mod_logs[0].reason, 'legacy entry');

  await db.createCase('legacy-guild', 'user-new', 'mod-new', 'mute', 'new case');
  const after = await db.readDatabase();
  assert.equal(after.mod_logs.length, 1);
  assert.equal(after.mod_logs[0].reason, 'legacy entry');
  assert.equal(after.cases.length, 1);
  console.log('legacy mod_logs compatibility: PASS');
});

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await import('../src/database/db.js');
  db.configureDatabase({ path: dbPath, hooks: {} });
  await db.initializeDatabase();

  const guildId = 'guild-fields';
  const modId = 'mod-1';
  const userId = 'user-1';

  const warn = await db.createWarningWithCase({
    guildId,
    userId,
    moderatorId: modId,
    reason: 'warn reason',
    source: 'warn_command',
  });
  const warnCase = await db.getCase(guildId, warn.caseNumber);
  assert.equal(warnCase.extra.warning_id, warn.warningId);
  assert.equal(warnCase.extra.source, 'warn_command');

  const endsAt = Date.now() + 3600_000;
  const tempBan = await db.createTemporaryPunishmentRecords({
    guildId,
    userId,
    moderatorId: modId,
    caseAction: 'ban',
    caseReason: 'temp ban',
    timedAction: 'unban',
    endsAt,
  });
  const banCase = await db.getCase(guildId, tempBan.caseNumber);
  assert.equal(banCase.extra.ends_at, endsAt);
  assert.equal(banCase.extra.timed_action, 'unban');
  assert.equal(banCase.extra.timed_action_id, tempBan.timedActionId);
  assert.equal(banCase.extra.source, 'moderation');

  const tempMute = await db.createTemporaryPunishmentRecords({
    guildId,
    userId,
    moderatorId: modId,
    caseAction: 'mute',
    caseReason: 'temp mute',
    timedAction: 'unmute',
    endsAt,
  });
  const muteCase = await db.getCase(guildId, tempMute.caseNumber);
  assert.equal(muteCase.extra.timed_action, 'unmute');

  const strikeFail = await db.createCase(guildId, userId, modId, 'strike_ban_failed', 'bot cannot act', {
    source: 'strike',
    status: 'failed',
  });
  const failCase = await db.getCase(guildId, strikeFail);
  assert.equal(failCase.extra.status, 'failed');
  assert.equal(failCase.extra.source, 'strike');
  console.log('case completeness fields: PASS');
});

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await import('../src/database/db.js');
  db.configureDatabase({ path: dbPath, hooks: {} });
  await db.initializeDatabase();
  await db.updateGuildSetting('guild-notify', 'mod_log_channel', 'channel-1');

  const { sendModLog } = await import('../src/utils/modLog.js');
  const caseNum = await db.createCase('guild-notify', 'user-1', 'mod-1', 'kick', 'notify test', {
    source: 'moderation',
  });
  const before = await db.readDatabase();
  assert.equal(before.cases.length, 1);

  const guild = {
    id: 'guild-notify',
    channels: {
      cache: new Map([
        ['channel-1', { send: async () => { throw new Error('send failed'); } }],
      ]),
    },
  };

  const notified = await sendModLog(guild, {
    action: 'kick',
    target: { id: 'user-1', toString: () => '<@user-1>' },
    moderator: { id: 'mod-1', toString: () => '<@mod-1>' },
    reason: 'notify test',
    caseNumber: caseNum,
  });

  assert.equal(notified, false);
  const after = await db.readDatabase();
  assert.equal(after.cases.length, 1);
  assert.equal(after.cases[0].case_number, caseNum);
  assert.equal(after.mod_logs.length, 0);
  console.log('notification failure preserves case: PASS');
});

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await import('../src/database/db.js');
  db.configureDatabase({ path: dbPath, hooks: { failNextMutations: 1 } });
  await db.initializeDatabase();

  let threw = false;
  try {
    await db.createCase('guild-fail', 'user-1', 'mod-1', 'kick', 'should fail');
  } catch {
    threw = true;
  }
  assert.equal(threw, true);
  const data = await db.readDatabase();
  assert.equal(data.cases.length, 0);
  assert.equal(data.mod_logs.length, 0);
  console.log('persistence failure creates no records: PASS');
});

const dbSrc = await readFile(join(import.meta.dirname, '../src/database/db.js'), 'utf8');
assert.equal(dbSrc.includes('data.mod_logs.push'), false, 'createCaseInData must not write mod_logs');
console.log('no mod_logs writes in source: PASS');

console.log('All case consolidation tests passed');
