"""Banned word matching and repository tests (ported from verify-banned-words.mjs)."""

from __future__ import annotations

import pytest
from bot.automod.banned_words import (
    BannedWordMatch,
    find_banned_word_match,
    format_banned_word_reason,
    match_banned_word_entry,
)
from bot.database.models import BannedWordMatchMode
from bot.database.repositories.banned_words import BannedWordRecord
from bot.errors import DatabaseError
from tests.conftest import Repositories


def _entry(entry_id: int, value: str, match_mode: str) -> dict[str, object]:
    return {"id": entry_id, "guild_id": "match-guild", "value": value, "match_mode": match_mode}


def test_matching_behavior() -> None:
    contains_entry = _entry(1, "bad", "contains")
    exact_entry = _entry(2, "bad", "exact")

    assert (
        find_banned_word_match("this is bad stuff", [_record(contains_entry), _record(exact_entry)]).match_mode
        == BannedWordMatchMode.CONTAINS
    )
    assert (
        find_banned_word_match("this is bad stuff", [_record(exact_entry), _record(contains_entry)]).match_mode
        == BannedWordMatchMode.EXACT
    )
    assert (
        find_banned_word_match("bad", [_record(exact_entry), _record(contains_entry)]).match_mode
        == BannedWordMatchMode.EXACT
    )
    assert find_banned_word_match("xxbadxx", [_record(contains_entry)]).value == "bad"
    assert find_banned_word_match("xxbadxx", [_record(exact_entry)]) is None
    assert find_banned_word_match("BAD WORD", [_record(contains_entry)]).value == "bad"
    assert find_banned_word_match("word, bad!", [_record(exact_entry)]).match_mode == BannedWordMatchMode.EXACT
    assert find_banned_word_match("wordbad", [_record(exact_entry)]) is None
    assert (
        find_banned_word_match(
            "first bad then worse",
            [_record(_entry(3, "bad", "contains")), _record(_entry(4, "worse", "contains"))],
        ).value
        == "bad"
    )
    assert (
        format_banned_word_reason(
            BannedWordMatch(id=1, value="bad", match_mode=BannedWordMatchMode.EXACT),
        )
        == "Banned word (exact): bad"
    )


def _record(raw: dict[str, object]) -> BannedWordRecord:
    return BannedWordRecord(
        id=int(raw["id"]),  # type: ignore[arg-type]
        guild_id=str(raw["guild_id"]),
        value=str(raw["value"]),
        match_mode=BannedWordMatchMode(str(raw["match_mode"])),
        created_by=None,
        created_at="2026-01-01T00:00:00.000Z",
    )


def test_malformed_entry_handling() -> None:
    assert match_banned_word_entry("test", {"value": "", "match_mode": "contains"}) is None
    assert match_banned_word_entry("test", {"value": "ok", "match_mode": "invalid"}) is None


@pytest.mark.asyncio
async def test_duplicate_and_dual_mode_entries(repos: Repositories, guild_id: str) -> None:
    await repos.banned_words.add(guild_id, "spam", BannedWordMatchMode.CONTAINS, created_by="mod-1")
    with pytest.raises(DatabaseError, match="duplicate_banned_word"):
        await repos.banned_words.add(guild_id, "spam", BannedWordMatchMode.CONTAINS, created_by="mod-1")

    exact_id = await repos.banned_words.add(guild_id, "spam", BannedWordMatchMode.EXACT, created_by="mod-1")
    words = await repos.banned_words.list_for_guild(guild_id)
    assert len(words) == 2
    assert any(word.id == exact_id and word.match_mode == BannedWordMatchMode.EXACT for word in words)


@pytest.mark.asyncio
async def test_remove_by_id_keeps_other_mode(repos: Repositories, guild_id: str) -> None:
    contains_id = await repos.banned_words.add(guild_id, "dual", BannedWordMatchMode.CONTAINS, created_by="mod")
    await repos.banned_words.add(guild_id, "dual", BannedWordMatchMode.EXACT, created_by="mod")
    removed = await repos.banned_words.remove(guild_id, contains_id)
    assert removed is True
    remaining = await repos.banned_words.list_for_guild(guild_id)
    assert len(remaining) == 1
    assert remaining[0].match_mode == BannedWordMatchMode.EXACT


@pytest.mark.asyncio
async def test_legacy_automod_words_import_mapping(
    migrated_database,
    empty_legacy_store,
) -> None:
    from scripts.import_legacy_json import ImportSummary, import_data

    store = empty_legacy_store
    store["automod_words"] = [
        {"guild_id": "guild-migrate", "word": "substring", "exact": 0},
        {"guild_id": "guild-migrate", "word": "token", "exact": 1},
        {"guild_id": "guild-migrate", "word": "both", "exact": 0},
        {"guild_id": "guild-migrate", "word": "both", "exact": 1},
    ]
    summary = ImportSummary()
    await import_data(migrated_database, store, dry_run=False, summary=summary)
    rows = await migrated_database.fetchall(
        "SELECT * FROM banned_words WHERE guild_id = ?",
        ("guild-migrate",),
    )
    assert len(rows) == 4
    modes = {row["match_mode"] for row in rows}
    assert modes == {"contains", "exact"}
