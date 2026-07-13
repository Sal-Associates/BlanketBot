"""Banned word list persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.database.models import BannedWordMatchMode
from bot.database.repositories.base import Repository
from bot.errors import DatabaseError


@dataclass(frozen=True, slots=True)
class BannedWordRecord:
    id: int
    guild_id: str
    value: str
    match_mode: BannedWordMatchMode
    created_by: str | None
    created_at: str

    @classmethod
    def from_row(cls, row: Any) -> BannedWordRecord:
        return cls(
            id=int(row["id"]),
            guild_id=row["guild_id"],
            value=row["value"],
            match_mode=BannedWordMatchMode(row["match_mode"]),
            created_by=row["created_by"],
            created_at=row["created_at"],
        )


class BannedWordsRepository(Repository):
    async def add(
        self,
        guild_id: str,
        value: str,
        match_mode: BannedWordMatchMode | str,
        *,
        created_by: str | None = None,
    ) -> int:
        trimmed = (value or "").strip()
        if not trimmed:
            raise DatabaseError("Banned word value cannot be empty")

        mode = (
            match_mode if isinstance(match_mode, BannedWordMatchMode) else BannedWordMatchMode(str(match_mode).lower())
        )
        stored_value = trimmed.lower()

        existing = await self._db.fetchone(
            """
            SELECT id FROM banned_words
            WHERE guild_id = ? AND value = ? AND match_mode = ?
            """,
            (guild_id, stored_value, mode.value),
        )
        if existing:
            raise DatabaseError("duplicate_banned_word")

        cursor = await self._db.execute(
            """
            INSERT INTO banned_words (guild_id, value, match_mode, created_by)
            VALUES (?, ?, ?, ?)
            """,
            (guild_id, stored_value, mode.value, created_by),
        )
        await self._db.commit()
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)

    async def remove(self, guild_id: str, entry_id: int) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM banned_words WHERE guild_id = ? AND id = ?",
            (guild_id, entry_id),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def remove_by_value(
        self,
        guild_id: str,
        value: str,
        match_mode: BannedWordMatchMode | str = BannedWordMatchMode.CONTAINS,
    ) -> bool:
        mode = (
            match_mode if isinstance(match_mode, BannedWordMatchMode) else BannedWordMatchMode(str(match_mode).lower())
        )
        stored_value = (value or "").strip().lower()
        cursor = await self._db.execute(
            """
            DELETE FROM banned_words
            WHERE guild_id = ? AND value = ? AND match_mode = ?
            """,
            (guild_id, stored_value, mode.value),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def list_for_guild(self, guild_id: str) -> list[BannedWordRecord]:
        rows = await self._db.fetchall(
            """
            SELECT * FROM banned_words
            WHERE guild_id = ?
            ORDER BY value ASC, match_mode ASC
            """,
            (guild_id,),
        )
        return [BannedWordRecord.from_row(row) for row in rows]
