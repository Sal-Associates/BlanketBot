import { resolveMember, success, error, basicEmbed } from '../../utils/helpers.js';
import { checkMod } from '../../utils/checks.js';
import { addNote, getNotes, deleteNote, updateNote } from '../../database/db.js';
import { formatDate } from '../../utils/time.js';

export default {
  name: 'note',
  description: 'Staff notes: add, list, edit, del',
  category: 'Moderation',
  usage: '?note add|list|edit|del [args]',
  async execute(message, args, subcommand, subargs) {
    const denied = await checkMod(message);
    if (denied) return message.reply(denied);

    const action = subcommand?.toLowerCase() || 'add';
    const rest = subargs || args.trim();

    switch (action) {
      case 'add': {
        const parts = rest.split(/\s+/);
        const target = resolveMember(message, parts[0]);
        const content = parts.slice(1).join(' ');
        if (!target || !content) return message.reply(error('Usage: `?note add <user> <text>`'));
        const noteId = await addNote(message.guild.id, target.id, message.author.id, content);
        return message.reply(success(`Added note #${noteId} for **${target.user.tag}**.`));
      }
      case 'list': {
        const target = resolveMember(message, rest.trim());
        if (!target) return message.reply(error('Usage: `?note list <user>`'));
        const notes = await getNotes(message.guild.id, target.id);
        if (!notes.length) return message.reply(error(`No notes for **${target.user.tag}**.`));
        const lines = notes.map((n) => `**#${n.id}** — ${n.content} (${formatDate(n.created_at)})`);
        return message.reply({ embeds: [basicEmbed(`Notes: ${target.user.tag}`, lines.join('\n'), 0xeb459e)] });
      }
      case 'edit': {
        const parts = rest.split(/\s+/);
        const id = parseInt(parts[0]?.replace('#', ''), 10);
        const content = parts.slice(1).join(' ');
        if (!id || !content) return message.reply(error('Usage: `?note edit <note ID> <text>`'));
        if (!(await updateNote(id, content)).changes) return message.reply(error('Note not found.'));
        return message.reply(success(`Updated note #${id}.`));
      }
      case 'del': {
        const id = parseInt(rest.trim().replace('#', ''), 10);
        if (!id) return message.reply(error('Usage: `?note del <note ID>`'));
        if (!(await deleteNote(id)).changes) return message.reply(error('Note not found.'));
        return message.reply(success(`Deleted note #${id}.`));
      }
      default:
        return message.reply(error('Usage: `?note add|list|edit|del`'));
    }
  },
};
