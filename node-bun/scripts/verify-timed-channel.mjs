import assert from 'node:assert/strict';

process.env.GUILD_ID = process.env.GUILD_ID || '123456789012345678';
process.env.SUPERUSER_IDS = process.env.SUPERUSER_IDS || 'super';

import { mkdtemp, rm } from 'fs/promises';
import { join } from 'path';
import { tmpdir } from 'os';
import { PermissionFlagsBits } from 'discord.js';
import {
  getPermissionState,
  applyPermissionState,
  channelPermissionMatches,
  permissionStateToOverwriteValue,
} from '../src/utils/channelPermissions.js';
import { restoreChannelFromTimedAction } from '../src/utils/channelTimedUnlock.js';
import { MAX_CHANNEL_UNLOCK_ATTEMPTS, getRetryDelayMs } from '../src/utils/timedActionRetry.js';

async function withTempDatabase(run) {
  const dir = await mkdtemp(join(tmpdir(), 'modbot-timed-'));
  const dbPath = join(dir, 'store.json');
  try {
    await run(dbPath, dir);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

async function importDbFresh() {
  return import('../src/database/db.js');
}

function mockOverwrite(state, permission = 'SendMessages') {
  const bit = PermissionFlagsBits[permission];
  let allowBits = 0n;
  let denyBits = 0n;
  if (state === 'allow') allowBits = bit;
  if (state === 'deny') denyBits = bit;
  return {
    allow: { has: (b) => (allowBits & b) === b },
    deny: { has: (b) => (denyBits & b) === b },
  };
}

function createMockChannel(roleId, initialState, { failEdits = 0 } = {}) {
  const permission = 'SendMessages';
  const bit = PermissionFlagsBits.SendMessages;
  let allowBits = 0n;
  let denyBits = 0n;
  if (initialState === 'allow') allowBits = bit;
  if (initialState === 'deny') denyBits = bit;
  let remainingFailures = failEdits;

  const overwrites = new Map();
  const refresh = () => {
    overwrites.set(roleId, {
      allow: { has: (b) => (allowBits & b) === b },
      deny: { has: (b) => (denyBits & b) === b },
    });
  };
  refresh();

  return {
    id: 'channel-1',
    permissionOverwrites: {
      cache: { get: (id) => overwrites.get(id) },
      edit: async (role, patch) => {
        if (remainingFailures > 0) {
          remainingFailures--;
          throw new Error('500: Discord API unavailable');
        }
        const value = patch[permission];
        if (value === true) {
          allowBits = bit;
          denyBits = 0n;
        } else if (value === false) {
          denyBits = bit;
          allowBits = 0n;
        } else {
          allowBits = 0n;
          denyBits = 0n;
        }
        refresh();
      },
    },
    getState: () => getPermissionState(overwrites.get(roleId), permission),
    toString: () => '<#channel-1>',
  };
}

function createMockClient({ guildId, roleId, channel, manageChannels = true }) {
  const guild = {
    id: guildId,
    roles: {
      everyone: { id: roleId },
      cache: { get: (id) => (id === roleId ? { id: roleId } : null) },
      fetch: async (id) => (id === roleId ? { id: roleId } : null),
    },
    members: {
      me: { permissions: { has: (bit) => (manageChannels ? bit === PermissionFlagsBits.ManageChannels : false) } },
      fetchMe: async () => ({
        permissions: { has: (bit) => (manageChannels ? bit === PermissionFlagsBits.ManageChannels : false) },
      }),
    },
    channels: {
      fetch: async (id) => (id === channel.id ? channel : null),
    },
  };

  return {
    guilds: {
      fetch: async (id) => (id === guildId ? guild : null),
    },
  };
}

async function seedChannelUnlock(db, {
  guildId,
  channelId,
  roleId,
  previousState,
  endsAt,
  attemptCount = 0,
  nextRetryAt = null,
}) {
  return db.upsertChannelTimedAction({
    guildId,
    channelId,
    roleId,
    action: 'channel_unlock',
    permission: 'SendMessages',
    previousState,
    appliedState: 'deny',
    endsAt,
    moderatorId: 'mod-1',
  }).then(async (id) => {
    if (attemptCount > 0 || nextRetryAt) {
      await db.recordTimedActionRetry(id, {
        attemptCount,
        lastError: 'prior_failure',
        nextRetryAt: nextRetryAt ?? endsAt,
      });
    }
    return id;
  });
}

console.log('Running timed channel tests...');

for (const state of ['allow', 'deny', 'unset']) {
  const overwrite = mockOverwrite(state);
  assert.equal(getPermissionState(overwrite, 'SendMessages'), state);
  const expected = state === 'allow' ? true : state === 'deny' ? false : null;
  assert.equal(permissionStateToOverwriteValue(state), expected);
}
console.log('permission-state serialization: PASS');

for (const state of ['allow', 'deny', 'unset']) {
  const roleId = 'role-everyone';
  const channel = createMockChannel(roleId, state);
  await applyPermissionState(channel, roleId, 'SendMessages', 'deny');
  assert.equal(channel.getState(), 'deny');
  await applyPermissionState(channel, roleId, 'SendMessages', state);
  assert.equal(channel.getState(), state);
}
console.log('permission-state restoration: PASS');

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await importDbFresh();
  db.configureDatabase({ path: dbPath, hooks: {} });
  await db.initializeDatabase();

  const guildId = '123456789012345678';
  const channelId = 'channel-1';
  const roleId = 'role-everyone';
  const permission = 'SendMessages';
  const now = Date.now();

  const firstId = await db.upsertChannelTimedAction({
    guildId,
    channelId,
    roleId,
    action: 'channel_unlock',
    permission,
    previousState: 'unset',
    appliedState: 'deny',
    endsAt: now + 10 * 60 * 1000,
    moderatorId: 'mod-1',
  });

  const secondId = await db.upsertChannelTimedAction({
    guildId,
    channelId,
    roleId,
    action: 'channel_unlock',
    permission,
    previousState: 'allow',
    appliedState: 'deny',
    endsAt: now + 30 * 60 * 1000,
    moderatorId: 'mod-2',
  });

  assert.equal(firstId, secondId);
  const data = await db.readDatabase();
  const pending = data.timed_actions.filter((a) => a.action === 'channel_unlock');
  assert.equal(pending.length, 1);
  assert.equal(pending[0].previous_state, 'unset');
  assert.equal(pending[0].ends_at, now + 30 * 60 * 1000);
  console.log('overlapping lock test: PASS');

  const cancelled = await db.cancelChannelTimedActions(guildId, channelId, 'channel_unlock', permission);
  assert.equal(cancelled.removed, 1);
  console.log('manual unlock cancellation test: PASS');

  await seedChannelUnlock(db, {
    guildId,
    channelId,
    roleId,
    previousState: 'allow',
    endsAt: now - 1000,
  });

  const roleId2 = 'role-everyone';
  const channel = createMockChannel(roleId2, 'deny');
  const client = createMockClient({ guildId, roleId: roleId2, channel });
  const { processDueTimedActions, executeTimedAction } = await import('../src/handlers/timedActions.js');

  await processDueTimedActions(client);
  assert.equal(channel.getState(), 'allow');
  const afterRestore = await db.readDatabase();
  assert.equal(afterRestore.timed_actions.length, 0);
  console.log('restart / due restoration test: PASS');

  await seedChannelUnlock(db, {
    guildId,
    channelId,
    roleId,
    previousState: 'unset',
    endsAt: now - 1000,
  });

  const conflictChannel = createMockChannel(roleId2, 'allow');
  const conflictClient = createMockClient({ guildId, roleId: roleId2, channel: conflictChannel });
  const due = await db.getDueTimedActions();
  assert.equal(due.length, 1);

  const result = await executeTimedAction(conflictClient, due[0]);
  assert.equal(result.outcome, 'terminal');
  assert.equal(result.reason, 'manual_change');
  assert.equal(conflictChannel.getState(), 'allow');
  await db.completeTimedAction(due[0].id);
  console.log('manual-change conflict test: PASS');

  await db.upsertChannelTimedAction({
    guildId,
    channelId: 'deleted-channel',
    roleId,
    action: 'channel_unlock',
    permission,
    previousState: 'unset',
    appliedState: 'deny',
    endsAt: now - 1000,
    moderatorId: 'mod-1',
  });

  const missingClient = createMockClient({
    guildId,
    roleId: roleId2,
    channel: createMockChannel(roleId2, 'deny'),
  });
  await processDueTimedActions(missingClient);
  const afterMissing = await db.readDatabase();
  assert.equal(afterMissing.timed_actions.length, 0);
  console.log('deleted channel test: PASS');

  await seedChannelUnlock(db, {
    guildId,
    channelId,
    roleId,
    previousState: 'allow',
    endsAt: now - 1000,
  });

  const failChannel = createMockChannel(roleId2, 'deny', { failEdits: 1 });
  const failClient = createMockClient({ guildId, roleId: roleId2, channel: failChannel });
  await processDueTimedActions(failClient);
  let action = (await db.readDatabase()).timed_actions[0];
  assert.ok(action);
  assert.equal(action.status ?? 'pending', 'pending');
  assert.equal(action.attempt_count, 1);
  assert.ok(action.next_retry_at > Date.now());

  action.next_retry_at = Date.now() - 1;
  await db.recordTimedActionRetry(action.id, {
    attemptCount: action.attempt_count,
    lastError: action.last_error,
    nextRetryAt: action.next_retry_at,
  });

  await processDueTimedActions(failClient);
  assert.equal(failChannel.getState(), 'allow');
  assert.equal((await db.readDatabase()).timed_actions.length, 0);
  console.log('transient failure test: PASS');

  await seedChannelUnlock(db, {
    guildId,
    channelId,
    roleId,
    previousState: 'unset',
    endsAt: now - 1000,
  });

  const noPermChannel = createMockChannel(roleId2, 'deny');
  const noPermClient = createMockClient({
    guildId,
    roleId: roleId2,
    channel: noPermChannel,
    manageChannels: false,
  });
  await processDueTimedActions(noPermClient);
  action = (await db.readDatabase()).timed_actions[0];
  assert.equal(action.attempt_count, 1);
  assert.equal(action.status ?? 'pending', 'pending');

  const withPermClient = createMockClient({
    guildId,
    roleId: roleId2,
    channel: noPermChannel,
    manageChannels: true,
  });
  action.next_retry_at = Date.now() - 1;
  await db.recordTimedActionRetry(action.id, {
    attemptCount: action.attempt_count,
    lastError: action.last_error,
    nextRetryAt: action.next_retry_at,
  });
  await processDueTimedActions(withPermClient);
  assert.equal(noPermChannel.getState(), 'unset');
  console.log('missing permission test: PASS');

  await seedChannelUnlock(db, {
    guildId,
    channelId,
    roleId,
    previousState: 'allow',
    endsAt: now - 1000,
  });

  const maxFailChannel = createMockChannel(roleId2, 'deny', { failEdits: MAX_CHANNEL_UNLOCK_ATTEMPTS });
  const maxFailClient = createMockClient({ guildId, roleId: roleId2, channel: maxFailChannel });
  for (let i = 0; i < MAX_CHANNEL_UNLOCK_ATTEMPTS; i++) {
    action = (await db.getDueTimedActions())[0] ?? (await db.readDatabase()).timed_actions[0];
    if (action.next_retry_at) {
      await db.recordTimedActionRetry(action.id, {
        attemptCount: action.attempt_count ?? 0,
        lastError: action.last_error ?? 'err',
        nextRetryAt: Date.now() - 1,
      });
    }
    await processDueTimedActions(maxFailClient);
  }

  const failed = (await db.readDatabase()).timed_actions[0];
  assert.equal(failed.status, 'failed');
  assert.equal(failed.attempt_count, MAX_CHANNEL_UNLOCK_ATTEMPTS);
  assert.equal(maxFailChannel.getState(), 'deny');
  assert.equal((await db.getDueTimedActions()).length, 0);

  const diagnostics = await db.getChannelRestoreDiagnostics(guildId);
  assert.equal(diagnostics.failed.length, 1);
  console.log('maximum attempts test: PASS');

  for (const originalState of ['allow', 'deny', 'unset']) {
    const manualChannel = createMockChannel(roleId2, 'deny');
    const timedAction = {
      permission: 'SendMessages',
      applied_state: 'deny',
      previous_state: originalState,
    };
    const restore = await restoreChannelFromTimedAction(manualChannel, roleId2, timedAction);
    assert.equal(restore.type, 'restored');
    assert.equal(manualChannel.getState(), originalState);
  }
  console.log('manual restore explicit states test: PASS');

  const staleChannel = createMockChannel(roleId2, 'allow');
  const staleAction = {
    permission: 'SendMessages',
    applied_state: 'deny',
    previous_state: 'unset',
  };
  const staleResult = await restoreChannelFromTimedAction(staleChannel, roleId2, staleAction);
  assert.equal(staleResult.type, 'conflict');
  assert.equal(staleChannel.getState(), 'allow');
  console.log('manual restore conflict helper test: PASS');

  assert.equal(getRetryDelayMs(1), 30_000);
  assert.equal(getRetryDelayMs(3), 120_000);
  assert.equal(getRetryDelayMs(10), 300_000);
});

assert.equal(channelPermissionMatches(mockOverwrite('deny'), 'SendMessages', 'deny'), true);
assert.equal(channelPermissionMatches(mockOverwrite('allow'), 'SendMessages', 'deny'), false);

await import('./verify-database.mjs');

console.log('All timed channel and regression tests passed');
