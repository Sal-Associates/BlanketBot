"""Automod threshold validation and helpers."""

from __future__ import annotations

import logging
import re
from typing import Any

import discord

from bot.constants import AUTOMOD_THRESHOLD_DEFAULTS, CAPS_MIN_LETTERS
from bot.database.repositories.guild_settings import GuildSettings
from bot.utils.time import format_duration, parse_duration

logger = logging.getLogger(__name__)

THRESHOLD_KEYS = tuple(AUTOMOD_THRESHOLD_DEFAULTS.keys())
INTEGER_KEYS = frozenset({"caps_threshold", "spam_threshold", "mention_threshold"})

THRESHOLD_RANGES: dict[str, dict[str, int]] = {
    "caps_threshold": {"min": 50, "max": 100},
    "spam_threshold": {"min": 3, "max": 20},
    "spam_interval_ms": {"min": 1000, "max": 60_000},
    "mention_threshold": {"min": 2, "max": 50},
}


def _parse_integer(raw: Any) -> int | None:
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and re.fullmatch(r"\d+", raw.strip()):
        return int(raw.strip())
    return None


def _parse_ms(raw: Any) -> int | None:
    if isinstance(raw, (int, float)) and float(raw) == int(raw):
        return int(raw)
    if isinstance(raw, str) and re.fullmatch(r"\d+", raw.strip()):
        return int(raw.strip())
    return None


def coerce_threshold_value(
    key: str,
    raw: Any,
    default_value: int | None = None,
) -> tuple[int, bool]:
    default = default_value if default_value is not None else AUTOMOD_THRESHOLD_DEFAULTS[key]
    range_ = THRESHOLD_RANGES.get(key)
    if range_ is None:
        return default, False

    if raw is None:
        return default, False

    if key == "spam_interval_ms":
        parsed = _parse_ms(raw)
    else:
        parsed = _parse_integer(raw)
        if parsed is not None and key not in INTEGER_KEYS:
            parsed = None

    if parsed is None:
        return default, True

    if key in INTEGER_KEYS and not isinstance(parsed, int):
        return default, True

    if parsed < range_["min"] or parsed > range_["max"]:
        return default, True

    return parsed, False


def normalize_automod_thresholds(
    settings: GuildSettings,
    *,
    log: logging.Logger | None = None,
) -> GuildSettings:
    log_fn = log or logger
    updates: dict[str, int] = {}
    source = {
        "caps_threshold": settings.caps_threshold,
        "spam_threshold": settings.spam_threshold,
        "spam_interval_ms": settings.spam_interval_ms,
        "mention_threshold": settings.mention_threshold,
    }
    for key in THRESHOLD_KEYS:
        value, replaced = coerce_threshold_value(key, source.get(key))
        if replaced and source.get(key) is not None and source.get(key) != value:
            log_fn.warning(
                "[automod] Invalid %s=%r; using %s",
                key,
                source.get(key),
                value,
            )
        updates[key] = value
    return GuildSettings(**{**settings.__dict__, **updates})


def resolve_automod_thresholds(settings: GuildSettings) -> GuildSettings:
    return normalize_automod_thresholds(settings)


def validate_caps_threshold_input(input_value: str | None) -> dict[str, Any]:
    trimmed = (input_value or "").strip()
    if not trimmed or not re.fullmatch(r"\d+", trimmed):
        return {"ok": False, "error": "Caps threshold must be a whole number percentage."}
    value = int(trimmed)
    range_ = THRESHOLD_RANGES["caps_threshold"]
    if value < range_["min"] or value > range_["max"]:
        return {
            "ok": False,
            "error": f"Caps threshold must be between {range_['min']} and {range_['max']}.",
        }
    return {"ok": True, "value": value}


def validate_spam_count_input(input_value: str | None) -> dict[str, Any]:
    trimmed = (input_value or "").strip()
    if not trimmed or not re.fullmatch(r"\d+", trimmed):
        return {"ok": False, "error": "Spam count must be a whole number."}
    value = int(trimmed)
    range_ = THRESHOLD_RANGES["spam_threshold"]
    if value < range_["min"] or value > range_["max"]:
        return {
            "ok": False,
            "error": f"Spam count must be between {range_['min']} and {range_['max']} messages.",
        }
    return {"ok": True, "value": value}


def validate_spam_window_input(input_value: str | None) -> dict[str, Any]:
    trimmed = (input_value or "").strip()
    if not trimmed:
        return {"ok": False, "error": "Provide a duration such as `5s` or `1m`."}

    if re.fullmatch(r"\d+", trimmed):
        ms_value = int(trimmed)
    else:
        ms_value = parse_duration(trimmed)

    if not ms_value:
        return {"ok": False, "error": "Spam window must be a duration such as `5s` or `1m`."}

    range_ = THRESHOLD_RANGES["spam_interval_ms"]
    if ms_value < range_["min"] or ms_value > range_["max"]:
        return {"ok": False, "error": "Spam window must be between 1 second and 60 seconds."}

    return {"ok": True, "value": round(ms_value)}


def validate_mention_threshold_input(input_value: str | None) -> dict[str, Any]:
    trimmed = (input_value or "").strip()
    if not trimmed or not re.fullmatch(r"\d+", trimmed):
        return {"ok": False, "error": "Mention threshold must be a whole number."}
    value = int(trimmed)
    range_ = THRESHOLD_RANGES["mention_threshold"]
    if value < range_["min"] or value > range_["max"]:
        return {
            "ok": False,
            "error": f"Mention threshold must be between {range_['min']} and {range_['max']}.",
        }
    return {"ok": True, "value": value}


def caps_percentage(content: str) -> float:
    letters = re.sub(r"[^a-zA-Z]", "", content)
    if len(letters) < CAPS_MIN_LETTERS:
        return 0.0
    caps = len(re.sub(r"[^A-Z]", "", letters))
    return (caps / len(letters)) * 100


def count_mention_targets(message: discord.Message) -> int:
    return len(message.mentions) + len(message.role_mentions)


def is_mass_mention(message: discord.Message, mention_threshold: int) -> bool:
    if message.mention_everyone:
        return True
    return count_mention_targets(message) >= mention_threshold


def format_spam_window(ms_value: int) -> str:
    return format_duration(ms_value)


def format_threshold_show(
    settings: GuildSettings,
    *,
    module_disabled: bool = False,
) -> str:
    thresholds = resolve_automod_thresholds(settings)
    inactive = " (saved, inactive — Automod module disabled)" if module_disabled else ""

    lines = [
        (
            f"**Caps:** {thresholds.caps_threshold}% at {CAPS_MIN_LETTERS}+ letters — "
            f"anti-caps {'enabled' if settings.anti_caps else 'disabled'}{inactive}"
        ),
        (
            f"**Spam:** {thresholds.spam_threshold} messages within "
            f"{format_spam_window(thresholds.spam_interval_ms)} — "
            f"anti-spam {'enabled' if settings.anti_spam else 'disabled'}{inactive}"
        ),
        (
            f"**Mentions:** {thresholds.mention_threshold} user/role mentions per message "
            f"(@everyone/@here always flagged) — "
            f"anti-mention {'enabled' if settings.anti_mention else 'disabled'}{inactive}"
        ),
        "",
        "_Minimum caps length is fixed at 8 letters (not configurable)._",
        "_Use `?automod threshold reset <caps|spam|mentions|all>` to restore defaults._",
    ]
    return "\n".join(lines)


def get_threshold_reset_updates(target: str) -> dict[str, int] | None:
    if target == "caps":
        return {"caps_threshold": AUTOMOD_THRESHOLD_DEFAULTS["caps_threshold"]}
    if target == "spam":
        return {
            "spam_threshold": AUTOMOD_THRESHOLD_DEFAULTS["spam_threshold"],
            "spam_interval_ms": AUTOMOD_THRESHOLD_DEFAULTS["spam_interval_ms"],
        }
    if target == "mentions":
        return {"mention_threshold": AUTOMOD_THRESHOLD_DEFAULTS["mention_threshold"]}
    if target == "all":
        return dict(AUTOMOD_THRESHOLD_DEFAULTS)
    return None
