"""Discord object resolution helpers."""

from __future__ import annotations

import discord

from bot.utils.helpers import CHANNEL_MENTION_RE, MENTION_ONLY_RE, ROLE_MENTION_RE, SNOWFLAKE_RE


def resolve_member(guild: discord.Guild, message: discord.Message, input_value: str | None) -> discord.Member | None:
    if not input_value:
        return message.author if isinstance(message.author, discord.Member) else None
    mention = MENTION_ONLY_RE.match(input_value.strip())
    if mention:
        return guild.get_member(int(mention.group(1)))
    if SNOWFLAKE_RE.match(input_value):
        return guild.get_member(int(input_value))
    lowered = input_value.lower()
    for member in guild.members:
        if member.display_name.lower() == lowered or member.name.lower() == lowered:
            return member
    return None


def resolve_user_target(
    guild: discord.Guild,
    message: discord.Message,
    input_value: str | None,
) -> tuple[discord.Member | None, str | None]:
    member = resolve_member(guild, message, input_value)
    if member:
        return member, member.id
    if not input_value:
        return None, None
    mention = MENTION_ONLY_RE.match(input_value.strip())
    if mention:
        return None, mention.group(1)
    if SNOWFLAKE_RE.match(input_value.strip()):
        return None, input_value.strip()
    return None, None


def resolve_role(guild: discord.Guild, input_value: str | None) -> discord.Role | None:
    if not input_value:
        return None
    mention = ROLE_MENTION_RE.match(input_value.strip())
    if mention:
        return guild.get_role(int(mention.group(1)))
    if SNOWFLAKE_RE.match(input_value.strip()):
        return guild.get_role(int(input_value.strip()))
    lowered = input_value.lower()
    for role in guild.roles:
        if role.name.lower() == lowered:
            return role
    return None


def resolve_channel(guild: discord.Guild, input_value: str | None) -> discord.abc.GuildChannel | None:
    if not input_value:
        return None
    mention = CHANNEL_MENTION_RE.match(input_value.strip())
    if mention:
        return guild.get_channel(int(mention.group(1)))
    if SNOWFLAKE_RE.match(input_value.strip()):
        return guild.get_channel(int(input_value.strip()))
    lowered = input_value.lower()
    for channel in guild.channels:
        if channel.name.lower() == lowered:
            return channel
    return None
