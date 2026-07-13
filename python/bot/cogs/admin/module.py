"""?module / ?modules — module toggles."""

from __future__ import annotations

from discord.ext import commands

from bot.checks.decorators import administrator_required
from bot.cogs.deps import CogRepos
from bot.utils.helpers import basic_embed, error, success

VALID_MODULES = ("Automod",)


class ModuleCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repos = CogRepos(bot)

    @commands.command(name="module")
    @administrator_required()
    async def module(self, ctx: commands.Context[commands.Bot], *, module_name: str) -> None:
        match = next((m for m in VALID_MODULES if m.lower() == module_name.lower()), None)
        if not match:
            await ctx.reply(error(f"Invalid module. Available: {', '.join(VALID_MODULES)}"))
            return
        enabled, _ = await self.repos.guild_settings.toggle_module(str(ctx.guild.id), match)  # type: ignore[union-attr]
        await ctx.reply(success(f"**{match}** is now **{'enabled' if enabled else 'disabled'}**."))

    @commands.command(name="modules")
    async def modules(self, ctx: commands.Context[commands.Bot]) -> None:
        guild_id = str(ctx.guild.id)  # type: ignore[union-attr]
        lines = []
        for module in VALID_MODULES:
            disabled = await self.repos.guild_settings.is_module_disabled(guild_id, module)
            status = "🔴 Disabled" if disabled else "🟢 Enabled"
            lines.append(f"**{module}** — {status}")
        await ctx.reply(embed=basic_embed("Server Modules", "\n".join(lines)))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModuleCog(bot))
