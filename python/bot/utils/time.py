"""Duration parsing and formatting."""

from __future__ import annotations

import re

_DURATION_RE = re.compile(
    r"^(\d+)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)$",
    re.IGNORECASE,
)


def parse_duration(input_value: str | None) -> int | None:
    if not input_value:
        return None
    raw = input_value.strip().lower()
    match = _DURATION_RE.match(raw)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2).lower()
    if unit.startswith("s"):
        ms = amount * 1000
    elif unit.startswith("m"):
        ms = amount * 60_000
    elif unit.startswith("h"):
        ms = amount * 3_600_000
    else:
        ms = amount * 86_400_000
    return ms if ms >= 1000 else None


def format_duration(ms_value: int) -> str:
    seconds = ms_value // 1000
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24
    if days > 0:
        return f"{days}d {hours % 24}h"
    if hours > 0:
        return f"{hours}h {minutes % 60}m"
    if minutes > 0:
        return f"{minutes}m {seconds % 60}s"
    return f"{seconds}s"


def format_timestamp(ts_ms: int) -> str:
    return f"<t:{ts_ms // 1000}:R>"


def format_date(ts_ms: int) -> str:
    return f"<t:{ts_ms // 1000}:f>"


def format_iso_date(iso_value: str) -> str:
    from datetime import datetime

    normalized = iso_value.replace("Z", "+00:00")
    timestamp = int(datetime.fromisoformat(normalized).timestamp())
    return f"<t:{timestamp}:f>"
