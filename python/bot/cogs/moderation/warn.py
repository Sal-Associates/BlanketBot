"""?warn — warning system."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot.checks.decorators import moderator_required
from bot.cogs.deps import CogRepos
from bot.services.hierarchy import get_moderation_denied
from bot.services.mod_log import send_mod_log
from bot.services.strikes import check_strike_escalation
from bot.utils.helpers import basic_embed, error, success
from bot.utils.resolvers import resolve_member
from bot.utils.time import format_iso_date

logger = logging.getLogger(__name__)


class WarnCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repos = CogRepos(bot)

    @commands.group(name="warn", invoke_without_command=True)
    @moderator_required()
    async def warn(self, ctx: commands.Context[commands.Bot]) -> None:
        await ctx.reply(error("Usage: `?warn add|list|del|clear|view|remove`"))

    @warn.command(name="add")
    @moderator_required()
    async def warn_add(self, ctx: commands.Context[commands.Bot], *, args: str) -> None:
        parts = args.split()
        target = resolve_member(ctx.guild, ctx.message, parts[0])  # type: ignore[arg-type]
        if target is None:
            await ctx.reply(error("That user is not currently a member of this server."))
            return
        if not isinstance(ctx.author, discord.Member):
            return
        denied = get_moderation_denied(ctx.guild, ctx.author, target)  # type: ignore[arg-type]
        if denied:
            await ctx.reply(denied)
            return
        reason = " ".join(parts[1:]) or "No reason provided"
        try:
            warning_id, case_number = await self.repos.warnings.create_with_case(
                guild_id=str(ctx.guild.id),  # type: ignore[union-attr]
                user_id=str(target.id),
                moderator_id=str(ctx.author.id),
                reason=reason,
                source="warn_command",
                cases=self.repos.cases,
            )
        except Exception as exc:
            logger.error("[warn] Database write failed: %s", exc)
            await ctx.reply(error("Could not save that warning."))
            return

        notified = await send_mod_log(
            ctx.guild,  # type: ignore[arg-type]
            action="warn",
            target=target,
            moderator=ctx.author,
            reason=reason,
            case_number=case_number,
            guild_settings=self.repos.guild_settings,
        )
        if not notified:
            logger.error("[warn] Mod-log channel notification failed for case #%s", case_number)

        reply = success(
            f"Warned **{target.display_name}** — Warning #{warning_id}, Case #{case_number}. Reason: {reason}",
        )
        escalation = await check_strike_escalation(
            ctx.guild,  # type: ignore[arg-type]
            target,
            ctx.author,
            guild_settings=self.repos.guild_settings,
            warnings=self.repos.warnings,
            cases=self.repos.cases,
            strike_state=self.repos.strike_state,
        )
        if escalation:
            extra = escalation.value if escalation.ok else escalation.error
            if extra:
                reply = f"{reply}\n{extra}"
        await ctx.reply(reply)

    @warn.command(name="list", aliases=["view"])
    @moderator_required()
    async def warn_list(self, ctx: commands.Context[commands.Bot], *, user_arg: str | None = None) -> None:
        target = resolve_member(ctx.guild, ctx.message, user_arg)  # type: ignore[arg-type]
        if target is None and isinstance(ctx.author, discord.Member):
            target = ctx.author
        if target is None:
            await ctx.reply(error("Usage: `?warn list [@user]`"))
            return
        warnings = await self.repos.warnings.list_active(str(ctx.guild.id), str(target.id))  # type: ignore[union-attr]
        if not warnings:
            await ctx.reply(error(f"**{target.display_name}** has no warnings."))
            return
        lines = [f"**#{w.id}** — {w.reason or 'No reason'} ({format_iso_date(w.created_at)})" for w in warnings]
        await ctx.reply(
            embed=basic_embed(f"Warnings: {target.display_name}", "\n".join(lines), color=0xFEE75C),
        )

    @warn.command(name="del", aliases=["remove"])
    @moderator_required()
    async def warn_del(self, ctx: commands.Context[commands.Bot], warning_id: str) -> None:
        parsed = int(warning_id.replace("#", ""), 10)
        if not parsed:
            await ctx.reply(error("Usage: `?warn del <warning ID>`"))
            return
        if not await self.repos.warnings.void(parsed):
            await ctx.reply(error("Warning not found."))
            return
        await ctx.reply(success(f"Deleted warning #{parsed}."))

    @warn.command(name="clear")
    @moderator_required()
    async def warn_clear(self, ctx: commands.Context[commands.Bot], *, user_arg: str) -> None:
        target = resolve_member(ctx.guild, ctx.message, user_arg)  # type: ignore[arg-type]
        if target is None:
            await ctx.reply(error("Usage: `?warn clear <user>`"))
            return
        await self.repos.warnings.void_all_for_user(str(ctx.guild.id), str(target.id))  # type: ignore[union-attr]
        await ctx.reply(success(f"Cleared all warnings for **{target.display_name}**."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WarnCog(bot))
