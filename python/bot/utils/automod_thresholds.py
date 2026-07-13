"""Automod threshold validation and display helpers."""

from __future__ import annotations

import re
from typing import Any

from bot.constants import AUTOMOD_THRESHOLD_DEFAULTS, CAPS_MIN_LETTERS
from bot.database.repositories.guild_settings import GuildSettings
from bot.utils.time import format_duration, parse_duration

_THRESHOLD_RANGES: dict[str, tuple[int, int]] = {
    "caps_threshold": (50, 100),
    "spam_threshold": (3, 20),
    "spam_interval_ms": (1000, 60_000),
    "mention_threshold": (2, 50),
}


def _parse_int(raw: str) -> int | None:
    trimmed = raw.strip()
    if re.fullmatch(r"\d+", trimmed):
        return int(trimmed)
    return None


def validate_caps_threshold_input(raw: str) -> dict[str, Any]:
    value = _parse_int(raw)
    low, high = _THRESHOLD_RANGES["caps_threshold"]
    if value is None:
        return {"ok": False, "error": "Caps threshold must be a whole number percentage."}
    if value < low or value > high:
        return {"ok": False, "error": f"Caps threshold must be between {low} and {high}."}
    return {"ok": True, "value": value}


def validate_spam_count_input(raw: str) -> dict[str, Any]:
    value = _parse_int(raw)
    low, high = _THRESHOLD_RANGES["spam_threshold"]
    if value is None:
        return {"ok": False, "error": "Spam count must be a whole number."}
    if value < low or value > high:
        return {"ok": False, "error": f"Spam count must be between {low} and {high} messages."}
    return {"ok": True, "value": value}


def validate_spam_window_input(raw: str) -> dict[str, Any]:
    trimmed = raw.strip()
    if not trimmed:
        return {"ok": False, "error": "Provide a duration such as `5s` or `1m`."}
    ms_value = _parse_int(trimmed) or parse_duration(trimmed)
    if ms_value is None:
        return {"ok": False, "error": "Spam window must be a duration such as `5s` or `1m`."}
    low, high = _THRESHOLD_RANGES["spam_interval_ms"]
    if ms_value < low or ms_value > high:
        return {"ok": False, "error": "Spam window must be between 1 second and 60 seconds."}
    return {"ok": True, "value": int(ms_value)}


def validate_mention_threshold_input(raw: str) -> dict[str, Any]:
    value = _parse_int(raw)
    low, high = _THRESHOLD_RANGES["mention_threshold"]
    if value is None:
        return {"ok": False, "error": "Mention threshold must be a whole number."}
    if value < low or value > high:
        return {"ok": False, "error": f"Mention threshold must be between {low} and {high}."}
    return {"ok": True, "value": value}


def format_spam_window(ms_value: int) -> str:
    return format_duration(ms_value)


def format_threshold_show(settings: GuildSettings, *, module_disabled: bool = False) -> str:
    inactive = " (saved, inactive — Automod module disabled)" if module_disabled else ""
    lines = [
        (
            f"**Caps:** {settings.caps_threshold}% at {CAPS_MIN_LETTERS}+ letters "
            f"— anti-caps {'enabled' if settings.anti_caps else 'disabled'}{inactive}"
        ),
        (
            f"**Spam:** {settings.spam_threshold} messages within "
            f"{format_spam_window(settings.spam_interval_ms)} "
            f"— anti-spam {'enabled' if settings.anti_spam else 'disabled'}{inactive}"
        ),
        (
            f"**Mentions:** {settings.mention_threshold} user/role mentions per message "
            f"(@everyone/@here always flagged) "
            f"— anti-mention {'enabled' if settings.anti_mention else 'disabled'}{inactive}"
        ),
        "",
        "_Minimum caps length is fixed at 8 letters (not configurable)._",
        "_Use `?automod threshold reset <caps|spam|mentions|all>` to restore defaults._",
    ]
    return "\n".join(lines)


def get_threshold_reset_updates(target: str) -> dict[str, int] | None:
    normalized = target.lower()
    if normalized == "caps":
        return {"caps_threshold": AUTOMOD_THRESHOLD_DEFAULTS["caps_threshold"]}
    if normalized == "spam":
        return {
            "spam_threshold": AUTOMOD_THRESHOLD_DEFAULTS["spam_threshold"],
            "spam_interval_ms": AUTOMOD_THRESHOLD_DEFAULTS["spam_interval_ms"],
        }
    if normalized == "mentions":
        return {"mention_threshold": AUTOMOD_THRESHOLD_DEFAULTS["mention_threshold"]}
    if normalized == "all":
        return dict(AUTOMOD_THRESHOLD_DEFAULTS)
    return None
