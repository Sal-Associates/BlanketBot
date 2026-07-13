"""Single-guild guard helpers."""

from __future__ import annotations

import discord


def is_configured_guild(guild_id: int | str | None, configured_guild_id: str) -> bool:
    if guild_id is None:
        return False
    return str(guild_id) == configured_guild_id


def reject_foreign_guild(
    guild: discord.Guild | None,
    configured_guild_id: str,
) -> bool:
    """Return True if the event should be ignored (foreign or missing guild)."""
    if guild is None:
        return True
    return not is_configured_guild(guild.id, configured_guild_id)
