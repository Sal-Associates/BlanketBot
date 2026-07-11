"""?prefix — change the command prefix."""

from __future__ import annotations

from discord.ext import commands

from bot.checks.decorators import administrator_required
from bot.cogs.deps import CogRepos
from bot.services.prefix import get_prefix, update_prefix, validate_prefix
from bot.utils.helpers import error, success


class PrefixCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repos = CogRepos(bot)

    @commands.command(name="prefix")
    @administrator_required()
    async def prefix(self, ctx: commands.Context[commands.Bot], *, new_prefix: str | None = None) -> None:
        guild_id = str(ctx.guild.id)  # type: ignore[union-attr]
        if new_prefix is None:
            current = await get_prefix(guild_id, self.repos.guild_settings)
            await ctx.reply(f"Current prefix: `{current}`")
            return

        validated = validate_prefix(new_prefix)
        if not validated.ok or validated.value is None:
            await ctx.reply(error(validated.error or "Invalid prefix."))
            return

        result = await update_prefix(guild_id, new_prefix, self.repos.guild_settings)
        if not result.ok or result.value is None:
            await ctx.reply(error(result.error or "Could not update prefix."))
            return
        await ctx.reply(success(f"Prefix changed to `{result.value}`"))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PrefixCog(bot))
