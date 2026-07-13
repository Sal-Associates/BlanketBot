"""Live mod-log channel notifications."""

from __future__ import annotations

import logging
from typing import Any

import discord

from bot.database.repositories.guild_settings import GuildSettingsRepository

logger = logging.getLogger(__name__)

MOD_LOG_COLORS: dict[str, int] = {
    "ban": 0xED4245,
    "unban": 0x57F287,
    "kick": 0xFAA61A,
    "mute": 0x5865F2,
    "unmute": 0x57F287,
    "warn": 0xFEE75C,
    "softban": 0xED4245,
    "note": 0xEB459E,
    "lock": 0x95A5A6,
    "unlock": 0x57F287,
    "purge": 0x99AAB5,
    "automod": 0xE67E22,
    "strike_mute": 0x5865F2,
    "strike_ban": 0xED4245,
    "strike_mute_failed": 0x5865F2,
    "strike_ban_failed": 0xED4245,
    "queue_deny": 0xFEE75C,
    "queue_approve": 0x57F287,
    "channel_unlock_skipped": 0xFAA61A,
    "channel_unlock_failed": 0xED4245,
    "lockdown_enable": 0xED4245,
    "lockdown_enable_partial": 0xFAA61A,
    "lockdown_disable": 0x57F287,
    "lockdown_restore_failed": 0xED4245,
    "deafen": 0x5865F2,
    "undeafen": 0x57F287,
}


def _format_user(target: Any) -> str:
    return f"{target} ({getattr(target, 'id', target)})"


async def send_mod_log(
    guild: discord.Guild,
    *,
    action: str,
    target: Any,
    moderator: Any,
    reason: str | None,
    case_number: int | None,
    guild_settings: GuildSettingsRepository,
) -> bool:
    """Send a live notification to the configured mod-log channel."""
    settings = await guild_settings.get(str(guild.id))
    if not settings.mod_log_channel_id:
        return True

    channel = guild.get_channel(int(settings.mod_log_channel_id))
    if channel is None or not isinstance(channel, discord.TextChannel):
        logger.error(
            "[mod-log channel] Configured channel %s not found in guild %s",
            settings.mod_log_channel_id,
            guild.id,
        )
        return False

    title = f"Case #{case_number} — {action.upper()}" if case_number is not None else f"Case: {action.upper()}"
    embed = discord.Embed(
        title=title,
        color=MOD_LOG_COLORS.get(action, 0x5865F2),
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="User", value=_format_user(target), inline=True)
    embed.add_field(name="Moderator", value=str(moderator), inline=True)
    embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)

    try:
        await channel.send(embed=embed)
        return True
    except discord.HTTPException as exc:
        logger.error("[mod-log channel] Failed to send %s notification: %s", action, exc)
        return False


async def get_or_create_mute_role(
    guild: discord.Guild,
    *,
    guild_settings: GuildSettingsRepository,
) -> discord.Role:
    settings = await guild_settings.get(str(guild.id))
    if settings.mute_role_id:
        existing = guild.get_role(int(settings.mute_role_id))
        if existing is not None:
            return existing

    role = discord.utils.get(guild.roles, name="Muted")
    if role is None:
        role = await guild.create_role(
            name="Muted",
            colour=discord.Colour(0x808080),
            reason="Auto-created mute role",
        )
        for channel in guild.channels:
            if not isinstance(
                channel,
                discord.TextChannel | discord.VoiceChannel | discord.StageChannel | discord.ForumChannel,
            ):
                continue
            me = guild.me
            if me is None or not channel.permissions_for(me).manage_channels:
                continue
            overwrite = channel.overwrites_for(role)
            overwrite.send_messages = False
            overwrite.add_reactions = False
            if isinstance(channel, discord.VoiceChannel | discord.StageChannel):
                overwrite.speak = False
            try:
                await channel.set_permissions(role, overwrite=overwrite, reason="Mute role setup")
            except discord.HTTPException:
                continue

    await guild_settings.update(str(guild.id), mute_role_id=str(role.id))
    return role
