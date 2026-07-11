export const commands = new Map();

export function registerCommand(name, command) {
  commands.set(name.toLowerCase(), command);
  if (command.aliases) {
    for (const alias of command.aliases) {
      commands.set(alias.toLowerCase(), command);
    }
  }
}

export async function loadCommands() {
  const modules = [
    '../commands/admin/staff.js',
    '../commands/admin/strike.js',
    '../commands/admin/modqueue.js',
    '../commands/admin/prefix.js',
    '../commands/admin/module.js',
    '../commands/admin/modules.js',
    '../commands/admin/modlog.js',
    '../commands/moderation/mod.js',
    '../commands/moderation/warn.js',
    '../commands/moderation/note.js',
    '../commands/moderation/channel.js',
    '../commands/moderation/case.js',
    '../commands/moderation/audit.js',
    '../commands/purge/purge.js',
    '../commands/automod/automod.js',
    '../commands/info/info.js',
    '../commands/info/whois.js',
    '../commands/info/help.js',
  ];

  for (const mod of modules) {
    const imported = await import(mod);
    registerCommand(imported.default.name, imported.default);
  }
}
