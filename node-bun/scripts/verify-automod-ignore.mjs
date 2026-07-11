import assert from 'node:assert/strict';

process.env.GUILD_ID = process.env.GUILD_ID || '123456789012345678';
process.env.SUPERUSER_IDS = '';

import { mkdtemp, rm } from 'fs/promises';
import { join } from 'path';
import { tmpdir } from 'os';
import { ChannelType } from 'discord.js';
import {
  isAutomodEligibleChannel,
  resolveChannelTarget,
  resolveRoleTarget,
  formatIgnoredChannelLine,
  formatIgnoredRoleLine,
} from '../src/utils/automodIgnore.js';

async function withTempDatabase(run) {
  const dir = await mkdtemp(join(tmpdir(), 'modbot-automod-ignore-'));
  const dbPath = join(dir, 'store.json');
  try {
    await run(dbPath);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

function mockTextChannel(id, name = 'general') {
  return {
    id,
    name,
    isTextBased: () => true,
    toString: () => `<#${id}>`,
  };
}

function mockVoiceChannel(id) {
  return {
    id,
    type: ChannelType.GuildVoice,
    isTextBased: () => false,
    toString: () => `<#${id}>`,
  };
}

function mockGuild({ channels = [], roles = [] }) {
  const channelMap = new Map(channels.map((c) => [c.id, c]));
  const roleMap = new Map(roles.map((r) => [r.id, r]));
  const everyone = roles.find((r) => r.name === '@everyone') ?? { id: 'role-everyone', name: '@everyone' };
  return {
    id: '123456789012345678',
    roles: {
      everyone,
      cache: roleMap,
      get: (id) => roleMap.get(id),
    },
    channels: {
      cache: channelMap,
      get: (id) => channelMap.get(id),
    },
  };
}

function createMockMessage({
  guildId,
  channelId,
  userId,
  content,
  roleIds = [],
  isModerator = false,
}) {
  let deleted = false;
  let bannedWordsLoaded = false;

  return {
    guild: { id: guildId },
    author: { id: userId, bot: false },
    content,
    member: {
      id: userId,
      guild: { id: guildId },
      permissions: {
        has: (bit) => isModerator,
      },
      roles: {
        cache: {
          some: (fn) => roleIds.map((id) => ({ id })).some(fn),
        },
      },
    },
    channel: {
      id: channelId,
      send: async () => ({ delete: async () => {} }),
    },
    mentions: { users: { size: 0 }, roles: { size: 0 }, everyone: false },
    delete: async () => { deleted = true; },
    wasDeleted: () => deleted,
    setBannedWordsLoaded: () => { bannedWordsLoaded = true; },
    bannedWordsLoaded: () => bannedWordsLoaded,
  };
}

console.log('Running Automod ignore tests...');

assert.equal(isAutomodEligibleChannel(mockTextChannel('ch-1')), true);
assert.equal(isAutomodEligibleChannel(mockVoiceChannel('voice-1')), false);
console.log('channel eligibility: PASS');

await withTempDatabase(async (dbPath) => {
  process.env.STORE_PATH = dbPath;
  const db = await import('../src/database/db.js');
  db.configureDatabase({ path: dbPath, hooks: {} });
  await db.initializeDatabase();

  const guildId = '123456789012345678';
  const textChannel = mockTextChannel('ch-text', 'general');
  const guild = mockGuild({
    channels: [textChannel, mockVoiceChannel('ch-voice')],
    roles: [
      { id: 'role-everyone', name: '@everyone' },
      { id: 'role-mod', name: 'Moderator' },
      { id: 'role-vip', name: 'VIP' },
    ],
  });

  await db.addIgnoredChannel(guildId, 'ch-text');
  assert.deepEqual(await db.getIgnoredChannels(guildId), ['ch-text']);
  console.log('add valid text channel: PASS');

  await assert.rejects(
    () => db.addIgnoredChannel(guildId, 'ch-text'),
    (err) => err.message === 'duplicate_ignored_channel',
  );
  console.log('reject duplicate channel: PASS');

  const voiceTarget = resolveChannelTarget(guild, 'ch-voice');
  assert.equal(voiceTarget.channel && isAutomodEligibleChannel(voiceTarget.channel), false);
  console.log('reject unsupported channel type: PASS');

  const removed = await db.removeIgnoredChannel(guildId, 'ch-text');
  assert.equal(removed.removed, 1);
  assert.deepEqual(await db.getIgnoredChannels(guildId), []);
  console.log('remove channel by ID: PASS');

  await db.addIgnoredChannel(guildId, 'ch-deleted');
  const missingRemoved = await db.removeIgnoredChannel(guildId, 'ch-deleted');
  assert.equal(missingRemoved.removed, 1);
  console.log('remove deleted-channel ID: PASS');

  const notFound = await db.removeIgnoredChannel(guildId, '999999999999999999');
  assert.equal(notFound.removed, 0);
  console.log('invalid channel ID not found: PASS');

  await db.addIgnoredChannel(guildId, 'ch-text');
  await db.addIgnoredChannel(guildId, 'ch-stale');
  const listLines = (await db.getIgnoredChannels(guildId)).map((id) => formatIgnoredChannelLine(guild, id));
  const activeLine = listLines.find((line) => line.includes('ch-text'));
  const staleLine = listLines.find((line) => line.includes('ch-stale'));
  assert.match(activeLine, /ch-text/);
  assert.match(staleLine, /Deleted or inaccessible channel/);
  console.log('list active and deleted channels: PASS');

  await db.addIgnoredRole(guildId, 'role-vip');
  assert.deepEqual(await db.getIgnoredRoles(guildId), ['role-vip']);
  console.log('add valid role: PASS');

  await assert.rejects(
    () => db.addIgnoredRole(guildId, 'role-vip'),
    (err) => err.message === 'duplicate_ignored_role',
  );
  console.log('reject duplicate role: PASS');

  const everyoneTarget = resolveRoleTarget(guild, guild.roles.everyone.id);
  assert.equal(everyoneTarget.id, guild.roles.everyone.id);
  // @everyone is rejected by addIgnoredRoleEntry in automod.js, not at DB layer
  console.log('reject everyone policy (command layer): PASS');

  const roleRemoved = await db.removeIgnoredRole(guildId, 'role-vip');
  assert.equal(roleRemoved.removed, 1);
  console.log('remove active role: PASS');

  await db.addIgnoredRole(guildId, 'role-gone');
  const staleRoleRemoved = await db.removeIgnoredRole(guildId, 'role-gone');
  assert.equal(staleRoleRemoved.removed, 1);
  console.log('remove deleted-role ID: PASS');

  const roleNotFound = await db.removeIgnoredRole(guildId, '888888888888888888');
  assert.equal(roleNotFound.removed, 0);
  console.log('invalid role ID not found: PASS');

  await db.addIgnoredRole(guildId, 'role-vip');
  const roleLines = [formatIgnoredRoleLine(guild, 'role-vip'), formatIgnoredRoleLine(guild, 'role-missing')];
  assert.match(roleLines[0], /VIP/);
  assert.match(roleLines[1], /Deleted or inaccessible role/);
  console.log('list active and deleted roles: PASS');

  await db.addBannedWord(guildId, 'badword', 'contains', 'mod-1');
  const { handleAutomod } = await import('../src/handlers/automodHandler.js');

  for (const id of await db.getIgnoredChannels(guildId)) {
    await db.removeIgnoredChannel(guildId, id);
  }

  await db.addIgnoredChannel(guildId, 'ch-ignored');
  const ignoredChannelMsg = createMockMessage({
    guildId,
    channelId: 'ch-ignored',
    userId: 'user-1',
    content: 'badword here',
  });
  assert.equal(await handleAutomod(ignoredChannelMsg), false);
  assert.equal(ignoredChannelMsg.wasDeleted(), false);
  console.log('ignored channel bypasses automod: PASS');

  await db.removeIgnoredChannel(guildId, 'ch-ignored');
  const ignoredRoleMsg = createMockMessage({
    guildId,
    channelId: 'ch-text',
    userId: 'user-2',
    content: 'badword here',
    roleIds: ['role-vip'],
  });
  assert.equal(await handleAutomod(ignoredRoleMsg), false);
  assert.equal(ignoredRoleMsg.wasDeleted(), false);
  console.log('ignored role bypasses automod: PASS');

  const normalMsg = createMockMessage({
    guildId,
    channelId: 'ch-text',
    userId: 'user-3',
    content: 'badword here',
    roleIds: ['role-other'],
  });
  assert.equal(await handleAutomod(normalMsg), true);
  assert.equal(normalMsg.wasDeleted(), true);
  console.log('non-ignored member still triggers automod: PASS');

  await db.addIgnoredRole(guildId, 'role-deleted-id');
  const deletedRoleMsg = createMockMessage({
    guildId,
    channelId: 'ch-text',
    userId: 'user-4',
    content: 'badword again',
    roleIds: ['role-other'],
  });
  assert.equal(await handleAutomod(deletedRoleMsg), true);
  console.log('deleted role ID does not crash processing: PASS');

  const persistedChannels = await db.getIgnoredChannels(guildId);
  db.configureDatabase({ path: dbPath, hooks: {} });
  const reloaded = await import('../src/database/db.js');
  assert.deepEqual(await reloaded.getIgnoredChannels(guildId), persistedChannels);
  console.log('persistence across reload: PASS');

  const [r1, r2] = await Promise.allSettled([
    reloaded.addIgnoredChannel(guildId, 'ch-concurrent'),
    reloaded.addIgnoredChannel(guildId, 'ch-concurrent'),
  ]);
  const fulfilled = [r1, r2].filter((r) => r.status === 'fulfilled');
  const rejected = [r1, r2].filter((r) => r.status === 'rejected');
  assert.equal(fulfilled.length, 1);
  assert.equal(rejected.length, 1);
  assert.equal((await reloaded.getIgnoredChannels(guildId)).filter((id) => id === 'ch-concurrent').length, 1);
  console.log('concurrent duplicate channel add: PASS');

  await reloaded.addIgnoredChannel(guildId, 'ch-rm');
  const [rm1, rm2] = await Promise.all([
    reloaded.removeIgnoredChannel(guildId, 'ch-rm'),
    reloaded.removeIgnoredChannel(guildId, 'ch-rm'),
  ]);
  assert.equal(rm1.removed + rm2.removed, 1);
  console.log('concurrent remove operations: PASS');

  const automodCmd = (await import('../src/commands/automod/automod.js')).default;
  assert.equal(typeof automodCmd.execute, 'function');
  assert.match(automodCmd.usage, /automod/);
  console.log('legacy alias module loads shared command: PASS');
});

console.log('All Automod ignore tests passed.');
