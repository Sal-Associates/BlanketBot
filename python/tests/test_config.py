"""Configuration loading and validation tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from bot.config import load_settings
from bot.errors import ConfigurationError


def test_missing_token_fails() -> None:
    env = {
        "GUILD_ID": "123456789012345678",
        "DATABASE_PATH": "data/test.sqlite3",
    }
    with pytest.raises(ConfigurationError, match="DISCORD_TOKEN"):
        load_settings(environ=env)


def test_missing_guild_id_fails() -> None:
    env = {
        "DISCORD_TOKEN": "test-token",
        "DATABASE_PATH": "data/test.sqlite3",
    }
    with pytest.raises(ConfigurationError, match="GUILD_ID"):
        load_settings(environ=env)


@pytest.mark.parametrize(
    "guild_id",
    [
        "abc",
        "123",
        "123456789012345678901",
    ],
)
def test_invalid_guild_id_fails(guild_id: str) -> None:
    env = {
        "DISCORD_TOKEN": "test-token",
        "GUILD_ID": guild_id,
    }
    with pytest.raises(ConfigurationError, match="GUILD_ID"):
        load_settings(environ=env)


def test_valid_configuration_loads() -> None:
    env = {
        "DISCORD_TOKEN": "test-token",
        "GUILD_ID": "123456789012345678",
        "SUPERUSER_IDS": "111, 222",
        "DATABASE_PATH": "data/custom.sqlite3",
    }
    settings = load_settings(environ=env)
    assert settings.discord_token == "test-token"
    assert settings.guild_id == "123456789012345678"
    assert settings.superuser_ids == frozenset({"111", "222"})
    assert settings.database_path == Path("data/custom.sqlite3")


def test_superuser_ids_optional() -> None:
    env = {
        "DISCORD_TOKEN": "test-token",
        "GUILD_ID": "123456789012345678",
    }
    settings = load_settings(environ=env)
    assert settings.superuser_ids == frozenset()
