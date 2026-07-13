import { resolveMember, success, error, LINK_REGEX, INVITE_REGEX } from '../../utils/helpers.js';
import { checkMod } from '../../utils/checks.js';
import { sendModLog } from '../../utils/modLog.js';
import { createCase } from '../../database/db.js';

const MAX_PURGE = 100;
const MAX_AGE_MS = 14 * 24 * 60 * 60 * 1000;

function isOld(msg) {
  return Date.now() - msg.createdTimestamp > MAX_AGE_MS;
}

async function bulkDelete(channel, messages) {
  const deletable = messages.filter((m) => !isOld(m));
  if (!deletable.size) return 0;

  if (deletable.size === 1) {
    await deletable.first().delete();
    return 1;
  }

  const deleted = await channel.bulkDelete(deletable, true);
  return deleted.size;
}

export default {
  name: 'purge',
  description: 'Delete messages from a channel',
  category: 'Purge',
  usage: '?purge [count] or ?purge [filter] [args]',
  async execute(message, args, subcommand, subargs) {
    const denied = await checkMod(message);
    if (denied) return message.reply(denied);

    const PURGE_FILTERS = ['user', 'match', 'not', 'startswith', 'endswith', 'links', 'invites', 'images', 'mentions', 'embeds', 'bots', 'humans', 'text'];

    let filter = subcommand || 'any';
    let filterArgs = subcommand ? subargs : args.trim();

    if (filter && !PURGE_FILTERS.includes(filter) && /^\d+$/.test(filter)) {
      filterArgs = filter;
      filter = 'any';
    }

    const parts = filterArgs.split(/\s+/);
    const count = Math.min(parseInt(parts[parts.length - 1], 10) || 100, MAX_PURGE);

    const fetched = await message.channel.messages.fetch({ limit: 100 });
    let toDelete = fetched.filter((m) => m.id !== message.id);

    switch (filter) {
      case 'any':
      case undefined: {
        const n = parseInt(filterArgs, 10) || 100;
        toDelete = toDelete.first(Math.min(n, MAX_PURGE));
        break;
      }
      case 'user': {
        const user = resolveMember(message, parts[0]);
        if (!user) return message.reply(error('Usage: `?purge user [user] [count]`'));
        toDelete = toDelete.filter((m) => m.author.id === user.id).first(count);
        break;
      }
      case 'match': {
        const text = parts.slice(0, -1).join(' ') || parts[0];
        toDelete = toDelete.filter((m) => m.content.includes(text)).first(count);
        break;
      }
      case 'not': {
        const text = parts.slice(0, -1).join(' ') || parts[0];
        toDelete = toDelete.filter((m) => !m.content.includes(text)).first(count);
        break;
      }
      case 'startswith': {
        const text = parts.slice(0, -1).join(' ') || parts[0];
        toDelete = toDelete.filter((m) => m.content.startsWith(text)).first(count);
        break;
      }
      case 'endswith': {
        const text = parts.slice(0, -1).join(' ') || parts[0];
        toDelete = toDelete.filter((m) => m.content.endsWith(text)).first(count);
        break;
      }
      case 'links':
        toDelete = toDelete.filter((m) => LINK_REGEX.test(m.content)).first(count);
        break;
      case 'invites':
        toDelete = toDelete.filter((m) => INVITE_REGEX.test(m.content)).first(count);
        break;
      case 'images':
        toDelete = toDelete.filter((m) => m.attachments.some((a) => a.contentType?.startsWith('image/'))).first(count);
        break;
      case 'mentions':
        toDelete = toDelete.filter((m) => m.mentions.users.size > 0).first(count);
        break;
      case 'embeds':
        toDelete = toDelete.filter((m) => m.embeds.length > 0).first(count);
        break;
      case 'bots':
        toDelete = toDelete.filter((m) => m.author.bot).first(count);
        break;
      case 'humans':
        toDelete = toDelete.filter((m) => !m.author.bot).first(count);
        break;
      case 'text':
        toDelete = toDelete.filter((m) => m.content && !m.attachments.size && !m.embeds.length).first(count);
        break;
      default:
        return message.reply(error('Filters: any, user, match, not, startswith, endswith, links, invites, images, mentions, embeds, bots, humans, text'));
    }

    const deleted = await bulkDelete(message.channel, toDelete);
    const caseNum = await createCase(
      message.guild.id,
      message.channel.id,
      message.author.id,
      'purge',
      `Purged ${deleted} messages (${filter})`
    );
    await sendModLog(message.guild, {
      action: 'purge',
      target: { id: message.channel.id, toString: () => message.channel.toString() },
      moderator: message.author,
      reason: `Purged ${deleted} messages (${filter})`,
      caseNumber: caseNum,
    });

    const reply = await message.reply(success(`Deleted **${deleted}** message(s).`));
    setTimeout(() => reply.delete().catch(() => {}), 5000);
  },
};
