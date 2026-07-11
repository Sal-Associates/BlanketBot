import { updateGuildSetting, updateGuildSettings, getGuildSettings } from '../../database/db.js';
import { resolveChannel, success, error, basicEmbed } from '../../utils/helpers.js';
import { checkAdmin } from '../../utils/checks.js';

export default {
  name: 'modqueue',
  description: 'Configure the automod review queue',
  category: 'Admin',
  usage: '?modqueue [#channel] or ?modqueue off|status',
  async execute(message, args, subcommand, subargs) {
    const denied = await checkAdmin(message);
    if (denied) return message.reply(denied);

    const first = (subcommand || args.trim().split(/\s+/)[0] || '').toLowerCase();

    if (first === 'off') {
      await updateGuildSetting(message.guild.id, 'mod_queue_enabled', 0);
      return message.reply(success('Mod queue **disabled**. Automod will auto-delete messages again.'));
    }

    if (first === 'status') {
      const settings = await getGuildSettings(message.guild.id);
      const ch = settings.mod_queue_channel ? `<#${settings.mod_queue_channel}>` : 'Not set';
      return message.reply({
        embeds: [basicEmbed('Mod Queue', [
          `**Enabled:** ${settings.mod_queue_enabled ? 'Yes' : 'No'}`,
          `**Channel:** ${ch}`,
          '',
          'When enabled, flagged messages are sent to the queue for mod review instead of being silently deleted.',
        ].join('\n'))],
      });
    }

    const channelInput = subcommand?.match(/^<#/) ? subcommand : (subargs || args.trim());
    const channel = resolveChannel(message.guild, channelInput) ?? message.channel;
    if (!channel.isTextBased()) return message.reply(error('Provide a text channel.'));

    await updateGuildSettings(message.guild.id, {
      mod_queue_channel: channel.id,
      mod_queue_enabled: 1,
    });
    return message.reply(success(`Mod queue enabled in ${channel}. Flagged messages will appear there for review.`));
  },
};
