"""Warning persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.database.models import WarningStatus
from bot.database.repositories.base import Repository
from bot.database.repositories.cases import CasesRepository
from bot.database.transaction import immediate_transaction


@dataclass(frozen=True, slots=True)
class WarningRecord:
    id: int
    guild_id: str
    user_id: str
    moderator_id: str
    reason: str
    source: str | None
    status: WarningStatus
    created_at: str

    @classmethod
    def from_row(cls, row: Any) -> WarningRecord:
        return cls(
            id=int(row["id"]),
            guild_id=row["guild_id"],
            user_id=row["user_id"],
            moderator_id=row["moderator_id"],
            reason=row["reason"] or "",
            source=row["source"],
            status=WarningStatus(row["status"]),
            created_at=row["created_at"],
        )


class WarningsRepository(Repository):
    async def list_active(self, guild_id: str, user_id: str) -> list[WarningRecord]:
        rows = await self._db.fetchall(
            """
            SELECT * FROM warnings
            WHERE guild_id = ? AND user_id = ? AND status = ?
            ORDER BY id DESC
            """,
            (guild_id, user_id, WarningStatus.ACTIVE.value),
        )
        return [WarningRecord.from_row(row) for row in rows]

    async def list_all(self, guild_id: str, user_id: str | None = None) -> list[WarningRecord]:
        if user_id:
            rows = await self._db.fetchall(
                "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id DESC",
                (guild_id, user_id),
            )
        else:
            rows = await self._db.fetchall(
                "SELECT * FROM warnings WHERE guild_id = ? ORDER BY id DESC LIMIT 50",
                (guild_id,),
            )
        return [WarningRecord.from_row(row) for row in rows]

    async def get(self, warning_id: int) -> WarningRecord | None:
        row = await self._db.fetchone("SELECT * FROM warnings WHERE id = ?", (warning_id,))
        return WarningRecord.from_row(row) if row else None

    async def create_with_case(
        self,
        *,
        guild_id: str,
        user_id: str,
        moderator_id: str,
        reason: str,
        source: str | None = None,
        cases: CasesRepository,
    ) -> tuple[int, int]:
        async with immediate_transaction(self._db):
            cursor = await self._db.execute(
                """
                INSERT INTO warnings (guild_id, user_id, moderator_id, reason, source, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (guild_id, user_id, moderator_id, reason, source, WarningStatus.ACTIVE.value),
            )
            warning_id = cursor.lastrowid
            assert warning_id is not None
            case_number = await cases._insert_case(
                guild_id=guild_id,
                user_id=user_id,
                moderator_id=moderator_id,
                action="warn",
                reason=reason,
                source=source,
                metadata={"warning_id": warning_id},
            )
            return int(warning_id), case_number

    async def void(self, warning_id: int) -> bool:
        cursor = await self._db.execute(
            "UPDATE warnings SET status = ? WHERE id = ? AND status = ?",
            (WarningStatus.VOIDED.value, warning_id, WarningStatus.ACTIVE.value),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def void_all_for_user(self, guild_id: str, user_id: str) -> int:
        cursor = await self._db.execute(
            """
            UPDATE warnings SET status = ?
            WHERE guild_id = ? AND user_id = ? AND status = ?
            """,
            (WarningStatus.VOIDED.value, guild_id, user_id, WarningStatus.ACTIVE.value),
        )
        await self._db.commit()
        return cursor.rowcount

    async def active_count(self, guild_id: str, user_id: str) -> int:
        row = await self._db.fetchone(
            """
            SELECT COUNT(*) AS count FROM warnings
            WHERE guild_id = ? AND user_id = ? AND status = ?
            """,
            (guild_id, user_id, WarningStatus.ACTIVE.value),
        )
        return int(row["count"]) if row else 0
