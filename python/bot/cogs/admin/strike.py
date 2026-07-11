"""?strike — configure strike escalation thresholds."""

from __future__ import annotations

from discord.ext import commands

from bot.checks.decorators import administrator_required
from bot.cogs.deps import CogRepos
from bot.utils.helpers import basic_embed, error, success


class StrikeCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repos = CogRepos(bot)

    @commands.group(name="strike", invoke_without_command=True)
    @administrator_required()
    async def strike(self, ctx: commands.Context[commands.Bot]) -> None:
        await self._status(ctx)

    @strike.command(name="status")
    @administrator_required()
    async def strike_status(self, ctx: commands.Context[commands.Bot]) -> None:
        await self._status(ctx)

    async def _status(self, ctx: commands.Context[commands.Bot]) -> None:
        settings = await self.repos.guild_settings.get(str(ctx.guild.id))  # type: ignore[union-attr]
        body = "\n".join(
            [
                f"**Enabled:** {'Yes' if settings.strike_enabled else 'No'}",
                f"**Auto-mute at:** {settings.strike_mute_at} warnings",
                f"**Auto-ban at:** {settings.strike_ban_at} warnings",
                "",
                "When a user reaches the mute threshold, they are automatically muted.",
                "When they reach the ban threshold, they are automatically banned.",
            ],
        )
        await ctx.reply(embed=basic_embed("Strike Escalation", body))

    @strike.command(name="set")
    @administrator_required()
    async def strike_set(
        self,
        ctx: commands.Context[commands.Bot],
        mute_at: int,
        ban_at: int,
    ) -> None:
        if mute_at <= 0 or ban_at <= 0 or mute_at >= ban_at:
            await ctx.reply(
                error("Usage: `?strike set <muteAt> <banAt>` — mute must be less than ban (e.g. 3 5)"),
            )
            return
        await self.repos.guild_settings.update(
            str(ctx.guild.id),  # type: ignore[union-attr]
            strike_mute_at=mute_at,
            strike_ban_at=ban_at,
            strike_enabled=True,
        )
        await ctx.reply(success(f"Strike escalation set: mute at **{mute_at}**, ban at **{ban_at}** warnings."))

    @strike.command(name="on")
    @administrator_required()
    async def strike_on(self, ctx: commands.Context[commands.Bot]) -> None:
        await self.repos.guild_settings.update(str(ctx.guild.id), strike_enabled=True)  # type: ignore[union-attr]
        await ctx.reply(success("Strike escalation **enabled**."))

    @strike.command(name="off")
    @administrator_required()
    async def strike_off(self, ctx: commands.Context[commands.Bot]) -> None:
        await self.repos.guild_settings.update(str(ctx.guild.id), strike_enabled=False)  # type: ignore[union-attr]
        await ctx.reply(success("Strike escalation **disabled**."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StrikeCog(bot))
