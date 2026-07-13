"""?channel — lock, unlock, slowmode, and lockdown controls."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime

import discord
from discord.ext import commands

from bot.checks.decorators import administrator_required, moderator_required
from bot.cogs.deps import CogRepos
from bot.errors import DatabaseError
from bot.services.lockdown import (
    bot_has_manage_channels,
    build_lockdown_status,
    disable_lockdown,
    enable_lockdown,
    format_lockdown_reply,
    is_lockdown_eligible_channel,
)
from bot.services.mod_log import send_mod_log
from bot.utils.channel_permissions import (
    apply_permission_state,
    get_permission_state,
    restore_channel_from_timed_action,
)
from bot.utils.helpers import basic_embed, error, success
from bot.utils.resolvers import resolve_channel
from bot.utils.time import format_duration, parse_duration

logger = logging.getLogger(__name__)

CHANNEL_LOCK_PERMISSION = "SendMessages"
CHANNEL_UNLOCK_ACTION = "channel_unlock"


class ChannelCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repos = CogRepos(bot)

    @commands.group(name="channel", invoke_without_command=True)
    async def channel(self, ctx: commands.Context[commands.Bot]) -> None:
        await ctx.reply(error("Usage: `?channel lock|unlock|slowmode|lockdown`"))

    @channel.group(name="lockdown", invoke_without_command=True)
    @administrator_required()
    async def channel_lockdown(self, ctx: commands.Context[commands.Bot], *, reason: str = "") -> None:
        if not bot_has_manage_channels(ctx.guild):  # type: ignore[arg-type]
            await ctx.reply(error("I need the **Manage Channels** permission for lockdown commands."))
            return
        result = await enable_lockdown(
            ctx.guild,  # type: ignore[arg-type]
            ctx.author,  # type: ignore[arg-type]
            reason or None,
            lockdown=self.repos.lockdown,
            cases=self.repos.cases,
            guild_settings=self.repos.guild_settings,
            timed_actions=self.repos.timed_actions,
        )
        await ctx.reply(format_lockdown_reply(result))

    @channel_lockdown.group(name="channel", invoke_without_command=True)
    @administrator_required()
    async def lockdown_channel(self, ctx: commands.Context[commands.Bot]) -> None:
        await ctx.reply(error("Usage: `?channel lockdown channel add|remove|list`"))

    @lockdown_channel.command(name="add")
    @administrator_required()
    async def lockdown_channel_add(self, ctx: commands.Context[commands.Bot], *, channel_arg: str) -> None:
        channel = resolve_channel(ctx.guild, channel_arg)  # type: ignore[arg-type]
        if channel is None:
            await ctx.reply(error("Usage: `?channel lockdown channel add #channel`"))
            return
        if not is_lockdown_eligible_channel(channel):
            await ctx.reply(error("That channel type does not support SendMessages permission overwrites."))
            return
        try:
            await self.repos.lockdown.add_channel(str(ctx.guild.id), str(channel.id))  # type: ignore[union-attr]
        except DatabaseError:
            await ctx.reply(error(f"{channel} is already in the lockdown channel list."))
            return
        await ctx.reply(success(f"Added {channel} to lockdown channels."))

    @lockdown_channel.command(name="remove")
    @administrator_required()
    async def lockdown_channel_remove(self, ctx: commands.Context[commands.Bot], *, channel_arg: str) -> None:
        channel = resolve_channel(ctx.guild, channel_arg)  # type: ignore[arg-type]
        if channel is None:
            await ctx.reply(error("Usage: `?channel lockdown channel remove #channel`"))
            return
        removed = await self.repos.lockdown.remove_channel(str(ctx.guild.id), str(channel.id))  # type: ignore[union-attr]
        if not removed:
            await ctx.reply(error(f"{channel} is not in the lockdown channel list."))
            return
        await ctx.reply(success(f"Removed {channel} from lockdown channels."))

    @lockdown_channel.command(name="list")
    @administrator_required()
    async def lockdown_channel_list(self, ctx: commands.Context[commands.Bot]) -> None:
        configured = await self.repos.lockdown.list_channels(str(ctx.guild.id))  # type: ignore[union-attr]
        if not configured:
            await ctx.reply(error("No lockdown channels configured."))
            return
        lines = []
        for channel_id in configured:
            channel = ctx.guild.get_channel(int(channel_id))  # type: ignore[union-attr]
            lines.append(f"• {channel} (`{channel_id}`)" if channel else f"• ~~deleted~~ (`{channel_id}`)")
        await ctx.reply(embed=basic_embed("Lockdown Channels", "\n".join(lines)))

    @channel_lockdown.command(name="enable")
    @administrator_required()
    async def lockdown_enable(self, ctx: commands.Context[commands.Bot], *, reason: str = "") -> None:
        await self.channel_lockdown(ctx, reason=reason)

    @channel_lockdown.command(name="disable", aliases=["end"])
    @administrator_required()
    async def lockdown_disable(self, ctx: commands.Context[commands.Bot], *, reason: str = "") -> None:
        if not bot_has_manage_channels(ctx.guild):  # type: ignore[arg-type]
            await ctx.reply(error("I need the **Manage Channels** permission for lockdown commands."))
            return
        result = await disable_lockdown(
            ctx.guild,  # type: ignore[arg-type]
            ctx.author,  # type: ignore[arg-type]
            reason or None,
            lockdown=self.repos.lockdown,
            cases=self.repos.cases,
            guild_settings=self.repos.guild_settings,
            timed_actions=self.repos.timed_actions,
        )
        await ctx.reply(format_lockdown_reply(result))

    @channel_lockdown.command(name="status")
    @administrator_required()
    async def lockdown_status(self, ctx: commands.Context[commands.Bot]) -> None:
        status = await build_lockdown_status(
            ctx.guild,  # type: ignore[arg-type]
            lockdown=self.repos.lockdown,
            timed_actions=self.repos.timed_actions,
        )
        await ctx.reply(embed=basic_embed("Lockdown Status", status))

    @channel.command(name="lock")
    @moderator_required()
    async def channel_lock(self, ctx: commands.Context[commands.Bot], *, args: str = "") -> None:
        parts = args.split()
        channel = ctx.channel
        time_arg = parts[0] if parts else None
        if parts and parts[0].startswith("<#"):
            resolved = resolve_channel(ctx.guild, parts[0])  # type: ignore[arg-type]
            if resolved:
                channel = resolved
            time_arg = parts[1] if len(parts) > 1 else None

        if not isinstance(channel, discord.TextChannel | discord.Thread):
            await ctx.reply(error("Could not lock that channel."))
            return

        duration = parse_duration(time_arg) if time_arg else None
        everyone = ctx.guild.default_role  # type: ignore[union-attr]
        previous_state = get_permission_state(channel.overwrites_for(everyone), CHANNEL_LOCK_PERMISSION)

        try:
            await channel.set_permissions(everyone, send_messages=False)
        except discord.HTTPException:
            await ctx.reply(error("Could not lock that channel."))
            return

        if duration:
            ends_at = datetime.fromtimestamp((time.time() * 1000 + duration) / 1000, UTC).strftime(
                "%Y-%m-%dT%H:%M:%fZ",
            )
            try:
                await self.repos.timed_actions.upsert_channel(
                    guild_id=str(ctx.guild.id),  # type: ignore[union-attr]
                    channel_id=str(channel.id),
                    role_id=str(everyone.id),
                    action=CHANNEL_UNLOCK_ACTION,
                    permission=CHANNEL_LOCK_PERMISSION,
                    previous_state=previous_state,
                    applied_state="deny",
                    ends_at=ends_at,
                    moderator_id=str(ctx.author.id),
                )
            except Exception as exc:
                logger.error("[channel] Timed unlock persistence failed: %s", exc)
                try:
                    await apply_permission_state(
                        channel,
                        everyone,
                        CHANNEL_LOCK_PERMISSION,
                        previous_state,
                        reason="Lock rollback",
                    )
                except discord.HTTPException as rollback_exc:
                    logger.error("[channel] Lock rollback failed: %s", rollback_exc)
                await ctx.reply(
                    error(
                        "Channel was locked briefly but auto-unlock could not be scheduled. The lock was rolled back.",
                    ),
                )
                return

        try:
            case_number = await self.repos.cases.create_case(
                guild_id=str(ctx.guild.id),  # type: ignore[union-attr]
                user_id=str(channel.id),
                moderator_id=str(ctx.author.id),
                action="lock",
                reason="Channel locked",
                source="moderation",
            )
            await send_mod_log(
                ctx.guild,  # type: ignore[arg-type]
                action="lock",
                target=channel,
                moderator=ctx.author,
                reason=f"Channel locked ({format_duration(duration)})" if duration else "Channel locked",
                case_number=case_number,
                guild_settings=self.repos.guild_settings,
            )
            suffix = f" (auto-unlock in {time_arg})" if duration and time_arg else ""
            await ctx.reply(success(f"Locked {channel} — Case #{case_number}{suffix}."))
        except Exception as exc:
            logger.error("[channel] Case logging failed after lock: %s", exc)
            await ctx.reply(error("Channel was locked but the case could not be saved."))

    @channel.command(name="unlock")
    @moderator_required()
    async def channel_unlock(self, ctx: commands.Context[commands.Bot], *, channel_arg: str = "") -> None:
        channel = resolve_channel(ctx.guild, channel_arg) or ctx.channel  # type: ignore[arg-type]
        if not isinstance(channel, discord.TextChannel | discord.Thread):
            await ctx.reply(error("Could not unlock that channel."))
            return

        everyone = ctx.guild.default_role  # type: ignore[union-attr]
        current_state = get_permission_state(channel.overwrites_for(everyone), CHANNEL_LOCK_PERMISSION)
        pending = await self.repos.timed_actions.list_pending_channel(
            str(ctx.guild.id),  # type: ignore[union-attr]
            str(channel.id),
            CHANNEL_UNLOCK_ACTION,
            CHANNEL_LOCK_PERMISSION,
        )

        restored_state: str | None = None
        if pending:
            timed_action = pending[0]
            try:
                restore_result = await restore_channel_from_timed_action(
                    channel,
                    everyone.id,
                    permission=CHANNEL_LOCK_PERMISSION,
                    applied_state=timed_action.applied_state or "deny",  # type: ignore[arg-type]
                    previous_state=timed_action.previous_state or "unset",  # type: ignore[arg-type]
                    reason="Manual unlock",
                )
            except discord.HTTPException:
                await ctx.reply(error("Could not restore channel permissions."))
                return

            if restore_result.kind == "conflict":
                removed = await self.repos.timed_actions.cancel_channel(
                    str(ctx.guild.id),  # type: ignore[union-attr]
                    str(channel.id),
                    CHANNEL_UNLOCK_ACTION,
                    CHANNEL_LOCK_PERMISSION,
                )
                await ctx.reply(
                    success(
                        f"Cancelled pending timed unlock ({removed}). "
                        f"{CHANNEL_LOCK_PERMISSION} was already changed manually "
                        f"(now {restore_result.current_state}); no overwrite was modified.",
                    ),
                )
                return

            restored_state = restore_result.previous_state
            if not await self.repos.timed_actions.complete(timed_action.id):
                logger.error(
                    "[channel] Restored %s but failed to remove pending timed action %s",
                    channel.id,
                    timed_action.id,
                )
            unlock_reason = (
                f"Manual unlock restored {CHANNEL_LOCK_PERMISSION} to {restored_state} (cancelled pending timed unlock)"
            )
        else:
            if current_state != "deny":
                await ctx.reply(error("That channel is not locked."))
                return
            try:
                await channel.set_permissions(everyone, send_messages=None)
            except discord.HTTPException:
                await ctx.reply(error("Could not unlock that channel."))
                return
            unlock_reason = "Channel unlocked (no pending timed lock)"
            restored_state = "unset"

        case_number = await self.repos.cases.create_case(
            guild_id=str(ctx.guild.id),  # type: ignore[union-attr]
            user_id=str(channel.id),
            moderator_id=str(ctx.author.id),
            action="unlock",
            reason=unlock_reason,
            source="moderation",
        )
        await send_mod_log(
            ctx.guild,  # type: ignore[arg-type]
            action="unlock",
            target=channel,
            moderator=ctx.author,
            reason=unlock_reason,
            case_number=case_number,
            guild_settings=self.repos.guild_settings,
        )
        await ctx.reply(
            success(
                f"Unlocked {channel} — Case #{case_number}. "
                f"Restored {CHANNEL_LOCK_PERMISSION} to **{restored_state or 'inherit'}**.",
            ),
        )

    @channel.command(name="slowmode")
    @moderator_required()
    async def channel_slowmode(self, ctx: commands.Context[commands.Bot], seconds: int) -> None:
        if seconds < 0 or seconds > 21600:
            await ctx.reply(error("Provide seconds between 0 and 21600."))
            return
        await ctx.channel.edit(slowmode_delay=seconds)  # type: ignore[union-attr]
        if seconds == 0:
            await ctx.reply(success("Slowmode disabled."))
        else:
            await ctx.reply(success(f"Slowmode set to **{seconds}s**."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ChannelCog(bot))
