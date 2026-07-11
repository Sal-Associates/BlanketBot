import { EmbedBuilder } from 'discord.js';
import { resolveMember, resolveChannel, basicEmbed, error } from '../../utils/helpers.js';

export default {
  name: 'info',
  description: 'Server, user, channel, and avatar info',
  category: 'Info',
  usage: '?info server|user|channel|avatar [args]',
  async execute(message, args, subcommand, subargs) {
    const action = subcommand?.toLowerCase() || 'server';
    const rest = subargs || args.trim();

    switch (action) {
      case 'server': {
        const { guild } = message;
        const embed = new EmbedBuilder()
          .setTitle(guild.name)
          .setThumbnail(guild.iconURL())
          .setColor(0x5865f2)
          .addFields(
            { name: 'Owner', value: `<@${guild.ownerId}>`, inline: true },
            { name: 'Members', value: `${guild.memberCount}`, inline: true },
            { name: 'Humans / Bots', value: `${guild.members.cache.filter((m) => !m.user.bot).size} / ${guild.members.cache.filter((m) => m.user.bot).size}`, inline: true },
            { name: 'Channels', value: `${guild.channels.cache.size}`, inline: true },
            { name: 'Roles', value: `${guild.roles.cache.size}`, inline: true },
            { name: 'Boost Level', value: `${guild.premiumTier}`, inline: true },
            { name: 'Created', value: `<t:${Math.floor(guild.createdTimestamp / 1000)}:R>`, inline: true },
          );
        if (guild.description) embed.setDescription(guild.description);
        return message.reply({ embeds: [embed] });
      }
      case 'user': {
        const target = resolveMember(message, rest.trim()) ?? message.member;
        const user = target.user;
        const embed = new EmbedBuilder()
          .setTitle(user.tag)
          .setThumbnail(user.displayAvatarURL({ size: 256 }))
          .setColor(target.displayHexColor || 0x5865f2)
          .addFields(
            { name: 'ID', value: user.id, inline: true },
            { name: 'Joined', value: target.joinedAt ? `<t:${Math.floor(target.joinedTimestamp / 1000)}:R>` : 'Unknown', inline: true },
            { name: 'Created', value: `<t:${Math.floor(user.createdTimestamp / 1000)}:R>`, inline: true },
            { name: 'Roles', value: target.roles.cache.filter((r) => r.id !== message.guild.id).map((r) => r.toString()).join(' ') || 'None' },
          );
        return message.reply({ embeds: [embed] });
      }
      case 'channel': {
        const channel = resolveChannel(message.guild, rest.trim()) ?? message.channel;
        const embed = basicEmbed(`#${channel.name}`, [
          `**ID:** ${channel.id}`,
          `**Type:** ${channel.type}`,
          `**Created:** <t:${Math.floor(channel.createdTimestamp / 1000)}:R>`,
          channel.topic ? `**Topic:** ${channel.topic}` : null,
          channel.rateLimitPerUser ? `**Slowmode:** ${channel.rateLimitPerUser}s` : null,
        ].filter(Boolean).join('\n'));
        return message.reply({ embeds: [embed] });
      }
      case 'avatar': {
        const target = resolveMember(message, rest.trim()) ?? message.member;
        const url = target.user.displayAvatarURL({ size: 512 });
        return message.reply({ content: `**${target.user.tag}**'s avatar:`, embeds: [{ image: { url } }] });
      }
      default:
        return message.reply(error('Usage: `?info server|user|channel|avatar`'));
    }
  },
};
