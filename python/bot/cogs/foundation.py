"""Foundation cog — single-guild guard and queue interactions."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot.config import Settings
from bot.services.guild_guard import reject_foreign_guild
from bot.views.mod_queue import handle_mod_queue_interaction

logger = logging.getLogger(__name__)


class FoundationCog(commands.Cog):
    """Validates guild scope and handles queue button interactions."""

    def __init__(self, bot: commands.Bot, settings: Settings) -> None:
        self.bot = bot
        self.settings = settings

    async def cog_check(self, ctx: commands.Context[commands.Bot]) -> bool:
        if ctx.guild is None:
            return False
        if reject_foreign_guild(ctx.guild, self.settings.guild_id):
            logger.debug(
                "Ignored command from foreign guild %s (configured %s)",
                ctx.guild.id,
                self.settings.guild_id,
            )
            return False
        return True

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            if interaction.type is discord.InteractionType.component:
                await interaction.response.send_message(
                    "This bot only operates in its configured server.",
                    ephemeral=True,
                )
            return
        if reject_foreign_guild(interaction.guild, self.settings.guild_id):
            if interaction.type is discord.InteractionType.component:
                await interaction.response.send_message(
                    "This bot only operates in its configured server.",
                    ephemeral=True,
                )
            return

        if interaction.type is discord.InteractionType.component:
            handled = await handle_mod_queue_interaction(
                interaction,
                database=self.bot.database,  # type: ignore[attr-defined]
                settings=self.settings,
            )
            if handled:
                return


async def setup(bot: commands.Bot) -> None:
    settings: Settings = bot.settings  # type: ignore[attr-defined]
    await bot.add_cog(FoundationCog(bot, settings))
