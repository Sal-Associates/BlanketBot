"""Single-guild guard tests."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from bot.services.guild_guard import is_configured_guild, reject_foreign_guild

CONFIGURED = "123456789012345678"


def test_is_configured_guild_matches() -> None:
    assert is_configured_guild(CONFIGURED, CONFIGURED) is True
    assert is_configured_guild(int(CONFIGURED), CONFIGURED) is True


def test_is_configured_guild_rejects_foreign() -> None:
    assert is_configured_guild("999999999999999999", CONFIGURED) is False
    assert is_configured_guild(None, CONFIGURED) is False


def test_reject_foreign_guild_missing_guild() -> None:
    assert reject_foreign_guild(None, CONFIGURED) is True


def test_reject_foreign_guild_foreign() -> None:
    guild = MagicMock()
    guild.id = 999999999999999999
    assert reject_foreign_guild(guild, CONFIGURED) is True


def test_reject_foreign_guild_configured() -> None:
    guild = MagicMock()
    guild.id = int(CONFIGURED)
    assert reject_foreign_guild(guild, CONFIGURED) is False


@pytest.mark.asyncio
async def test_foundation_cog_rejects_foreign_guild_before_commands() -> None:
    from bot.cogs.foundation import FoundationCog
    from bot.config import Settings

    settings = Settings(
        discord_token="token",
        guild_id=CONFIGURED,
        superuser_ids=frozenset(),
        database_path=Path("data/test.sqlite3"),
    )
    bot = MagicMock()
    cog = FoundationCog(bot, settings)

    foreign_ctx = MagicMock()
    foreign_ctx.guild = MagicMock()
    foreign_ctx.guild.id = 999999999999999999

    assert await cog.cog_check(foreign_ctx) is False

    dm_ctx = MagicMock()
    dm_ctx.guild = None
    assert await cog.cog_check(dm_ctx) is False

    home_ctx = MagicMock()
    home_ctx.guild = MagicMock()
    home_ctx.guild.id = int(CONFIGURED)
    assert await cog.cog_check(home_ctx) is True
