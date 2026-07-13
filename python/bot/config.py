"""Environment configuration loading and validation."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from bot.constants import DEFAULT_DATABASE_PATH, SNOWFLAKE_MAX_LEN, SNOWFLAKE_MIN_LEN
from bot.errors import ConfigurationError

_SNOWFLAKE_RE = re.compile(rf"^\d{{{SNOWFLAKE_MIN_LEN},{SNOWFLAKE_MAX_LEN}}}$")


@dataclass(frozen=True, slots=True)
class Settings:
    discord_token: str
    guild_id: str
    superuser_ids: frozenset[str]
    database_path: Path


def _parse_superuser_ids(raw: str | None) -> frozenset[str]:
    if not raw or not raw.strip():
        return frozenset()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def _validate_snowflake(name: str, value: str) -> str:
    trimmed = value.strip()
    if not trimmed.isdigit():
        raise ConfigurationError(f"{name} must contain only digits")
    if not _SNOWFLAKE_RE.match(trimmed):
        raise ConfigurationError(
            f"{name} does not look like a valid Discord snowflake "
            f"(expected {SNOWFLAKE_MIN_LEN}–{SNOWFLAKE_MAX_LEN} digits)",
        )
    return trimmed


def load_settings(*, env_file: Path | None = None, environ: os._Environ[str] | None = None) -> Settings:
    """Load settings from environment, optionally merging a .env file."""
    if env_file is not None:
        load_dotenv(env_file, override=False)
    else:
        load_dotenv(override=False)

    env = environ if environ is not None else os.environ

    token = env.get("DISCORD_TOKEN", "").strip()
    if not token:
        raise ConfigurationError("DISCORD_TOKEN is required")

    guild_raw = env.get("GUILD_ID", "").strip()
    if not guild_raw:
        raise ConfigurationError("GUILD_ID is required")
    guild_id = _validate_snowflake("GUILD_ID", guild_raw)

    db_raw = env.get("DATABASE_PATH", DEFAULT_DATABASE_PATH).strip() or DEFAULT_DATABASE_PATH
    database_path = Path(db_raw)

    return Settings(
        discord_token=token,
        guild_id=guild_id,
        superuser_ids=_parse_superuser_ids(env.get("SUPERUSER_IDS")),
        database_path=database_path,
    )
