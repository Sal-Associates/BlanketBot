import { isModuleDisabled } from '../../database/db.js';
import { basicEmbed } from '../../utils/helpers.js';

const ALL_MODULES = ['Automod'];

export default {
  name: 'modules',
  description: 'List all modules and their status',
  category: 'Admin',
  usage: '?modules',
  async execute(message) {
    const lines = await Promise.all(ALL_MODULES.map(async (m) => {
      const disabled = await isModuleDisabled(message.guild.id, m);
      const status = disabled ? '🔴 Disabled' : '🟢 Enabled';
      return `**${m}** — ${status}`;
    }));

    const embed = basicEmbed('Server Modules', lines.join('\n'));
    return message.reply({ embeds: [embed] });
  },
};