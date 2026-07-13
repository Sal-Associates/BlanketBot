import assert from 'node:assert/strict';

process.env.SUPERUSER_IDS = 'super';

const {
  checkModerationTarget,
  checkBotCanActOn,
  MODERATION_DENIAL,
  isSuperuser,
} = await import(`../src/utils/permissions.js?moderation=${Date.now()}`);

function mockGuild({ ownerId = 'owner', botPosition = 20 } = {}) {
  return {
    ownerId,
    members: {
      me: {
        id: 'bot',
        roles: { highest: { position: botPosition } },
      },
    },
  };
}

function mockMember(id, position, guild) {
  return {
    id,
    roles: { highest: { position } },
    guild,
    user: { tag: `User${id}`, id },
  };
}

const guild = mockGuild({ ownerId: 'owner', botPosition: 20 });
const mod = mockMember('mod', 10, guild);
const targetLow = mockMember('target-low', 5, guild);
const targetEqual = mockMember('target-equal', 10, guild);
const targetHigh = mockMember('target-high', 15, guild);
const owner = mockMember('owner', 0, guild);
const superuser = mockMember('super', 3, guild);

assert.equal(isSuperuser('super'), true);

// Moderator 10, target 5, bot 20: allowed
assert.equal(checkModerationTarget(guild, mod, targetLow).allowed, true);

// Moderator 10, target 10: denied
assert.equal(checkModerationTarget(guild, mod, targetEqual).allowed, false);
assert.equal(checkModerationTarget(guild, mod, targetEqual).reason, MODERATION_DENIAL.TARGET_ABOVE_ISSUER);

// Moderator 10, target 15: denied
assert.equal(checkModerationTarget(guild, mod, targetHigh).allowed, false);

// Guild owner targeting position 15: allowed if bot above target
assert.equal(checkModerationTarget(guild, owner, targetHigh).allowed, true);

// Superuser targeting member above superuser: denied
assert.equal(checkModerationTarget(guild, superuser, targetHigh).allowed, false);

// Bot position 8, target 9: denied regardless of issuer
const lowBotGuild = mockGuild({ botPosition: 8 });
const modLowBot = mockMember('mod', 10, lowBotGuild);
const targetNine = mockMember('target-nine', 9, lowBotGuild);
assert.equal(checkModerationTarget(lowBotGuild, modLowBot, targetNine).allowed, false);
assert.equal(checkModerationTarget(lowBotGuild, modLowBot, targetNine).reason, MODERATION_DENIAL.BOT_CANNOT_ACT);

// Self-target denied
assert.equal(checkModerationTarget(guild, mod, mod).allowed, false);
assert.equal(checkModerationTarget(guild, mod, mod).reason, MODERATION_DENIAL.SELF);

// Guild owner target denied
assert.equal(checkModerationTarget(guild, mod, owner).allowed, false);
assert.equal(checkModerationTarget(guild, mod, owner).reason, MODERATION_DENIAL.TARGET_IS_OWNER);

// Unmute / undeafen use same member hierarchy path
assert.equal(checkModerationTarget(guild, mod, targetHigh).allowed, false);

// Member-only command with plain user object
assert.equal(checkModerationTarget(guild, mod, { id: 'gone' }).allowed, false);
assert.equal(checkModerationTarget(guild, mod, { id: 'gone' }).reason, MODERATION_DENIAL.NOT_A_MEMBER);

// Ban by raw user ID for non-member still allowed when otherwise permitted
assert.equal(checkModerationTarget(guild, mod, { id: '999999999999999999' }, { requireMember: false }).allowed, true);

// Bot escalation helper
assert.equal(checkBotCanActOn(guild, targetLow).allowed, true);
assert.equal(checkBotCanActOn(lowBotGuild, targetNine).allowed, false);

console.log('Moderation hierarchy tests passed');
