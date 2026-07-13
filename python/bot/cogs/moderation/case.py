"""?case — moderation case history."""

from __future__ import annotations

from discord.ext import commands

from bot.checks.decorators import moderator_required
from bot.cogs.deps import CogRepos
from bot.utils.helpers import basic_embed, error
from bot.utils.resolvers import resolve_member
from bot.utils.time import format_iso_date


def _format_case_extra(metadata: dict) -> list[str]:
    lines: list[str] = []
    for key, label in (
        ("source", "Source"),
        ("status", "Status"),
        ("warning_id", "Warning ID"),
        ("queue_id", "Queue ID"),
        ("timed_action_id", "Timed action ID"),
        ("timed_action", "Timed action"),
        ("ends_at", "Expires"),
    ):
        if key in metadata and metadata[key] is not None:
            value = metadata[key]
            if key == "ends_at" and isinstance(value, int):
                lines.append(f"**{label}:** <t:{value // 1000}:f>")
            else:
                lines.append(f"**{label}:** {value}")
    return lines


class CaseCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repos = CogRepos(bot)

    @commands.group(name="case", invoke_without_command=True)
    @moderator_required()
    async def case(self, ctx: commands.Context[commands.Bot], *, arg: str = "") -> None:
        if ctx.invoked_subcommand is not None:
            return
        trimmed = arg.strip()
        if not trimmed:
            await ctx.reply(error("Usage: `?case <number>` or `?case list [user]`"))
            return
        try:
            case_number = int(trimmed.replace("#", ""), 10)
        except ValueError:
            await ctx.reply(error("Usage: `?case <number>` or `?case list [user]`"))
            return
        await self._show_case(ctx, case_number)

    async def _show_case(self, ctx: commands.Context[commands.Bot], case_number: int) -> None:
        record = await self.repos.cases.get_case(str(ctx.guild.id), case_number)  # type: ignore[union-attr]
        if record is None:
            await ctx.reply(error(f"Case #{case_number} not found."))
            return
        body = "\n".join(
            [
                f"**Action:** {record.action}",
                f"**User:** <@{record.user_id}> (`{record.user_id}`)",
                f"**Moderator:** <@{record.moderator_id}>",
                f"**Reason:** {record.reason or 'None'}",
                f"**Date:** {format_iso_date(record.created_at)}",
                *_format_case_extra(record.metadata),
            ],
        )
        await ctx.reply(embed=basic_embed(f"Case #{record.case_number}", body))

    @case.command(name="list")
    @moderator_required()
    async def case_list(self, ctx: commands.Context[commands.Bot], *, user_arg: str | None = None) -> None:
        guild_id = str(ctx.guild.id)  # type: ignore[union-attr]
        target = resolve_member(ctx.guild, ctx.message, user_arg)  # type: ignore[arg-type]
        cases = (
            await self.repos.cases.list_for_user(guild_id, str(target.id))
            if target
            else await self.repos.cases.list_recent(guild_id)
        )
        if not cases:
            await ctx.reply(error("No cases found."))
            return
        title = f"Cases: {target.display_name}" if target else "Recent Cases"
        lines = [
            f"**#{c.case_number}** {c.action} — {c.reason} by <@{c.moderator_id}> ({format_iso_date(c.created_at)})"
            for c in cases
        ]
        await ctx.reply(embed=basic_embed(title, "\n".join(lines)))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(CaseCog(bot))
