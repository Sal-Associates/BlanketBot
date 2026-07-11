import { EmbedBuilder, AuditLogEvent } from 'discord.js';
import { resolveMember, error } from '../../utils/helpers.js';
import { checkMod } from '../../utils/checks.js';

const ACTION_NAMES = {
  [AuditLogEvent.MemberBanAdd]: 'Ban',
  [AuditLogEvent.MemberKick]: 'Kick',
  [AuditLogEvent.MemberUpdate]: 'Member Update',
  [AuditLogEvent.MemberRoleUpdate]: 'Role Update',
  [AuditLogEvent.MessageDelete]: 'Message Delete',
  [AuditLogEvent.MessageBulkDelete]: 'Bulk Delete',
  [AuditLogEvent.ChannelCreate]: 'Channel Create',
  [AuditLogEvent.ChannelDelete]: 'Channel Delete',
  [AuditLogEvent.RoleCreate]: 'Role Create',
  [AuditLogEvent.RoleDelete]: 'Role Delete',
};

export default {
  name: 'audit',
  description: 'Sync Discord audit log entries for a user',
  category: 'Moderation',
  usage: '?audit <user> [limit]',
  async execute(message, args) {
    const denied = await checkMod(message);
    if (denied) return message.reply(denied);

    const parts = args.trim().split(/\s+/);
    const target = resolveMember(message, parts[0]);
    if (!target) return message.reply(error('Usage: `?audit <user> [limit]`'));

    const limit = Math.min(parseInt(parts[1], 10) || 10, 25);

    try {
      const logs = await message.guild.fetchAuditLogs({ limit: 100 });
      const entries = logs.entries
        .filter((e) => e.target?.id === target.id || e.executor?.id === target.id)
        .first(limit);

      if (!entries.length) {
        return message.reply(`No audit log entries found for **${target.user.tag}**.`);
      }

      const lines = entries.map((e) => {
        const action = ACTION_NAMES[e.action] ?? `Action ${e.action}`;
        const executor = e.executor ? e.executor.tag : 'Unknown';
        const when = `<t:${Math.floor(e.createdTimestamp / 1000)}:R>`;
        const reason = e.reason ? ` — ${e.reason}` : '';
        return `**${action}** by ${executor} ${when}${reason}`;
      });

      const embed = new EmbedBuilder()
        .setTitle(`Audit Log: ${target.user.tag}`)
        .setDescription(lines.join('\n'))
        .setColor(0x5865f2)
        .setFooter({ text: 'Source: Discord native audit log' });

      return message.reply({ embeds: [embed] });
    } catch {
      return message.reply(error('Could not fetch audit logs. Bot needs **View Audit Log** permission.'));
    }
  },
};
