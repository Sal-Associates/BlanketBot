"""Bot bootstrap and shutdown tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from bot.client import ModBot, build_bot
from bot.config import Settings


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        discord_token="test-token",
        guild_id="123456789012345678",
        superuser_ids=frozenset(),
        database_path=tmp_path / "bot.sqlite3",
    )


@pytest.mark.asyncio
async def test_build_bot_wires_settings_and_database(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    bot = build_bot(settings)
    assert isinstance(bot, ModBot)
    assert bot.settings is settings
    assert bot.database.path == settings.database_path


@pytest.mark.asyncio
async def test_graceful_shutdown_closes_database(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    bot = build_bot(settings)
    await bot.database.connect()
    assert bot.database._connection is not None
    await bot.close()
    assert bot.database._connection is None


@pytest.mark.asyncio
async def test_setup_hook_runs_migrations(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    bot = build_bot(settings)
    await bot.setup_hook()
    try:
        assert await bot.database.table_exists("guild_settings") is True
        row = await bot.database.fetchone("SELECT version FROM schema_migrations WHERE version = 1")
        assert row is not None
    finally:
        await bot.close()


def test_main_exits_before_connect_on_bad_config() -> None:
    from unittest.mock import patch

    from bot import __main__ as entry
    from bot.errors import ConfigurationError

    with patch(
        "bot.__main__.load_settings",
        side_effect=ConfigurationError("DISCORD_TOKEN is required"),
    ):
        with pytest.raises(SystemExit) as exc:
            entry.main()
        assert exc.value.code == 1
