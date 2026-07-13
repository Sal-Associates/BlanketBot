"""Message routing — dynamic prefix, mention discovery, automod hook."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot.automod.handler import handle_automod
from bot.config import Settings
from bot.constants import DEFAULT_PREFIX
from bot.database.repositories.guild_settings import GuildSettingsRepository
from bot.services.guild_guard import reject_foreign_guild
from bot.services.prefix import get_prefix

logger = logging.getLogger(__name__)


class MessagesCog(commands.Cog):
    """Dynamic prefix resolution and non-command automod processing."""

    def __init__(self, bot: commands.Bot, settings: Settings) -> None:
        self.bot = bot
        self.settings = settings
        self._guild_settings = GuildSettingsRepository(bot.database)  # type: ignore[attr-defined]

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        if reject_foreign_guild(message.guild, self.settings.guild_id):
            return

        prefix = await get_prefix(str(message.guild.id), self._guild_settings)
        content = message.content

        if self.bot.user and self.bot.user in message.mentions and not content.startswith(prefix):
            await message.reply(f"My prefix is `{prefix}` — use `{prefix}help` for commands.")
            return

        ctx = await self.bot.get_context(message)
        if ctx.valid:
            return

        if not content.startswith(prefix):
            try:
                await handle_automod(
                    message,
                    bot=self.bot,
                    database=self.bot.database,  # type: ignore[attr-defined]
                    settings=self.settings,
                )
            except Exception as exc:
                logger.error("[automod] Database error: %s", exc)
            return

        try:
            await handle_automod(
                message,
                bot=self.bot,
                database=self.bot.database,  # type: ignore[attr-defined]
                settings=self.settings,
            )
        except Exception as exc:
            logger.error("[automod] Database error: %s", exc)


async def dynamic_prefix(bot: commands.Bot, message: discord.Message) -> list[str]:
    if message.guild is None:
        return [DEFAULT_PREFIX]
    repo = GuildSettingsRepository(bot.database)  # type: ignore[attr-defined]
    prefix = await get_prefix(str(message.guild.id), repo)
    return [prefix]


async def setup(bot: commands.Bot) -> None:
    settings: Settings = bot.settings  # type: ignore[attr-defined]
    await bot.add_cog(MessagesCog(bot, settings))
