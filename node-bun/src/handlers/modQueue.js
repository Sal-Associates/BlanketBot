import { EmbedBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle } from 'discord.js';
import {
  getGuildSettings,
  addModQueueEntry,
  setModQueueMessageId,
} from '../database/db.js';

export async function sendToModQueue(message, reason) {
  try {
    const settings = await getGuildSettings(message.guild.id);
    if (!settings.mod_queue_enabled || !settings.mod_queue_channel) return false;

    const queueChannel = message.guild.channels.cache.get(settings.mod_queue_channel);
    if (!queueChannel?.isTextBased()) return false;

    await message.delete().catch(() => {});

    const entry = await addModQueueEntry(
      message.guild.id,
      message.channel.id,
      message.author.id,
      message.content.slice(0, 1000),
      reason
    );

    const embed = new EmbedBuilder()
      .setTitle('Automod Flag — Review Required')
      .setColor(0xe67e22)
      .addFields(
        { name: 'User', value: `${message.author} (\`${message.author.id}\`)`, inline: true },
        { name: 'Channel', value: `${message.channel}`, inline: true },
        { name: 'Violation', value: reason },
        { name: 'Message Content', value: message.content.slice(0, 1000) || '*empty*' },
      )
      .setTimestamp();

    const row = new ActionRowBuilder().addComponents(
      new ButtonBuilder()
        .setCustomId(`queue_approve_${entry.id}`)
        .setLabel('Approve (false positive)')
        .setStyle(ButtonStyle.Success),
      new ButtonBuilder()
        .setCustomId(`queue_deny_${entry.id}`)
        .setLabel('Deny & Warn')
        .setStyle(ButtonStyle.Danger),
    );

    const queueMsg = await queueChannel.send({ embeds: [embed], components: [row] });
    await setModQueueMessageId(entry.id, queueMsg.id);
    return true;
  } catch (err) {
    console.error('[modQueue] Database error:', err.message);
    return false;
  }
}
