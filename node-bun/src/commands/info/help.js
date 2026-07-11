import { EmbedBuilder } from 'discord.js';
import { commands } from '../../handlers/commandLoader.js';

function getCategories() {
  const categories = {};
  for (const [, cmd] of commands) {
    if (!categories[cmd.category]) categories[cmd.category] = [];
    if (!categories[cmd.category].includes(cmd.name)) {
      categories[cmd.category].push(cmd.name);
    }
  }
  return categories;
}

export default {
  name: 'help',
  description: 'Show all commands',
  category: 'Info',
  usage: '?help [command]',
  async execute(message, args) {
    const query = args.trim().toLowerCase();

    if (query) {
      const cmd = commands.get(query);
      if (!cmd) return message.reply(`Unknown command: \`${query}\``);

      const embed = new EmbedBuilder()
        .setTitle(`?${cmd.name}`)
        .setDescription(cmd.description)
        .addFields(
          { name: 'Category', value: cmd.category, inline: true },
          { name: 'Usage', value: `\`${cmd.usage ?? `?${cmd.name}`}\`` },
        )
        .setColor(0x5865f2);

      return message.reply({ embeds: [embed] });
    }

    const embed = new EmbedBuilder()
      .setTitle('Mod Bot Commands')
      .setDescription('Moderation-focused bot. Use `?help [command]` for details.')
      .setColor(0x5865f2);

    for (const [category, cmds] of Object.entries(getCategories()).sort()) {
      embed.addFields({ name: category, value: cmds.map((c) => `\`${c}\``).join(', '), inline: false });
    }

    return message.reply({ embeds: [embed] });
  },
};
