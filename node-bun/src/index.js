import { Client, GatewayIntentBits, ActivityType } from 'discord.js';
import { loadCommands } from './handlers/commandLoader.js';
import { handleMessage } from './events/messageCreate.js';
import { handleInteraction } from './events/interactionCreate.js';
import { startScheduler } from './handlers/scheduler.js';
import { validateGuildIdConfig, getConfiguredGuildId } from './utils/guild.js';

import { initializeDatabase, flushDatabaseQueue } from './database/db.js';

const token = process.env.DISCORD_TOKEN;
if (!token) {
  console.error('Missing DISCORD_TOKEN in .env file');
  process.exit(1);
}

validateGuildIdConfig();

await initializeDatabase();

const client = new Client({
  intents: [
    GatewayIntentBits.Guilds,
    GatewayIntentBits.GuildMessages,
    GatewayIntentBits.GuildMembers,
    GatewayIntentBits.MessageContent,
  ],
});

await loadCommands();

client.once('ready', async () => {
  const guildId = getConfiguredGuildId();
  const guild = await client.guilds.fetch(guildId).catch(() => null);

  if (!guild) {
    console.error(`Bot is not a member of the configured guild (GUILD_ID=${guildId})`);
    process.exit(1);
  }

  console.log(`Logged in as ${client.user.tag}`);
  console.log(`Operating in: ${guild.name} (${guild.id})`);
  client.user.setActivity('?help | Moderation', { type: ActivityType.Watching });
  startScheduler(client);
});

client.on('messageCreate', handleMessage);
client.on('interactionCreate', handleInteraction);

let shuttingDown = false;

async function shutdown(signal) {
  if (shuttingDown) return;
  shuttingDown = true;
  console.log(`Received ${signal}, shutting down...`);

  try {
    await flushDatabaseQueue(5000);
  } catch (err) {
    console.error('[shutdown] Failed to flush database queue:', err.message);
  }

  client.destroy();
  process.exit(0);
}

process.on('SIGINT', () => shutdown('SIGINT'));
process.on('SIGTERM', () => shutdown('SIGTERM'));

client.login(token);