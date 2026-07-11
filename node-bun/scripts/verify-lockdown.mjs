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
} from '../src/utils/channelPermissions.js';
import { MAX_CHANNEL_UNLOCK_ATTEMPTS } from '../src/utils/timedActionRetry.js';

async function withTempDatabase(run) {
  const dir = await mkdtemp(join(tmpdir(), 'modbot-lockdown-'));
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

function createMockChannel(channelId, roleId, initialState, { failEdits = 0, textBased = true } = {}) {
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
    id: channelId,
    isTextBased: () => textBased,
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
    toString: () => `<#${channelId}>`,
  };
}

function createMockGuild({ guildId, roleId, channels, manageChannels = true }) {
  const channelMap = new Map(channels.map((c) => [c.id, c]));
  return {
    id: guildId,
    name: 'Test Guild',
    roles: { everyone: { id: roleId } },
    members: {
      me: {
        permissions: {
          has: (bit) => (manageChannels ? bit === PermissionFlagsBits.ManageChannels : false),
        },
      },
    },
    channels: {
      cache: channelMap,
      get: (id) => channelMap.get(id),
    },
  };
}

function createModerator(id = 'mod-1') {
  return { id, toString: () => `<@${id}>` };
}

console.log('Running lockdown tests...');

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await importDbFresh();
  db.configureDatabase({ path: dbPath, hooks: {} });
  await db.initializeDatabase();

  const guildId = '123456789012345678';
  const roleId = 'role-everyone';
  const mod = createModerator();

  await db.addLockdownChannel(guildId, 'ch-1');
  await db.addLockdownChannel(guildId, 'ch-2');
  assert.deepEqual(await db.getLockdownChannels(guildId), ['ch-1', 'ch-2']);
  console.log('add channel: PASS');

  await assert.rejects(
    () => db.addLockdownChannel(guildId, 'ch-1'),
    (err) => err.message === 'duplicate_lockdown_channel',
  );
  console.log('reject duplicate: PASS');

  const removed = await db.removeLockdownChannel(guildId, 'ch-2');
  assert.equal(removed.removed, 1);
  assert.deepEqual(await db.getLockdownChannels(guildId), ['ch-1']);
  console.log('remove channel: PASS');

  await db.addLockdownChannel(guildId, 'ch-deleted');
  const list = await db.getLockdownChannels(guildId);
  assert.ok(list.includes('ch-deleted'));
  console.log('list configured channels: PASS');

  const { enableLockdown, disableLockdown } = await import('../src/handlers/lockdownHandler.js');

  for (const initialState of ['allow', 'deny', 'unset']) {
    for (const id of await db.getLockdownChannels(guildId)) {
      await db.removeLockdownChannel(guildId, id);
    }
    await db.addLockdownChannel(guildId, 'ch-state');
    await db.clearLockdownState(guildId);

    const channel = createMockChannel('ch-state', roleId, initialState);
    const guild = createMockGuild({ guildId, roleId, channels: [channel] });

    const result = await enableLockdown(guild, mod, 'test enable');
    assert.match(result.reply, /Lockdown enabled/);
    assert.equal(channel.getState(), 'deny');

    const state = await db.getLockdownState(guildId);
    assert.equal(state.active, true);
    const channelEntry = state.channels.find((c) => c.channel_id === 'ch-state');
    assert.equal(channelEntry.previous_state, initialState);
    assert.equal(channelEntry.applied_state, 'deny');
    assert.equal(channelEntry.result, 'applied');

    await disableLockdown(guild, mod, 'test disable');
    assert.equal(channel.getState(), initialState);
    await db.clearLockdownState(guildId);
  }
  console.log('enable from allow/deny/unset + disable restore: PASS');

  for (const id of await db.getLockdownChannels(guildId)) {
    await db.removeLockdownChannel(guildId, id);
  }
  await db.clearLockdownState(guildId);
  await db.removeLockdownChannel(guildId, 'ch-state').catch(() => {});
  await db.addLockdownChannel(guildId, 'ch-ok');
  await db.addLockdownChannel(guildId, 'ch-fail');

  const okChannel = createMockChannel('ch-ok', roleId, 'allow');
  const failChannel = createMockChannel('ch-fail', roleId, 'allow', { failEdits: 99 });
  const partialGuild = createMockGuild({
    guildId,
    roleId,
    channels: [okChannel, failChannel],
  });

  const partial = await enableLockdown(partialGuild, mod, 'partial');
  assert.match(partial.reply, /1 of 2/);
  assert.match(partial.reply, /failed/i);

  const partialState = await db.getLockdownState(guildId);
  assert.equal(partialState.active, true);
  assert.equal(partialState.channels.filter((c) => c.result === 'applied').length, 1);
  assert.equal(partialState.channels.filter((c) => c.result === 'failed').length, 1);
  console.log('partial enable failure: PASS');

  await disableLockdown(partialGuild, mod, 'cleanup partial');
  await db.clearLockdownState(guildId);

  await db.removeLockdownChannel(guildId, 'ch-ok');
  await db.removeLockdownChannel(guildId, 'ch-fail');
  await db.addLockdownChannel(guildId, 'ch-a');
  await db.addLockdownChannel(guildId, 'ch-b');

  const failA = createMockChannel('ch-a', roleId, 'allow', { failEdits: 99 });
  const failB = createMockChannel('ch-b', roleId, 'allow', { failEdits: 99 });
  const totalFailGuild = createMockGuild({ guildId, roleId, channels: [failA, failB] });

  const totalFail = await enableLockdown(totalFailGuild, mod, 'total fail');
  assert.match(totalFail.reply, /failed/i);
  const afterTotalFail = await db.getLockdownState(guildId);
  assert.equal(afterTotalFail, null);
  console.log('total enable failure: PASS');

  await db.clearLockdownState(guildId);
  await db.addLockdownChannel(guildId, 'ch-manual');
  const manualChannel = createMockChannel('ch-manual', roleId, 'allow');
  const manualGuild = createMockGuild({ guildId, roleId, channels: [manualChannel] });
  await enableLockdown(manualGuild, mod, 'manual test');
  await applyPermissionState(manualChannel, roleId, 'SendMessages', 'allow');

  const manualDisable = await disableLockdown(manualGuild, mod, 'preserve manual');
  assert.match(manualDisable.reply, /manual change/i);
  assert.equal(manualChannel.getState(), 'allow');
  console.log('disable preserves manual changes: PASS');

  await db.clearLockdownState(guildId);
  for (const id of await db.getLockdownChannels(guildId)) {
    await db.removeLockdownChannel(guildId, id);
  }
  await db.addLockdownChannel(guildId, 'ch-restart');
  const restartChannel = createMockChannel('ch-restart', roleId, 'unset');
  const restartGuild = createMockGuild({ guildId, roleId, channels: [restartChannel] });

  await enableLockdown(restartGuild, mod, 'restart test');
  const beforeRestart = await db.getLockdownState(guildId);
  assert.equal(beforeRestart.active, true);

  db.configureDatabase({ path: dbPath, hooks: {} });
  const reloadedState = await db.getLockdownState(guildId);
  assert.equal(reloadedState.active, true);
  const restartEntry = reloadedState.channels.find((c) => c.channel_id === 'ch-restart');
  assert.equal(restartEntry.previous_state, 'unset');

  await disableLockdown(restartGuild, mod, 'after restart');
  assert.equal(restartChannel.getState(), 'unset');
  console.log('restart persistence: PASS');

  await db.clearLockdownState(guildId);
  for (const id of await db.getLockdownChannels(guildId)) {
    await db.removeLockdownChannel(guildId, id);
  }
  await db.addLockdownChannel(guildId, 'ch-race');
  const raceChannel = createMockChannel('ch-race', roleId, 'allow');
  const raceGuild = createMockGuild({ guildId, roleId, channels: [raceChannel] });

  const [race1, race2] = await Promise.all([
    enableLockdown(raceGuild, mod, 'race 1'),
    enableLockdown(raceGuild, createModerator('mod-2'), 'race 2'),
  ]);
  const successes = [race1, race2].filter((r) => /Lockdown enabled/i.test(r.reply));
  const failures = [race1, race2].filter((r) => /already active/i.test(r.reply));
  assert.equal(successes.length, 1);
  assert.equal(failures.length, 1);
  const raceState = await db.getLockdownState(guildId);
  assert.equal(raceState.channels.find((c) => c.channel_id === 'ch-race').previous_state, 'allow');
  console.log('concurrent enable: PASS');

  const casesBeforeDisable = (await db.readDatabase()).cases.length;
  const [d1, d2] = await Promise.all([
    disableLockdown(raceGuild, mod, 'disable 1'),
    disableLockdown(raceGuild, createModerator('mod-2'), 'disable 2'),
  ]);
  const disableSuccess = [d1, d2].filter((r) => /Lockdown disabled/i.test(r.reply));
  const disableFail = [d1, d2].filter((r) => /No active lockdown/i.test(r.reply));
  assert.equal(disableSuccess.length, 1);
  assert.equal(disableFail.length, 1);
  const casesAfterDisable = (await db.readDatabase()).cases;
  assert.equal(casesAfterDisable.length - casesBeforeDisable, 1);
  console.log('concurrent disable: PASS');

  await db.clearLockdownState(guildId);
  for (const id of await db.getLockdownChannels(guildId)) {
    await db.removeLockdownChannel(guildId, id);
  }
  await db.addLockdownChannel(guildId, 'ch-db-fail');
  const dbFailChannel = createMockChannel('ch-db-fail', roleId, 'allow');
  const dbFailGuild = createMockGuild({ guildId, roleId, channels: [dbFailChannel] });

  await db.acquireLockdownEnable(guildId, {
    moderatorId: mod.id,
    reason: 'db fail test',
    roleId,
    permission: 'SendMessages',
  });
  const entry = {
    channel_id: 'ch-db-fail',
    previous_state: 'allow',
    applied_state: 'deny',
    result: 'applied',
  };
  await applyPermissionState(dbFailChannel, roleId, 'SendMessages', 'deny');
  db.configureDatabase({ path: dbPath, hooks: { failNextMutations: 1 } });
  await assert.rejects(
    () => db.finalizeLockdownEnable(guildId, [entry]),
    (err) => err.message === 'Simulated mutation failure',
  );
  db.configureDatabase({ path: dbPath, hooks: {} });
  await applyPermissionState(dbFailChannel, roleId, 'SendMessages', 'allow');
  await db.clearLockdownState(guildId);
  assert.equal(dbFailChannel.getState(), 'allow');
  console.log('database failure rollback path: PASS');

  await db.clearLockdownState(guildId);
  for (const id of await db.getLockdownChannels(guildId)) {
    await db.removeLockdownChannel(guildId, id);
  }
  await db.addLockdownChannel(guildId, 'ch-retry');
  await db.addLockdownRestoreAction({
    guildId,
    channelId: 'ch-retry',
    roleId,
    permission: 'SendMessages',
    previousState: 'unset',
    appliedState: 'deny',
  });

  const { processDueTimedActions } = await import('../src/handlers/timedActions.js');
  const failRetryChannel = createMockChannel('ch-retry', roleId, 'deny', { failEdits: 1 });
  const makeRetryClient = (channel) => ({
    guilds: {
      fetch: async (id) => (id === guildId ? {
        id: guildId,
        roles: {
          everyone: { id: roleId },
          cache: { get: (id2) => (id2 === roleId ? { id: roleId } : null) },
          fetch: async (id2) => (id2 === roleId ? { id: roleId } : null),
        },
        members: {
          me: { permissions: { has: (bit) => bit === PermissionFlagsBits.ManageChannels } },
          fetchMe: async () => ({ permissions: { has: (bit) => bit === PermissionFlagsBits.ManageChannels } }),
        },
        channels: { fetch: async (id2) => (id2 === 'ch-retry' ? channel : null) },
      } : null),
    },
  });

  await processDueTimedActions(makeRetryClient(failRetryChannel));
  let pending = (await db.readDatabase()).timed_actions.filter((a) => a.action === 'lockdown_channel_restore');
  assert.equal(pending.length, 1);
  assert.equal(pending[0].attempt_count, 1);

  pending[0].next_retry_at = Date.now() - 1;
  await db.recordTimedActionRetry(pending[0].id, {
    attemptCount: pending[0].attempt_count,
    lastError: pending[0].last_error,
    nextRetryAt: pending[0].next_retry_at,
  });

  const successRetryChannel = createMockChannel('ch-retry', roleId, 'deny');
  await processDueTimedActions(makeRetryClient(successRetryChannel));
  assert.equal(successRetryChannel.getState(), 'unset');
  assert.equal((await db.readDatabase()).timed_actions.filter((a) => a.action === 'lockdown_channel_restore').length, 0);
  console.log('lockdown restore retry: PASS');

  await db.clearLockdownState(guildId);
  await db.addLockdownChannel(guildId, 'ch-max-retry');
  await db.addLockdownRestoreAction({
    guildId,
    channelId: 'ch-max-retry',
    roleId,
    permission: 'SendMessages',
    previousState: 'allow',
    appliedState: 'deny',
  });

  const maxChannel = createMockChannel('ch-max-retry', roleId, 'deny', { failEdits: 99 });
  const maxClient = {
    guilds: {
      fetch: async (id) => (id === guildId ? {
        ...createMockGuild({ guildId, roleId, channels: [maxChannel] }),
        roles: {
          everyone: { id: roleId },
          cache: { get: (id2) => (id2 === roleId ? { id: roleId } : null) },
          fetch: async (id2) => (id2 === roleId ? { id: roleId } : null),
        },
        members: {
          me: maxChannel.permissionOverwrites ? { permissions: { has: () => true } } : null,
          fetchMe: async () => ({ permissions: { has: () => true } }),
        },
        channels: { fetch: async (id2) => (id2 === 'ch-max-retry' ? maxChannel : null) },
      } : null),
    },
  };

  const stuck = (await db.readDatabase()).timed_actions.find((a) => a.channel_id === 'ch-max-retry');
  stuck.next_retry_at = Date.now() - 1;
  await db.recordTimedActionRetry(stuck.id, {
    attemptCount: MAX_CHANNEL_UNLOCK_ATTEMPTS - 1,
    lastError: 'persistent',
    nextRetryAt: stuck.next_retry_at,
  });

  const { executeTimedAction } = await import('../src/handlers/timedActions.js');
  const action = (await db.getDueTimedActions()).find((a) => a.channel_id === 'ch-max-retry');
  const retryResult = await executeTimedAction(maxClient, action);
  assert.equal(retryResult.outcome, 'retryable');
  const { handleTimedActionResult } = await import('../src/handlers/timedActions.js');
  await handleTimedActionResult(maxClient, action, retryResult);
  const failed = (await db.readDatabase()).timed_actions.find((a) => a.channel_id === 'ch-max-retry');
  assert.equal(failed.status, 'failed');
  console.log('max retry retains failed record: PASS');
});

console.log('All lockdown tests passed.');
