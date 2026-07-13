"""Staff note persistence with revision history."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.database.repositories.base import Repository
from bot.database.transaction import immediate_transaction

_DELETED_SENTINEL = "[deleted]"


@dataclass(frozen=True, slots=True)
class NoteRecord:
    id: int
    guild_id: str
    user_id: str
    author_id: str
    content: str
    created_at: str
    updated_at: str

    @property
    def is_deleted(self) -> bool:
        return self.content == _DELETED_SENTINEL

    @classmethod
    def from_row(cls, row: Any) -> NoteRecord:
        return cls(
            id=int(row["id"]),
            guild_id=row["guild_id"],
            user_id=row["user_id"],
            author_id=row["author_id"],
            content=row["content"] or "",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


@dataclass(frozen=True, slots=True)
class NoteRevisionRecord:
    id: int
    note_id: int
    guild_id: str
    author_id: str
    content: str
    created_at: str

    @classmethod
    def from_row(cls, row: Any) -> NoteRevisionRecord:
        return cls(
            id=int(row["id"]),
            note_id=int(row["note_id"]),
            guild_id=row["guild_id"],
            author_id=row["author_id"],
            content=row["content"] or "",
            created_at=row["created_at"],
        )


class NotesRepository(Repository):
    async def create(
        self,
        *,
        guild_id: str,
        user_id: str,
        author_id: str,
        content: str,
    ) -> int:
        cursor = await self._db.execute(
            """
            INSERT INTO notes (guild_id, user_id, author_id, content)
            VALUES (?, ?, ?, ?)
            """,
            (guild_id, user_id, author_id, content),
        )
        await self._db.commit()
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)

    async def get(self, note_id: int) -> NoteRecord | None:
        row = await self._db.fetchone("SELECT * FROM notes WHERE id = ?", (note_id,))
        return NoteRecord.from_row(row) if row else None

    async def list_for_user(
        self,
        guild_id: str,
        user_id: str,
        *,
        include_deleted: bool = False,
    ) -> list[NoteRecord]:
        if include_deleted:
            rows = await self._db.fetchall(
                """
                SELECT * FROM notes
                WHERE guild_id = ? AND user_id = ?
                ORDER BY id DESC
                """,
                (guild_id, user_id),
            )
        else:
            rows = await self._db.fetchall(
                """
                SELECT * FROM notes
                WHERE guild_id = ? AND user_id = ? AND content != ?
                ORDER BY id DESC
                """,
                (guild_id, user_id, _DELETED_SENTINEL),
            )
        return [NoteRecord.from_row(row) for row in rows]

    async def list_revisions(self, note_id: int) -> list[NoteRevisionRecord]:
        rows = await self._db.fetchall(
            """
            SELECT * FROM note_revisions
            WHERE note_id = ?
            ORDER BY id DESC
            """,
            (note_id,),
        )
        return [NoteRevisionRecord.from_row(row) for row in rows]

    async def update(
        self,
        note_id: int,
        *,
        author_id: str,
        content: str,
    ) -> bool:
        async with immediate_transaction(self._db):
            row = await self._db.fetchone(
                "SELECT * FROM notes WHERE id = ? AND content != ?",
                (note_id, _DELETED_SENTINEL),
            )
            if not row:
                return False
            note = NoteRecord.from_row(row)
            await self._db.execute(
                """
                INSERT INTO note_revisions (note_id, guild_id, author_id, content)
                VALUES (?, ?, ?, ?)
                """,
                (note.id, note.guild_id, note.author_id, note.content),
            )
            cursor = await self._db.execute(
                """
                UPDATE notes
                SET content = ?, author_id = ?,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                WHERE id = ?
                """,
                (content, author_id, note_id),
            )
            return cursor.rowcount > 0

    async def delete(self, note_id: int, *, soft: bool = False) -> bool:
        row = await self._db.fetchone("SELECT * FROM notes WHERE id = ?", (note_id,))
        if not row:
            return False
        note = NoteRecord.from_row(row)
        if note.is_deleted:
            return False

        if soft:
            async with immediate_transaction(self._db):
                await self._db.execute(
                    """
                    INSERT INTO note_revisions (note_id, guild_id, author_id, content)
                    VALUES (?, ?, ?, ?)
                    """,
                    (note.id, note.guild_id, note.author_id, note.content),
                )
                cursor = await self._db.execute(
                    """
                    UPDATE notes
                    SET content = ?,
                        updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                    WHERE id = ?
                    """,
                    (_DELETED_SENTINEL, note_id),
                )
                return cursor.rowcount > 0

        cursor = await self._db.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        await self._db.commit()
        return cursor.rowcount > 0
