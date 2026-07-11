import { updateGuildSetting } from '../../database/db.js';
import { resolveChannel, success, error } from '../../utils/helpers.js';
import { checkAdmin } from '../../utils/checks.js';

export default {
  name: 'modlog',
  description: 'Set the moderation log channel',
  category: 'Admin',
  usage: '?modlog [channel]',
  async execute(message, args) {
    const denied = await checkAdmin(message);
    if (denied) return message.reply(denied);

    const channel = resolveChannel(message.guild, args.trim()) ?? message.channel;
    if (!channel.isTextBased()) return message.reply(error('Please provide a text channel.'));

    await updateGuildSetting(message.guild.id, 'mod_log_channel', channel.id);
    return message.reply(success(`Mod log channel set to ${channel}.`));
  },
};
