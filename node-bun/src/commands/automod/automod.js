import {
  addBannedWord,
  removeBannedWord,
  removeBannedWordByValue,
  getBannedWords,
  addAutomodLink,
  removeAutomodLink,
  getAutomodLinks,
  addIgnoredChannel,
  removeIgnoredChannel,
  getIgnoredChannels,
  addIgnoredRole,
  removeIgnoredRole,
  getIgnoredRoles,
  updateGuildSetting,
  updateGuildSettings,
  getGuildSettings,
  isModuleDisabled,
} from '../../database/db.js';
import { success, error, basicEmbed } from '../../utils/helpers.js';
import { checkAdmin } from '../../utils/checks.js';
import { isValidMatchMode } from '../../utils/bannedWords.js';
import {
  isAutomodEligibleChannel,
  resolveChannelTarget,
  resolveRoleTarget,
  formatIgnoredChannelLine,
  formatIgnoredRoleLine,
} from '../../utils/automodIgnore.js';
import { parseDuration } from '../../utils/time.js';
import {
  CAPS_MIN_LETTERS,
  validateCapsThresholdInput,
  validateSpamCountInput,
  validateSpamWindowInput,
  validateMentionThresholdInput,
  formatThresholdShow,
  formatSpamWindow,
  getThresholdResetUpdates,
} from '../../utils/automodThresholds.js';

const LIST_CHUNK_SIZE = 20;
const CANONICAL_IGNORE_HINT = 'Canonical syntax: `?automod ignore channel|role add|remove|list`';

async function addBannedWords(message, mode, rawValues) {
  const values = rawValues.split(',').map((part) => part.trim()).filter(Boolean);
  if (!values.length) {
    return message.reply(error('Provide at least one word or phrase.'));
  }
  if (!isValidMatchMode(mode)) {
    return message.reply(error('Match mode must be `contains` or `exact`.'));
  }

  const added = [];
  for (const value of values) {
    try {
      const id = await addBannedWord(message.guild.id, value, mode, message.author.id);
      added.push(`#${id} [${mode}] ${value.trim().toLowerCase()}`);
    } catch (err) {
      if (err.message === 'duplicate_banned_word') {
        return message.reply(error(`Duplicate entry: \`${value.trim().toLowerCase()}\` already exists in **${mode}** mode.`));
      }
      if (err.message === 'Banned word value cannot be empty') {
        return message.reply(error('Word value cannot be empty.'));
      }
      throw err;
    }
  }

  const hint = 'Use `?automod word list` to view entries. Legacy `?automod banword` / `banexact` still work.';
  return message.reply(success(`Added banned word${added.length > 1 ? 's' : ''}:\n${added.join('\n')}\n_${hint}_`));
}

async function listBannedWords(message) {
  const words = await getBannedWords(message.guild.id);
  if (!words.length) {
    return message.reply(error('No banned words configured.'));
  }

  const lines = [...words]
    .sort((a, b) => a.id - b.id)
    .map((entry) => `**#${entry.id}** [\`${entry.match_mode}\`] ${entry.value}`);

  const chunks = [];
  for (let i = 0; i < lines.length; i += LIST_CHUNK_SIZE) {
    chunks.push(lines.slice(i, i + LIST_CHUNK_SIZE).join('\n'));
  }

  for (let i = 0; i < chunks.length; i++) {
    const title = chunks.length > 1 ? `Banned Words (${i + 1}/${chunks.length})` : 'Banned Words';
    const embed = basicEmbed(title, chunks[i]);
    if (i === 0) {
      await message.reply({ embeds: [embed] });
    } else {
      await message.channel.send({ embeds: [embed] });
    }
  }
}

async function removeBannedWordEntry(message, rest) {
  const trimmed = rest.trim();
  if (!trimmed) {
    return message.reply(error('Usage: `?automod word remove <entry-id>`'));
  }

  const entryId = parseInt(trimmed, 10);
  if (Number.isInteger(entryId) && String(entryId) === trimmed) {
    const result = await removeBannedWord(message.guild.id, entryId);
    if (!result.removed) {
      return message.reply(error(`Banned word #${entryId} was not found.`));
    }
    return message.reply(success(`Removed banned word #${entryId}.`));
  }

  const parts = trimmed.split(/\s+/);
  const maybeMode = parts[parts.length - 1]?.toLowerCase();
  let mode = 'contains';
  let value = trimmed;

  if (isValidMatchMode(maybeMode) && parts.length > 1) {
    mode = maybeMode;
    value = parts.slice(0, -1).join(' ');
  }

  const containsMatches = (await getBannedWords(message.guild.id))
    .filter((entry) => entry.value === value.trim().toLowerCase());
  if (containsMatches.length > 1 && !isValidMatchMode(maybeMode)) {
    return message.reply(error(
      'That word exists in multiple modes. Remove by ID, or specify mode: `?automod word remove <text> contains|exact`.',
    ));
  }

  const result = await removeBannedWordByValue(message.guild.id, value, mode);
  if (!result.removed) {
    return message.reply(error(`No **${mode}** banned word matching \`${value.trim().toLowerCase()}\` was found.`));
  }

  return message.reply(success(
    `Removed **${mode}** banned word \`${value.trim().toLowerCase()}\`. Prefer \`?automod word remove <id>\` for unambiguous removal.`,
  ));
}

async function sendChunkedList(message, title, lines) {
  if (!lines.length) {
    return message.reply(error(`No ${title.toLowerCase()} configured.`));
  }

  const chunks = [];
  for (let i = 0; i < lines.length; i += LIST_CHUNK_SIZE) {
    chunks.push(lines.slice(i, i + LIST_CHUNK_SIZE).join('\n'));
  }

  for (let i = 0; i < chunks.length; i++) {
    const chunkTitle = chunks.length > 1 ? `${title} (${i + 1}/${chunks.length})` : title;
    const embed = basicEmbed(chunkTitle, chunks[i]);
    if (i === 0) {
      await message.reply({ embeds: [embed] });
    } else {
      await message.channel.send({ embeds: [embed] });
    }
  }
}

async function addIgnoredChannelEntry(message, input, { legacy = false } = {}) {
  const target = resolveChannelTarget(message.guild, input);
  if (!target?.channel) {
    return message.reply(error('Provide a valid channel mention or ID from this server.'));
  }
  if (!isAutomodEligibleChannel(target.channel)) {
    return message.reply(error('That channel type is not eligible for Automod message checks.'));
  }

  try {
    await addIgnoredChannel(message.guild.id, target.id);
  } catch (err) {
    if (err.message === 'duplicate_ignored_channel') {
      return message.reply(error(`${target.channel} is already in the ignored channel list.`));
    }
    throw err;
  }

  const suffix = legacy ? `\n_${CANONICAL_IGNORE_HINT}_` : '';
  return message.reply(success(`Automod will ignore ${target.channel} (\`${target.id}\`).${suffix}`));
}

async function removeIgnoredChannelEntry(message, input) {
  const target = resolveChannelTarget(message.guild, input);
  if (!target) {
    return message.reply(error('Usage: `?automod ignore channel remove #channel` or provide a channel ID.'));
  }

  const result = await removeIgnoredChannel(message.guild.id, target.id);
  if (!result.removed) {
    return message.reply(error(`Channel \`${target.id}\` is not in the ignored channel list.`));
  }

  const label = target.channel ? `${target.channel}` : `channel \`${target.id}\``;
  return message.reply(success(`Removed ${label} from ignored channels.`));
}

async function listIgnoredChannels(message) {
  const channelIds = await getIgnoredChannels(message.guild.id);
  const lines = channelIds.map((id) => formatIgnoredChannelLine(message.guild, id));
  return sendChunkedList(message, 'Ignored Channels', lines);
}

async function addIgnoredRoleEntry(message, input, { legacy = false } = {}) {
  const target = resolveRoleTarget(message.guild, input);
  if (!target?.role) {
    return message.reply(error('Provide a valid role mention or ID from this server.'));
  }
  if (target.id === message.guild.roles.everyone.id) {
    return message.reply(error('`@everyone` cannot be added — it would disable Automod for the entire server.'));
  }

  try {
    await addIgnoredRole(message.guild.id, target.id);
  } catch (err) {
    if (err.message === 'duplicate_ignored_role') {
      return message.reply(error(`Role **${target.role.name}** is already in the ignored role list.`));
    }
    throw err;
  }

  const suffix = legacy ? `\n_${CANONICAL_IGNORE_HINT}_` : '';
  return message.reply(success(`Automod will ignore role **${target.role.name}** (\`${target.id}\`).${suffix}`));
}

async function removeIgnoredRoleEntry(message, input) {
  const target = resolveRoleTarget(message.guild, input);
  if (!target) {
    return message.reply(error('Usage: `?automod ignore role remove @role` or provide a role ID.'));
  }

  const result = await removeIgnoredRole(message.guild.id, target.id);
  if (!result.removed) {
    return message.reply(error(`Role \`${target.id}\` is not in the ignored role list.`));
  }

  const label = target.role ? `**${target.role.name}**` : `role \`${target.id}\``;
  return message.reply(success(`Removed ${label} from ignored roles.`));
}

async function listIgnoredRoles(message) {
  const roleIds = await getIgnoredRoles(message.guild.id);
  const lines = roleIds.map((id) => formatIgnoredRoleLine(message.guild, id));
  return sendChunkedList(message, 'Ignored Roles', lines);
}

async function handleIgnoreSubcommand(message, rest) {
  const parts = rest.trim().split(/\s+/);
  const kind = parts[0]?.toLowerCase();
  const action = parts[1]?.toLowerCase();
  const arg = parts.slice(2).join(' ').trim();

  if (kind === 'channel') {
    if (action === 'add') return addIgnoredChannelEntry(message, arg);
    if (action === 'remove') return removeIgnoredChannelEntry(message, arg);
    if (action === 'list') return listIgnoredChannels(message);
    return message.reply(error('Usage: `?automod ignore channel add|remove|list`'));
  }

  if (kind === 'role') {
    if (action === 'add') return addIgnoredRoleEntry(message, arg);
    if (action === 'remove') return removeIgnoredRoleEntry(message, arg);
    if (action === 'list') return listIgnoredRoles(message);
    return message.reply(error('Usage: `?automod ignore role add|remove|list`'));
  }

  return message.reply(error('Usage: `?automod ignore channel|role add|remove|list`'));
}

async function handleThresholdSubcommand(message, rest) {
  const parts = rest.trim().split(/\s+/);
  const action = parts[0]?.toLowerCase();
  const arg = parts.slice(1).join(' ').trim();

  if (action === 'show') {
    const settings = await getGuildSettings(message.guild.id);
    const moduleDisabled = await isModuleDisabled(message.guild.id, 'Automod');
    return message.reply({
      embeds: [basicEmbed('Automod Thresholds', formatThresholdShow(settings, { moduleDisabled }))],
    });
  }

  if (action === 'reset') {
    const target = arg.toLowerCase();
    const updates = getThresholdResetUpdates(target);
    if (!updates) {
      return message.reply(error('Usage: `?automod threshold reset caps|spam|mentions|all`'));
    }
    await updateGuildSettings(message.guild.id, updates);
    return message.reply(success(`Reset **${target}** threshold${target === 'all' ? 's' : ''} to defaults.`));
  }

  if (action === 'caps') {
    const result = validateCapsThresholdInput(arg);
    if (!result.ok) return message.reply(error(result.error));
    await updateGuildSetting(message.guild.id, 'caps_threshold', result.value);
    return message.reply(success(
      `Caps threshold set to **${result.value}%** for messages with at least ${CAPS_MIN_LETTERS} letters.`,
    ));
  }

  if (action === 'spam-count') {
    const result = validateSpamCountInput(arg);
    if (!result.ok) return message.reply(error(result.error));
    await updateGuildSetting(message.guild.id, 'spam_threshold', result.value);
    const settings = await getGuildSettings(message.guild.id);
    return message.reply(success(
      `Spam count set to **${result.value}** messages within ${formatSpamWindow(settings.spam_interval)}.`,
    ));
  }

  if (action === 'spam-window') {
    const result = validateSpamWindowInput(arg, parseDuration);
    if (!result.ok) return message.reply(error(result.error));
    await updateGuildSetting(message.guild.id, 'spam_interval', result.value);
    const settings = await getGuildSettings(message.guild.id);
    return message.reply(success(
      `Spam window set to **${formatSpamWindow(result.value)}** (${settings.spam_threshold} messages within window).`,
    ));
  }

  if (action === 'mentions') {
    const result = validateMentionThresholdInput(arg);
    if (!result.ok) return message.reply(error(result.error));
    await updateGuildSetting(message.guild.id, 'mention_threshold', result.value);
    return message.reply(success(
      `Mention threshold set to **${result.value}** user/role mentions per message (@everyone/@here always flagged).`,
    ));
  }

  return message.reply(error(
    'Usage: `?automod threshold caps|spam-count|spam-window|mentions|show|reset`',
  ));
}

async function handleWordSubcommand(message, subargs) {
  const parts = subargs.trim().split(/\s+/);
  const action = parts[0]?.toLowerCase();

  switch (action) {
    case 'add': {
      const mode = parts[1]?.toLowerCase();
      const value = parts.slice(2).join(' ');
      if (!mode || !value.trim()) {
        return message.reply(error('Usage: `?automod word add contains|exact <text>`'));
      }
      return addBannedWords(message, mode, value);
    }
    case 'remove':
      return removeBannedWordEntry(message, parts.slice(1).join(' '));
    case 'list':
      return listBannedWords(message);
    default:
      return message.reply(error('Usage: `?automod word add|remove|list`'));
  }
}

export default {
  name: 'automod',
  description: 'Configure auto-moderation',
  category: 'Automod',
  usage: '?automod [subcommand]',
  async execute(message, args, subcommand, subargs) {
    const denied = await checkAdmin(message);
    if (denied) return message.reply(denied);

    const action = subcommand || 'status';
    const rest = subargs || args.trim();

    switch (action) {
      case 'word':
        return handleWordSubcommand(message, rest);
      case 'banword':
        return addBannedWords(message, 'contains', rest);
      case 'banexact':
        return addBannedWords(message, 'exact', rest);
      case 'unbanword':
        return removeBannedWordEntry(message, rest);
      case 'blacklist': {
        const links = rest.split(',').map((l) => l.trim()).filter(Boolean);
        for (const l of links) await addAutomodLink(message.guild.id, l, 'blacklist');
        return message.reply(success(`Blacklisted links: ${links.join(', ')}`));
      }
      case 'whitelist': {
        const links = rest.split(',').map((l) => l.trim()).filter(Boolean);
        for (const l of links) await addAutomodLink(message.guild.id, l, 'whitelist');
        return message.reply(success(`Whitelisted links: ${links.join(', ')}`));
      }
      case 'ignore':
        return handleIgnoreSubcommand(message, rest);
      case 'ignorechannel':
        return addIgnoredChannelEntry(message, rest.trim(), { legacy: true });
      case 'ignorerole':
        return addIgnoredRoleEntry(message, rest.trim(), { legacy: true });
      case 'ignored': {
        const channelIds = await getIgnoredChannels(message.guild.id);
        const roleIds = await getIgnoredRoles(message.guild.id);
        const channelLines = channelIds.map((id) => formatIgnoredChannelLine(message.guild, id));
        const roleLines = roleIds.map((id) => formatIgnoredRoleLine(message.guild, id));
        const embed = basicEmbed('Automod Ignored', [
          `**Channels (${channelIds.length}):**`,
          channelLines.length ? channelLines.join('\n') : 'None',
          '',
          `**Roles (${roleIds.length}):**`,
          roleLines.length ? roleLines.join('\n') : 'None',
          '',
          `_Use \`?automod ignore channel list\` or \`?automod ignore role list\` for paginated output._`,
        ].join('\n'));
        return message.reply({ embeds: [embed] });
      }
      case 'threshold':
        return handleThresholdSubcommand(message, rest);
      case 'antispam':
        await updateGuildSetting(message.guild.id, 'anti_spam', rest === 'off' ? 0 : 1);
        return message.reply(success(`Anti-spam ${rest === 'off' ? 'disabled' : 'enabled'}.`));
      case 'anticaps':
        await updateGuildSetting(message.guild.id, 'anti_caps', rest === 'off' ? 0 : 1);
        return message.reply(success(`Anti-caps ${rest === 'off' ? 'disabled' : 'enabled'}.`));
      case 'antiinvite':
        await updateGuildSetting(message.guild.id, 'anti_invite', rest === 'off' ? 0 : 1);
        return message.reply(success(`Anti-invite ${rest === 'off' ? 'disabled' : 'enabled'}.`));
      case 'antimention':
        await updateGuildSetting(message.guild.id, 'anti_mention', rest === 'off' ? 0 : 1);
        return message.reply(success(`Anti-mention ${rest === 'off' ? 'disabled' : 'enabled'}.`));
      case 'status': {
        const settings = await getGuildSettings(message.guild.id);
        const moduleDisabled = await isModuleDisabled(message.guild.id, 'Automod');
        const words = await getBannedWords(message.guild.id);
        const blacklist = await getAutomodLinks(message.guild.id, 'blacklist');
        const ignoredChannelCount = (await getIgnoredChannels(message.guild.id)).length;
        const ignoredRoleCount = (await getIgnoredRoles(message.guild.id)).length;
        const inactive = moduleDisabled ? ' (inactive)' : '';
        const embed = basicEmbed('Automod Status', [
          `**Master status:** ${moduleDisabled ? 'Disabled' : 'Enabled'}`,
          moduleDisabled ? '_Individual protections are inactive while the Automod module is disabled._' : '',
          `**Anti-spam:** ${settings.anti_spam ? 'On' : 'Off'}${inactive}`,
          `**Anti-caps:** ${settings.anti_caps ? 'On' : 'Off'}${inactive}`,
          `**Anti-invite:** ${settings.anti_invite ? 'On' : 'Off'}${inactive}`,
          `**Anti-mention:** ${settings.anti_mention ? 'On' : 'Off'}${inactive}`,
          `**Banned words:** ${words.length}${inactive}`,
          `**Blacklisted links:** ${blacklist.length}${inactive}`,
          `**Ignored channels:** ${ignoredChannelCount} — \`?automod ignore channel list\``,
          `**Ignored roles:** ${ignoredRoleCount} — \`?automod ignore role list\``,
          `**Thresholds:** \`?automod threshold show\``,
        ].filter(Boolean).join('\n'));
        return message.reply({ embeds: [embed] });
      }
      default:
        return message.reply(error(
          'Subcommands: word, banword, banexact, unbanword, blacklist, whitelist, ignore, threshold, ignorechannel, ignorerole, ignored, antispam, anticaps, antiinvite, antimention, status',
        ));
    }
  },
};
