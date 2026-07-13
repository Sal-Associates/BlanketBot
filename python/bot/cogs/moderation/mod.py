"""?mod — ban, kick, mute, and related moderation actions."""

from __future__ import annotations

import re

import discord
from discord.ext import commands

from bot.checks.decorators import moderator_required
from bot.cogs.deps import CogRepos
from bot.services.hierarchy import get_moderation_denied
from bot.services.moderation import ModerationService
from bot.utils.helpers import error
from bot.utils.resolvers import resolve_member, resolve_user_target
from bot.utils.time import parse_duration

ACTIONS = frozenset({"ban", "unban", "kick", "mute", "unmute", "softban", "deafen", "undeafen"})


class ModCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repos = CogRepos(bot)

    @commands.group(name="mod", invoke_without_command=True)
    @moderator_required()
    async def mod(self, ctx: commands.Context[commands.Bot]) -> None:
        await ctx.reply(error(f"Usage: `?mod {'|'.join(sorted(ACTIONS))}` followed by user and optional args."))

    async def _deny_if_needed(
        self,
        ctx: commands.Context[commands.Bot],
        target: discord.Member | object,
        *,
        require_member: bool = True,
    ) -> bool:
        if not isinstance(ctx.author, discord.Member):
            return True
        denied = get_moderation_denied(ctx.guild, ctx.author, target, require_member=require_member)  # type: ignore[arg-type]
        if denied:
            await ctx.reply(denied)
            return True
        return False

    @mod.command(name="ban")
    @moderator_required()
    async def mod_ban(self, ctx: commands.Context[commands.Bot], *, args: str) -> None:
        parts = args.split()
        member, user_id = resolve_user_target(ctx.guild, ctx.message, parts[0])  # type: ignore[arg-type]
        if user_id is None:
            await ctx.reply(error("Usage: `?mod ban <user> [time] [reason]`"))
            return
        target = member or type("UserTarget", (), {"id": int(user_id)})()
        if await self._deny_if_needed(ctx, target, require_member=False):
            return

        duration_ms = None
        reason_start = 1
        if len(parts) > 1:
            maybe = parse_duration(parts[1])
            if maybe:
                duration_ms = maybe
                reason_start = 2
        reason = " ".join(parts[reason_start:]) or "No reason provided"
        display = member.display_name if member else user_id

        result = await self.repos.moderation.ban(
            ctx.guild,  # type: ignore[arg-type]
            ctx.author,
            user_id=user_id,
            target_display=member or display,
            reason=reason,
            duration_ms=duration_ms,
        )
        await ctx.reply(ModerationService.format_reply(result))

    @mod.command(name="unban")
    @moderator_required()
    async def mod_unban(self, ctx: commands.Context[commands.Bot], *, args: str) -> None:
        parts = args.split()
        user_id = re.sub(r"[<@!>]", "", parts[0]) if parts else ""
        if not user_id:
            await ctx.reply(error("Usage: `?mod unban <userId> [reason]`"))
            return
        if str(ctx.author.id) == user_id:
            await ctx.reply(error("You cannot moderate yourself."))
            return
        reason = " ".join(parts[1:]) or "No reason provided"
        result = await self.repos.moderation.unban(ctx.guild, ctx.author, user_id=user_id, reason=reason)  # type: ignore[arg-type]
        await ctx.reply(ModerationService.format_reply(result))

    @mod.command(name="kick")
    @moderator_required()
    async def mod_kick(self, ctx: commands.Context[commands.Bot], *, args: str) -> None:
        parts = args.split()
        target = resolve_member(ctx.guild, ctx.message, parts[0])  # type: ignore[arg-type]
        if target is None:
            await ctx.reply(error("That user is not currently a member of this server."))
            return
        if await self._deny_if_needed(ctx, target):
            return
        reason = " ".join(parts[1:]) or "No reason provided"
        result = await self.repos.moderation.kick(ctx.guild, ctx.author, target, reason=reason)  # type: ignore[arg-type]
        await ctx.reply(ModerationService.format_reply(result))

    @mod.command(name="softban")
    @moderator_required()
    async def mod_softban(self, ctx: commands.Context[commands.Bot], *, args: str) -> None:
        parts = args.split()
        target = resolve_member(ctx.guild, ctx.message, parts[0])  # type: ignore[arg-type]
        if target is None:
            await ctx.reply(error("That user is not currently a member of this server."))
            return
        if await self._deny_if_needed(ctx, target):
            return
        reason = " ".join(parts[1:]) or "No reason provided"
        result = await self.repos.moderation.softban(ctx.guild, ctx.author, target, reason=reason)  # type: ignore[arg-type]
        await ctx.reply(ModerationService.format_reply(result))

    @mod.command(name="mute")
    @moderator_required()
    async def mod_mute(self, ctx: commands.Context[commands.Bot], *, args: str) -> None:
        parts = args.split()
        target = resolve_member(ctx.guild, ctx.message, parts[0])  # type: ignore[arg-type]
        if target is None:
            await ctx.reply(error("That user is not currently a member of this server."))
            return
        if await self._deny_if_needed(ctx, target):
            return
        duration_ms = None
        reason_start = 1
        if len(parts) > 1:
            maybe = parse_duration(parts[1])
            if maybe:
                duration_ms = maybe
                reason_start = 2
        reason = " ".join(parts[reason_start:]) or "No reason provided"
        result = await self.repos.moderation.mute(
            ctx.guild,  # type: ignore[arg-type]
            ctx.author,
            target,
            reason=reason,
            duration_ms=duration_ms,
        )
        await ctx.reply(ModerationService.format_reply(result))

    @mod.command(name="unmute")
    @moderator_required()
    async def mod_unmute(self, ctx: commands.Context[commands.Bot], *, args: str) -> None:
        parts = args.split()
        target = resolve_member(ctx.guild, ctx.message, parts[0])  # type: ignore[arg-type]
        if target is None:
            await ctx.reply(error("That user is not currently a member of this server."))
            return
        if await self._deny_if_needed(ctx, target):
            return
        reason = " ".join(parts[1:]) or "No reason provided"
        result = await self.repos.moderation.unmute(ctx.guild, ctx.author, target, reason=reason)  # type: ignore[arg-type]
        await ctx.reply(ModerationService.format_reply(result))

    @mod.command(name="deafen")
    @moderator_required()
    async def mod_deafen(self, ctx: commands.Context[commands.Bot], *, args: str) -> None:
        parts = args.split()
        target = resolve_member(ctx.guild, ctx.message, parts[0])  # type: ignore[arg-type]
        if target is None:
            await ctx.reply(error("That user is not currently a member of this server."))
            return
        if await self._deny_if_needed(ctx, target):
            return
        reason = " ".join(parts[1:]) or "Deafened"
        result = await self.repos.moderation.deafen(ctx.guild, ctx.author, target, reason=reason)  # type: ignore[arg-type]
        await ctx.reply(ModerationService.format_reply(result))

    @mod.command(name="undeafen")
    @moderator_required()
    async def mod_undeafen(self, ctx: commands.Context[commands.Bot], *, args: str) -> None:
        parts = args.split()
        target = resolve_member(ctx.guild, ctx.message, parts[0])  # type: ignore[arg-type]
        if target is None:
            await ctx.reply(error("That user is not currently a member of this server."))
            return
        if await self._deny_if_needed(ctx, target):
            return
        result = await self.repos.moderation.undeafen(ctx.guild, ctx.author, target)  # type: ignore[arg-type]
        await ctx.reply(ModerationService.format_reply(result))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModCog(bot))
