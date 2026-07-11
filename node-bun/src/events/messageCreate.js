import { getGuildSettings } from '../database/db.js';
import { commands } from '../handlers/commandLoader.js';
import { parseArgs } from '../utils/helpers.js';
import { handleAutomod } from '../handlers/automodHandler.js';
import { isConfiguredGuild } from '../utils/guild.js';

export async function handleMessage(message) {
  if (!message.guild || message.author.bot) return;
  if (!isConfiguredGuild(message.guild.id)) return;

  let settings;
  try {
    settings = await getGuildSettings(message.guild.id);
  } catch (err) {
    console.error('[messageCreate] Database read failed:', err.message);
    return;
  }

  const prefix = settings.prefix || '?';

  if (message.mentions.users.has(message.client.user.id) && !message.content.startsWith(prefix)) {
    return message.reply(`My prefix is \`${prefix}\` — use \`${prefix}help\` for commands.`);
  }

  if (!message.content.startsWith(prefix)) {
    try {
      await handleAutomod(message);
    } catch (err) {
      console.error('[automod] Database error:', err.message);
    }
    return;
  }

  const { command, args, subcommand, subargs } = parseArgs(message.content, prefix);
  if (!command) return;

  const cmd = commands.get(command);
  if (cmd) {
    try {
      await cmd.execute(message, args, subcommand, subargs);
    } catch (err) {
      console.error(`Error in ${command}:`, err.message);
      await message.reply('An error occurred while running that command.').catch(() => {});
    }
    return;
  }

  try {
    await handleAutomod(message);
  } catch (err) {
    console.error('[automod] Database error:', err.message);
  }
}
