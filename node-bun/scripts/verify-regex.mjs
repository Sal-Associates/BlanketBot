import assert from 'node:assert/strict';
import { LINK_REGEX, INVITE_REGEX } from '../src/utils/helpers.js';

const invite = 'join us at https://discord.gg/example';
const link = 'visit https://example.com/page';
const normal = 'hello world, no links here';

for (let i = 0; i < 10; i++) {
  assert.equal(INVITE_REGEX.test(invite), true);
  assert.equal(LINK_REGEX.test(link), true);
  assert.equal(INVITE_REGEX.test(normal), false);
  assert.equal(LINK_REGEX.test(normal), false);
}

const inviteVariants = [
  'discord.gg/example',
  'https://discord.gg/example',
  'https://DISCORD.GG/example',
  'https://discordapp.com/invite/example',
  'check https://discord.io/abc and more text',
];

for (const message of inviteVariants) {
  assert.equal(INVITE_REGEX.test(message), true, `invite should match: ${message}`);
}

const linkMessages = [
  'visit https://example.com/page',
  'HTTP://EXAMPLE.COM/path',
  'before https://a.com after',
];

for (const message of linkMessages) {
  assert.equal(LINK_REGEX.test(message), true, `link should match: ${message}`);
}

// Consecutive different messages must not alternate
const messages = [
  { regex: INVITE_REGEX, text: invite, expected: true },
  { regex: LINK_REGEX, text: link, expected: true },
  { regex: INVITE_REGEX, text: normal, expected: false },
  { regex: LINK_REGEX, text: normal, expected: false },
  { regex: INVITE_REGEX, text: 'https://discord.gg/abc', expected: true },
  { regex: LINK_REGEX, text: 'https://foo.bar', expected: true },
];

for (const { regex, text, expected } of messages) {
  for (let i = 0; i < 5; i++) {
    assert.equal(regex.test(text), expected, `${regex.source} on "${text}" iteration ${i}`);
  }
}

// Purge-style filter simulation
const purgeMessages = [
  { content: 'see https://example.com', links: true, invites: false },
  { content: 'join discord.gg/test', links: false, invites: true },
  { content: 'plain text', links: false, invites: false },
];

for (const msg of purgeMessages) {
  assert.equal(LINK_REGEX.test(msg.content), msg.links, `purge links: ${msg.content}`);
  assert.equal(INVITE_REGEX.test(msg.content), msg.invites, `purge invites: ${msg.content}`);
}

console.log('Regex regression tests passed');
