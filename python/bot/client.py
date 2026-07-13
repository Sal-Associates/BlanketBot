"""Discord client bootstrap."""

from __future__ import annotations

import logging
from pathlib import Path

import discord
from discord.ext import commands

from bot.cogs.core.messages import dynamic_prefix
from bot.config import Settings
from bot.database.connection import Database
from bot.database.migrations import run_migrations

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"

COG_EXTENSIONS: tuple[str, ...] = (
    "bot.cogs.foundation",
    "bot.cogs.core.messages",
    "bot.cogs.admin.prefix",
    "bot.cogs.admin.staff",
    "bot.cogs.admin.module",
    "bot.cogs.admin.modlog",
    "bot.cogs.admin.modqueue",
    "bot.cogs.admin.strike",
    "bot.cogs.admin.muterole",
    "bot.cogs.moderation.mod",
    "bot.cogs.moderation.warn",
    "bot.cogs.moderation.note",
    "bot.cogs.moderation.case",
    "bot.cogs.moderation.channel",
    "bot.cogs.moderation.audit",
    "bot.cogs.moderation.purge",
    "bot.cogs.automod.automod",
    "bot.cogs.info.help",
    "bot.cogs.info.info",
    "bot.cogs.info.whois",
)


class ModBot(commands.Bot):
    """Single-guild prefix-command moderation bot."""

    def __init__(self, settings: Settings, database: Database) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        super().__init__(command_prefix=dynamic_prefix, intents=intents, help_command=None)
        self.settings = settings
        self.database = database

    async def setup_hook(self) -> None:
        await self.database.connect()
        await run_migrations(self.database, MIGRATIONS_DIR)
        for extension in COG_EXTENSIONS:
            await self.load_extension(extension)

    async def on_ready(self) -> None:
        guild = self.get_guild(int(self.settings.guild_id))
        if guild is None:
            logger.error(
                "Bot is not a member of configured guild GUILD_ID=%s",
                self.settings.guild_id,
            )
            await self.close()
            return
        logger.info("Logged in as %s", self.user)
        logger.info("Operating in: %s (%s)", guild.name, guild.id)
        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="?help | Moderation")
        )

        from bot.scheduler.runner import start_scheduler
        from bot.views.mod_queue import register_persistent_mod_queue_views

        await register_persistent_mod_queue_views(self)
        await start_scheduler(self)

    async def close(self) -> None:
        from bot.scheduler.runner import stop_scheduler

        stop_scheduler()
        await self.database.close()
        await super().close()


def build_bot(settings: Settings) -> ModBot:
    database = Database(settings.database_path)
    return ModBot(settings, database)
