"""Automod ignore checks and target resolution."""

from __future__ import annotations

import discord

from bot.utils.helpers import CHANNEL_MENTION_RE, ROLE_MENTION_RE, SNOWFLAKE_RE
from bot.utils.resolvers import resolve_channel, resolve_role


def is_automod_eligible_channel(channel: discord.abc.GuildChannel | None) -> bool:
    return isinstance(channel, discord.abc.Messageable)


def is_channel_ignored(channel_id: str | int, ignored_channels: list[str]) -> bool:
    return str(channel_id) in ignored_channels


def is_member_role_ignored(member: discord.Member, ignored_roles: list[str]) -> bool:
    ignored = set(ignored_roles)
    return any(str(role.id) in ignored for role in member.roles)


def resolve_channel_target(
    guild: discord.Guild,
    input_value: str | None,
) -> tuple[str, discord.abc.GuildChannel | None] | None:
    if not input_value or not input_value.strip():
        return None
    trimmed = input_value.strip()
    mention = CHANNEL_MENTION_RE.match(trimmed)
    if mention:
        channel_id = mention.group(1)
        return channel_id, guild.get_channel(int(channel_id))
    if SNOWFLAKE_RE.match(trimmed):
        return trimmed, guild.get_channel(int(trimmed))
    channel = resolve_channel(guild, trimmed)
    return (str(channel.id), channel) if channel else None


def resolve_role_target(
    guild: discord.Guild,
    input_value: str | None,
) -> tuple[str, discord.Role | None] | None:
    if not input_value or not input_value.strip():
        return None
    trimmed = input_value.strip()
    mention = ROLE_MENTION_RE.match(trimmed)
    if mention:
        role_id = mention.group(1)
        return role_id, guild.get_role(int(role_id))
    if SNOWFLAKE_RE.match(trimmed):
        return trimmed, guild.get_role(int(trimmed))
    role = resolve_role(guild, trimmed)
    return (str(role.id), role) if role else None


def format_ignored_channel_line(guild: discord.Guild, channel_id: str) -> str:
    channel = guild.get_channel(int(channel_id))
    if channel:
        return f"{channel} — `{channel_id}`"
    return f"Deleted or inaccessible channel — `{channel_id}`"


def format_ignored_role_line(guild: discord.Guild, role_id: str) -> str:
    role = guild.get_role(int(role_id))
    if role:
        return f"{role.name} ({role}) — `{role_id}`"
    return f"Deleted or inaccessible role — `{role_id}`"
