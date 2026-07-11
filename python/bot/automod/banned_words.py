"""Banned word matching logic."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

from bot.database.models import BannedWordMatchMode
from bot.database.repositories.banned_words import BannedWordRecord

logger = logging.getLogger(__name__)

VALID_MODES = frozenset({BannedWordMatchMode.CONTAINS, BannedWordMatchMode.EXACT})


@dataclass(frozen=True, slots=True)
class BannedWordMatch:
    id: int
    value: str
    match_mode: BannedWordMatchMode
    source: str = "banned_word"


def normalize_match_mode(mode: Any) -> BannedWordMatchMode | None:
    if mode is None:
        return None
    if isinstance(mode, BannedWordMatchMode):
        return mode
    normalized = str(mode).lower()
    if normalized == BannedWordMatchMode.EXACT.value:
        return BannedWordMatchMode.EXACT
    if normalized == BannedWordMatchMode.CONTAINS.value:
        return BannedWordMatchMode.CONTAINS
    return None


def normalize_banned_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def match_banned_word_entry(content: str, entry: BannedWordRecord | dict[str, Any]) -> BannedWordMatch | None:
    if not isinstance(content, str) or entry is None:
        return None

    if isinstance(entry, BannedWordRecord):
        entry_id = entry.id
        value = normalize_banned_value(entry.value)
        match_mode = entry.match_mode
    else:
        entry_id = entry.get("id")
        value = normalize_banned_value(entry.get("value") or entry.get("word"))
        if entry.get("match_mode") is not None:
            match_mode = normalize_match_mode(entry.get("match_mode"))
        elif entry.get("exact") in {1}:
            match_mode = BannedWordMatchMode.EXACT
        else:
            match_mode = BannedWordMatchMode.CONTAINS

    if not value:
        logger.warning(
            "[bannedWords] Skipping malformed entry without value: %s",
            entry_id if entry_id is not None else "(no id)",
        )
        return None

    if match_mode is None:
        logger.warning(
            "[bannedWords] Skipping malformed entry with invalid mode: %s",
            entry_id if entry_id is not None else "(no id)",
        )
        return None

    if match_mode == BannedWordMatchMode.EXACT:
        escaped = re.escape(value)
        if re.search(rf"\b{escaped}\b", content, flags=re.IGNORECASE):
            return BannedWordMatch(
                id=int(entry_id) if entry_id is not None else 0,
                value=value,
                match_mode=match_mode,
            )
        return None

    if value in content.lower():
        return BannedWordMatch(
            id=int(entry_id) if entry_id is not None else 0,
            value=value,
            match_mode=match_mode,
        )

    return None


def find_banned_word_match(
    content: str,
    entries: list[BannedWordRecord],
) -> BannedWordMatch | None:
    for entry in entries:
        match = match_banned_word_entry(content, entry)
        if match:
            return match
    return None


def format_banned_word_reason(match: BannedWordMatch | None) -> str:
    if not match:
        return "Banned word"
    label = "exact" if match.match_mode == BannedWordMatchMode.EXACT else "contains"
    return f"Banned word ({label}): {match.value}"


def is_valid_match_mode(mode: Any) -> bool:
    return normalize_match_mode(mode) is not None
