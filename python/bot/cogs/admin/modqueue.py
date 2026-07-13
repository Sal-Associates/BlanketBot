"""?modqueue — configure the automod review queue."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.checks.decorators import administrator_required
from bot.cogs.deps import CogRepos
from bot.utils.helpers import basic_embed, error, success
from bot.utils.resolvers import resolve_channel


class ModQueueCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repos = CogRepos(bot)

    @commands.group(name="modqueue", invoke_without_command=True)
    @administrator_required()
    async def modqueue(self, ctx: commands.Context[commands.Bot], *, channel_arg: str | None = None) -> None:
        if channel_arg is None:
            await ctx.reply(error("Usage: `?modqueue [#channel]` · `?modqueue off` · `?modqueue status`"))
            return
        channel = resolve_channel(ctx.guild, channel_arg) or ctx.channel  # type: ignore[arg-type]
        if not isinstance(channel, discord.TextChannel | discord.Thread):
            await ctx.reply(error("Provide a text channel."))
            return
        await self.repos.guild_settings.update(
            str(ctx.guild.id),  # type: ignore[union-attr]
            mod_queue_channel_id=str(channel.id),
            mod_queue_enabled=True,
        )
        await ctx.reply(
            success(f"Mod queue enabled in {channel}. Flagged messages will appear there for review."),
        )

    @modqueue.command(name="off")
    @administrator_required()
    async def modqueue_off(self, ctx: commands.Context[commands.Bot]) -> None:
        await self.repos.guild_settings.update(str(ctx.guild.id), mod_queue_enabled=False)  # type: ignore[union-attr]
        await ctx.reply(success("Mod queue **disabled**. Automod will auto-delete messages again."))

    @modqueue.command(name="status")
    @administrator_required()
    async def modqueue_status(self, ctx: commands.Context[commands.Bot]) -> None:
        settings = await self.repos.guild_settings.get(str(ctx.guild.id))  # type: ignore[union-attr]
        channel = f"<#{settings.mod_queue_channel_id}>" if settings.mod_queue_channel_id else "Not set"
        body = "\n".join(
            [
                f"**Enabled:** {'Yes' if settings.mod_queue_enabled else 'No'}",
                f"**Channel:** {channel}",
                "",
                "When enabled, flagged messages are sent to the queue for mod review "
                "instead of being silently deleted.",
            ],
        )
        await ctx.reply(embed=basic_embed("Mod Queue", body))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModQueueCog(bot))
