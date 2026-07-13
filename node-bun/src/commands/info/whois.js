import { EmbedBuilder } from 'discord.js';
import { resolveMember, error } from '../../utils/helpers.js';
import { getWarnings, getNotes, getCasesForUser } from '../../database/db.js';
import { formatDate } from '../../utils/time.js';

export default {
  name: 'whois',
  description: 'Get user information and mod history',
  category: 'Info',
  usage: '?whois [user]',
  async execute(message, args) {
    const target = resolveMember(message, args.trim()) ?? message.member;
    const user = target.user;

    const warnings = await getWarnings(message.guild.id, target.id);
    const notes = await getNotes(message.guild.id, target.id);
    const cases = await getCasesForUser(message.guild.id, target.id, 5);

    const embed = new EmbedBuilder()
      .setTitle(user.tag)
      .setThumbnail(user.displayAvatarURL({ size: 256 }))
      .setColor(target.displayHexColor || 0x5865f2)
      .addFields(
        { name: 'ID', value: user.id, inline: true },
        { name: 'Joined', value: target.joinedAt ? `<t:${Math.floor(target.joinedTimestamp / 1000)}:R>` : 'Unknown', inline: true },
        { name: 'Created', value: `<t:${Math.floor(user.createdTimestamp / 1000)}:R>`, inline: true },
        { name: 'Roles', value: target.roles.cache.filter((r) => r.id !== message.guild.id).map((r) => r.toString()).join(' ') || 'None' },
        { name: 'Warnings', value: `${warnings.length}`, inline: true },
        { name: 'Notes', value: `${notes.length}`, inline: true },
      );

    if (cases.length) {
      embed.addFields({
        name: 'Recent Cases',
        value: cases.map((c) => `**#${c.case_number}** ${c.action} — ${c.reason || 'N/A'} (${formatDate(c.created_at)})`).join('\n'),
      });
    }

    return message.reply({ embeds: [embed] });
  },
};
