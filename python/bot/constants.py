"""Application constants aligned with the JavaScript reference implementation."""

from __future__ import annotations

DEFAULT_PREFIX = "?"
DEFAULT_DATABASE_PATH = "data/modbot.sqlite3"

# Automod threshold defaults (see node-bun/src/utils/automodThresholds.js)
CAPS_MIN_LETTERS = 8
AUTOMOD_THRESHOLD_DEFAULTS: dict[str, int] = {
    "caps_threshold": 70,
    "spam_threshold": 5,
    "spam_interval_ms": 5000,
    "mention_threshold": 5,
}

STRIKE_DEFAULTS: dict[str, int] = {
    "strike_enabled": 1,
    "strike_mute_at": 3,
    "strike_ban_at": 5,
}

SNOWFLAKE_MIN_LEN = 17
SNOWFLAKE_MAX_LEN = 20

MIGRATIONS_TABLE = "schema_migrations"
