await import('./verify-cleanup.mjs');
await import('./verify-automod-module.mjs');
await import('./verify-automod-ignore.mjs');
await import('./verify-automod-thresholds.mjs');
await import('./verify-cases-consolidation.mjs');
await import('./verify-banned-words.mjs');
await import('./verify-lockdown.mjs');

import assert from 'node:assert/strict';

process.env.GUILD_ID = process.env.GUILD_ID || '123456789012345678';
process.env.SUPERUSER_IDS = process.env.SUPERUSER_IDS || 'super';

import { mkdtemp, rm } from 'fs/promises';
import { join } from 'path';
import { tmpdir } from 'os';
import {
  rollbackTemporaryBan,
  rollbackTemporaryMute,
  persistenceRollbackMessage,
  persistenceLoggingFailureMessage,
} from '../src/utils/moderationCompensation.js';

async function withTempDatabase(run) {
  const dir = await mkdtemp(join(tmpdir(), 'modbot-workflow-'));
  const dbPath = join(dir, 'store.json');
  try {
    await run(dbPath);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

console.log('Running moderation workflow tests...');

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await import('../src/database/db.js');
  db.configureDatabase({ path: dbPath, hooks: {} });
  await db.initializeDatabase();

  const guildId = '123456789012345678';
  const userId = 'user-1';
  const modId = 'mod-1';

  db.configureDatabase({ hooks: { failNextMutations: 1 } });
  let threw = false;
  try {
    await db.createWarningWithCase({
      guildId,
      userId,
      moderatorId: modId,
      reason: 'test',
      source: 'test',
    });
  } catch {
    threw = true;
  }
  assert.equal(threw, true);
  const afterFail = await db.readDatabase();
  assert.equal(afterFail.warnings.length, 0);
  assert.equal(afterFail.cases.length, 0);
  console.log('warning transaction failure: PASS');

  db.configureDatabase({ hooks: { failNextMutations: 0 } });
  const warnResult = await db.createWarningWithCase({
    guildId,
    userId,
    moderatorId: modId,
    reason: 'warn1',
    source: 'test',
  });
  assert.ok(warnResult.warningId);
  assert.ok(warnResult.caseNumber);
  console.log('warning transaction success: PASS');

  const entry = await db.addModQueueEntry(guildId, 'ch-1', userId, 'content', 'spam');
  const [denyResult, approveResult] = await Promise.all([
    db.processModQueueDecision({
      entryId: entry.id,
      moderatorId: 'mod-a',
      decision: 'deny',
      warnReason: 'Automod: spam',
      caseAction: 'queue_deny',
      caseReason: 'Automod violation: spam',
    }),
    db.processModQueueDecision({
      entryId: entry.id,
      moderatorId: 'mod-b',
      decision: 'approve',
      caseAction: 'queue_approve',
      caseReason: 'False positive',
    }),
  ]);

  const outcomes = [denyResult.status, approveResult.status];
  assert.equal(outcomes.filter((s) => s === 'success').length, 1);
  assert.equal(outcomes.filter((s) => s === 'already_processed').length, 1);

  const data = await db.readDatabase();
  const queueEntry = data.mod_queue.find((q) => q.id === entry.id);
  assert.notEqual(queueEntry.status, 'pending');
  const warnCases = data.warnings.filter((w) => w.source === 'mod_queue');
  const queueCases = data.cases.filter((c) => c.action === 'queue_deny' || c.action === 'queue_approve');
  assert.equal(warnCases.length <= 1, true);
  assert.equal(queueCases.length, 1);
  console.log('concurrent queue decision: PASS');

  const tempBan = await db.createTemporaryPunishmentRecords({
    guildId,
    userId: 'user-ban',
    moderatorId: modId,
    caseAction: 'ban',
    caseReason: 'temp',
    timedAction: 'unban',
    endsAt: Date.now() + 60_000,
  });
  assert.ok(tempBan.caseNumber);
  assert.ok(tempBan.timedActionId);
  const banData = await db.readDatabase();
  assert.equal(banData.cases.filter((c) => c.action === 'ban').length, 1);
  assert.equal(banData.timed_actions.filter((a) => a.action === 'unban').length, 1);
  console.log('temporary punishment success: PASS');

  db.configureDatabase({ hooks: { failNextMutations: 1 } });
  const mockGuild = {
    members: {
      unban: async () => {},
    },
  };
  const mockTarget = {
    roles: {
      remove: async () => {},
      cache: { has: () => true },
    },
  };
  const mockMuteRole = { id: 'mute' };

  let muteRollbackCalled = false;
  mockTarget.roles.remove = async () => { muteRollbackCalled = true; };

  threw = false;
  try {
    await db.createTemporaryPunishmentRecords({
      guildId,
      userId: 'user-mute-fail',
      moderatorId: modId,
      caseAction: 'mute',
      caseReason: 'temp',
      timedAction: 'unmute',
      endsAt: Date.now() + 60_000,
    });
  } catch {
    threw = true;
  }
  assert.equal(threw, true);
  const rollback = await rollbackTemporaryMute(mockTarget, mockMuteRole);
  assert.equal(rollback.success, true);
  assert.equal(muteRollbackCalled, true);
  assert.match(persistenceRollbackMessage('mute', rollback), /reversed/);
  console.log('temporary mute persistence failure with rollback success: PASS');

  mockTarget.roles.remove = async () => { throw new Error('rollback failed'); };
  const rollbackFail = await rollbackTemporaryMute(mockTarget, mockMuteRole);
  assert.equal(rollbackFail.success, false);
  assert.match(persistenceRollbackMessage('mute', rollbackFail), /manual intervention/i);
  console.log('temporary mute rollback failure message: PASS');

  let banRollbackCalled = false;
  mockGuild.members.unban = async () => { banRollbackCalled = true; };
  db.configureDatabase({ hooks: { failNextMutations: 1 } });
  threw = false;
  try {
    await db.createTemporaryPunishmentRecords({
      guildId,
      userId: 'user-ban-fail',
      moderatorId: modId,
      caseAction: 'ban',
      caseReason: 'temp',
      timedAction: 'unban',
      endsAt: Date.now() + 60_000,
    });
  } catch {
    threw = true;
  }
  assert.equal(threw, true);
  const banRollback = await rollbackTemporaryBan(mockGuild, 'user-ban-fail');
  assert.equal(banRollback.success, true);
  assert.equal(banRollbackCalled, true);
  console.log('temporary ban persistence failure with rollback success: PASS');

  assert.match(persistenceLoggingFailureMessage('kicked'), /record could not be saved/i);
  console.log('permanent action logging failure message: PASS');

  db.configureDatabase({ hooks: { failNextMutations: 0 } });
});

await import('./verify-timed-channel.mjs');

console.log('All moderation workflow and regression tests passed');
