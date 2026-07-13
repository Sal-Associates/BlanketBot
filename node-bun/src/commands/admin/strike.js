import { getGuildSettings, updateGuildSetting, updateGuildSettings } from '../../database/db.js';
import { success, error, basicEmbed } from '../../utils/helpers.js';
import { checkAdmin } from '../../utils/checks.js';

export default {
  name: 'strike',
  description: 'Configure strike escalation thresholds',
  category: 'Admin',
  usage: '?strike status|set|on|off [muteAt] [banAt]',
  async execute(message, args, subcommand, subargs) {
    const denied = await checkAdmin(message);
    if (denied) return message.reply(denied);

    const action = subcommand?.toLowerCase() || 'status';
    const rest = subargs || args.trim();
    const settings = await getGuildSettings(message.guild.id);

    switch (action) {
      case 'status':
        return message.reply({
          embeds: [basicEmbed('Strike Escalation', [
            `**Enabled:** ${settings.strike_enabled ? 'Yes' : 'No'}`,
            `**Auto-mute at:** ${settings.strike_mute_at ?? 3} warnings`,
            `**Auto-ban at:** ${settings.strike_ban_at ?? 5} warnings`,
            '',
            'When a user reaches the mute threshold, they are automatically muted.',
            'When they reach the ban threshold, they are automatically banned.',
          ].join('\n'))],
        });
      case 'set': {
        const parts = rest.split(/\s+/);
        const muteAt = parseInt(parts[0], 10);
        const banAt = parseInt(parts[1], 10);
        if (!muteAt || !banAt || muteAt >= banAt) {
          return message.reply(error('Usage: `?strike set <muteAt> <banAt>` — mute must be less than ban (e.g. 3 5)'));
        }
        await updateGuildSettings(message.guild.id, {
          strike_mute_at: muteAt,
          strike_ban_at: banAt,
          strike_enabled: 1,
        });
        return message.reply(success(`Strike escalation set: mute at **${muteAt}**, ban at **${banAt}** warnings.`));
      }
      case 'on':
        await updateGuildSetting(message.guild.id, 'strike_enabled', 1);
        return message.reply(success('Strike escalation **enabled**.'));
      case 'off':
        await updateGuildSetting(message.guild.id, 'strike_enabled', 0);
        return message.reply(success('Strike escalation **disabled**.'));
      default:
        return message.reply(error('Usage: `?strike status|set|on|off`'));
    }
  },
};
