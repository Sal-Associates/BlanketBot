"""?whois — user profile with moderation history."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.cogs.deps import CogRepos
from bot.utils.resolvers import resolve_member
from bot.utils.time import format_iso_date


class WhoisCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repos = CogRepos(bot)

    @commands.command(name="whois")
    async def whois(self, ctx: commands.Context[commands.Bot], *, user_arg: str | None = None) -> None:
        target = resolve_member(ctx.guild, ctx.message, user_arg)  # type: ignore[arg-type]
        if target is None and isinstance(ctx.author, discord.Member):
            target = ctx.author
        if target is None:
            await ctx.reply("Could not resolve that user.")
            return

        guild_id = str(ctx.guild.id)  # type: ignore[union-attr]
        warnings = await self.repos.warnings.list_active(guild_id, str(target.id))
        notes = await self.repos.notes.list_for_user(guild_id, str(target.id))
        cases = await self.repos.cases.list_for_user(guild_id, str(target.id), limit=5)

        embed = discord.Embed(title=str(target), color=target.colour.value or 0x5865F2)
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="ID", value=str(target.id), inline=True)
        joined = f"<t:{int(target.joined_at.timestamp())}:R>" if target.joined_at else "Unknown"
        embed.add_field(name="Joined", value=joined, inline=True)
        embed.add_field(name="Created", value=f"<t:{int(target.created_at.timestamp())}:R>", inline=True)
        roles = [role.mention for role in target.roles if role != ctx.guild.default_role]  # type: ignore[union-attr]
        embed.add_field(name="Roles", value=" ".join(roles) or "None", inline=False)
        embed.add_field(name="Warnings", value=str(len(warnings)), inline=True)
        embed.add_field(name="Notes", value=str(len(notes)), inline=True)

        if cases:
            case_lines = [
                f"**#{case.case_number}** {case.action} — {case.reason or 'N/A'} ({format_iso_date(case.created_at)})"
                for case in cases
            ]
            embed.add_field(name="Recent Cases", value="\n".join(case_lines), inline=False)

        await ctx.reply(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WhoisCog(bot))
