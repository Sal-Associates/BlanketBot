const GUILD_ID = process.env.GUILD_ID?.trim();

export function getConfiguredGuildId() {
  return GUILD_ID;
}

export function isConfiguredGuild(guildId) {
  return guildId === GUILD_ID;
}

export function validateGuildIdConfig() {
  if (!GUILD_ID) {
    console.error('Missing GUILD_ID in .env file');
    process.exit(1);
  }

  if (!/^\d+$/.test(GUILD_ID)) {
    console.error('GUILD_ID must contain only digits');
    process.exit(1);
  }

  if (!/^\d{17,20}$/.test(GUILD_ID)) {
    console.error('GUILD_ID does not look like a valid Discord snowflake (expected 17–20 digits)');
    process.exit(1);
  }

  return GUILD_ID;
}
