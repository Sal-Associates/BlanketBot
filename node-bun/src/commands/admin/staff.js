import {
  addModRole, removeModRole, getModRoles,
  addAdminRole, removeAdminRole, getAdminRoles,
} from '../../database/db.js';
import { resolveRole, success, error, basicEmbed } from '../../utils/helpers.js';
import { checkAdmin } from '../../utils/checks.js';

export default {
  name: 'staff',
  description: 'Manage mod and admin roles',
  category: 'Admin',
  usage: '?staff mod|admin add|del|list [role]',
  async execute(message, args, subcommand, subargs) {
    const denied = await checkAdmin(message);
    if (denied) return message.reply(denied);

    const parts = (subargs || args.trim()).split(/\s+/);
    const type = subcommand?.toLowerCase();
    const action = parts[0]?.toLowerCase();
    const roleArg = parts.slice(1).join(' ') || parts[0];

    if (!type || !['mod', 'admin'].includes(type)) {
      return message.reply(error('Usage: `?staff mod|admin add|del|list [role]`'));
    }

    const isMod = type === 'mod';
    const label = isMod ? 'Moderator' : 'Admin';

    if (action === 'list' || (!action && !parts[0])) {
      const roleIds = isMod ? await getModRoles(message.guild.id) : await getAdminRoles(message.guild.id);
      if (!roleIds.length) return message.reply(error(`No ${label.toLowerCase()} roles configured.`));
      const roles = roleIds.map((id) => message.guild.roles.cache.get(id)).filter(Boolean);
      return message.reply({ embeds: [basicEmbed(`${label} Roles`, roles.map((r) => `• ${r}`).join('\n'))] });
    }

    const role = resolveRole(message.guild, action === 'add' || action === 'del' ? parts[1] : roleArg);
    if (!role && action !== 'list') {
      return message.reply(error(`Usage: \`?staff ${type} add|del|list [role]\``));
    }

    switch (action) {
      case 'add':
        await (isMod ? addModRole : addAdminRole)(message.guild.id, role.id);
        return message.reply(success(`**${role.name}** is now a ${label.toLowerCase()} role.`));
      case 'del':
        await (isMod ? removeModRole : removeAdminRole)(message.guild.id, role.id);
        return message.reply(success(`**${role.name}** removed from ${label.toLowerCase()} roles.`));
      default:
        return message.reply(error(`Usage: \`?staff ${type} add|del|list [role]\``));
    }
  },
};
