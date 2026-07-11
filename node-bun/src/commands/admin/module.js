import { toggleModule } from '../../database/db.js';
import { success, error } from '../../utils/helpers.js';
import { checkAdmin } from '../../utils/checks.js';

const VALID_MODULES = ['Automod'];

export default {
  name: 'module',
  description: 'Enable or disable a module',
  category: 'Admin',
  usage: '?module [module name]',
  async execute(message, args) {
    const denied = await checkAdmin(message);
    if (denied) return message.reply(denied);

    const moduleName = args.trim();
    const match = VALID_MODULES.find((m) => m.toLowerCase() === moduleName.toLowerCase());
    if (!match) {
      return message.reply(error(`Invalid module. Available: ${VALID_MODULES.join(', ')}`));
    }

    const nowDisabled = await toggleModule(message.guild.id, match);
    return message.reply(success(`**${match}** is now **${nowDisabled ? 'disabled' : 'enabled'}**.`));
  },
};
