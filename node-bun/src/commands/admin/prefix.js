import { updateGuildSetting } from '../../database/db.js';
import { success, error } from '../../utils/helpers.js';
import { checkAdmin } from '../../utils/checks.js';

export default {
  name: 'prefix',
  description: 'Change the bot prefix',
  category: 'Admin',
  usage: '?prefix [new prefix]',
  async execute(message, args) {
    const denied = await checkAdmin(message);
    if (denied) return message.reply(denied);

    const newPrefix = args.trim();
    if (!newPrefix || newPrefix.length > 5) {
      return message.reply(error('Please provide a prefix (max 5 characters).'));
    }

    await updateGuildSetting(message.guild.id, 'prefix', newPrefix);
    return message.reply(success(`Prefix changed to \`${newPrefix}\``));
  },
};
