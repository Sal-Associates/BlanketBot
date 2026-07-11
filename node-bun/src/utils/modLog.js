import { EmbedBuilder } from 'discord.js';
import { getGuildSettings, updateGuildSetting } from '../database/db.js';

/** Send a live notification to the configured Discord mod-log channel (not a database write). */
export async function sendModLog(guild, { action, target, moderator, reason, caseNumber }) {
  const settings = await getGuildSettings(guild.id);
  if (!settings.mod_log_channel) return true;

  const channel = guild.channels.cache.get(settings.mod_log_channel);
  if (!channel) {
    console.error(`[mod-log channel] Configured channel ${settings.mod_log_channel} not found in guild ${guild.id}`);
    return false;
  }

  const colors = {
    ban: 0xed4245,
    unban: 0x57f287,
    kick: 0xfaa61a,
    mute: 0x5865f2,
    unmute: 0x57f287,
    warn: 0xfee75c,
    softban: 0xed4245,
    note: 0xeb459e,
    lock: 0x95a5a6,
    unlock: 0x57f287,
    purge: 0x99aab5,
    automod: 0xe67e22,
    strike_mute: 0x5865f2,
    strike_ban: 0xed4245,
    strike_mute_failed: 0x5865f2,
    strike_ban_failed: 0xed4245,
    queue_deny: 0xfee75c,
    queue_approve: 0x57f287,
    channel_unlock_skipped: 0xfaa61a,
    channel_unlock_failed: 0xed4245,
    lockdown_enable: 0xed4245,
    lockdown_enable_partial: 0xfaa61a,
    lockdown_disable: 0x57f287,
    lockdown_restore_failed: 0xed4245,
  };

  const title = caseNumber ? `Case #${caseNumber} — ${action.toUpperCase()}` : `Case: ${action.toUpperCase()}`;

  const embed = new EmbedBuilder()
    .setColor(colors[action] ?? 0x5865f2)
    .setTitle(title)
    .addFields(
      { name: 'User', value: `${target} (${target.id})`, inline: true },
      { name: 'Moderator', value: `${moderator}`, inline: true },
      { name: 'Reason', value: reason || 'No reason provided' },
    )
    .setTimestamp();

  try {
    await channel.send({ embeds: [embed] });
    return true;
  } catch (err) {
    console.error(`[mod-log channel] Failed to send ${action} notification:`, err.message);
    return false;
  }
}

export async function getOrCreateMuteRole(guild) {
  const settings = await getGuildSettings(guild.id);
  if (settings.mute_role) {
    const existing = guild.roles.cache.get(settings.mute_role);
    if (existing) return existing;
  }

  let role = guild.roles.cache.find((r) => r.name === 'Muted');
  if (!role) {
    role = await guild.roles.create({
      name: 'Muted',
      color: 0x808080,
      reason: 'Auto-created mute role',
    });

    for (const channel of guild.channels.cache.values()) {
      if (channel.isTextBased?.()) {
        await channel.permissionOverwrites.edit(role, {
          SendMessages: false,
          AddReactions: false,
          Speak: false,
        }).catch(() => {});
      }
    }
  }

  await updateGuildSetting(guild.id, 'mute_role', role.id);
  return role;
}
