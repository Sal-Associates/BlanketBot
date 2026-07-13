"""?modlog — set the live mod-log channel."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.checks.decorators import administrator_required
from bot.cogs.deps import CogRepos
from bot.utils.helpers import error, success
from bot.utils.resolvers import resolve_channel


class ModLogCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repos = CogRepos(bot)

    @commands.command(name="modlog")
    @administrator_required()
    async def modlog(self, ctx: commands.Context[commands.Bot], *, channel_arg: str | None = None) -> None:
        channel = resolve_channel(ctx.guild, channel_arg) if channel_arg else ctx.channel  # type: ignore[arg-type]
        if channel is None or not isinstance(channel, discord.TextChannel | discord.Thread):
            await ctx.reply(error("Please provide a text channel."))
            return
        await self.repos.guild_settings.update(str(ctx.guild.id), mod_log_channel_id=str(channel.id))  # type: ignore[union-attr]
        await ctx.reply(success(f"Mod log channel set to {channel}."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModLogCog(bot))
