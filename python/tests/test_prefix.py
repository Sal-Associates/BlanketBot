"""Prefix validation and updates (ported from verify-database guild settings patterns)."""

from __future__ import annotations

import pytest
from bot.services.prefix import get_prefix, update_prefix, validate_prefix
from tests.conftest import Repositories


def test_validate_prefix_rejects_empty_and_long_values() -> None:
    assert validate_prefix(None).ok is False
    assert validate_prefix("").ok is False
    assert validate_prefix("   ").ok is False
    assert validate_prefix("toolong").ok is False


def test_validate_prefix_accepts_valid_prefix() -> None:
    result = validate_prefix("!")
    assert result.ok is True
    assert result.value == "!"


@pytest.mark.asyncio
async def test_get_and_update_prefix(repos: Repositories, guild_id: str) -> None:
    assert await get_prefix(guild_id, repos.guild_settings) == "?"
    updated = await update_prefix(guild_id, "!", repos.guild_settings)
    assert updated.ok is True
    assert updated.value == "!"
    assert await get_prefix(guild_id, repos.guild_settings) == "!"
