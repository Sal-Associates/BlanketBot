"""Case persistence with safe numbering."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from bot.database.repositories.base import Repository
from bot.database.transaction import immediate_transaction


@dataclass(frozen=True, slots=True)
class CaseRecord:
    guild_id: str
    case_number: int
    user_id: str
    moderator_id: str
    action: str
    reason: str | None
    source: str | None
    status: str | None
    metadata: dict[str, Any]
    created_at: str

    @classmethod
    def from_row(cls, row: Any) -> CaseRecord:
        metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        return cls(
            guild_id=row["guild_id"],
            case_number=int(row["case_number"]),
            user_id=row["user_id"],
            moderator_id=row["moderator_id"],
            action=row["action"],
            reason=row["reason"],
            source=row["source"],
            status=row["status"],
            metadata=metadata,
            created_at=row["created_at"],
        )


class CasesRepository(Repository):
    async def _allocate_case_number(self, guild_id: str) -> int:
        await self._db.execute(
            """
            INSERT INTO case_counters (guild_id, next_case_number)
            VALUES (?, 1)
            ON CONFLICT(guild_id) DO NOTHING
            """,
            (guild_id,),
        )
        row = await self._db.fetchone(
            "SELECT next_case_number FROM case_counters WHERE guild_id = ?",
            (guild_id,),
        )
        assert row is not None
        case_number = int(row["next_case_number"])
        await self._db.execute(
            "UPDATE case_counters SET next_case_number = ? WHERE guild_id = ?",
            (case_number + 1, guild_id),
        )
        return case_number

    async def _insert_case(
        self,
        *,
        guild_id: str,
        user_id: str,
        moderator_id: str,
        action: str,
        reason: str | None,
        source: str | None = None,
        status: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        case_number = await self._allocate_case_number(guild_id)
        await self._db.execute(
            """
            INSERT INTO cases (
                guild_id, case_number, user_id, moderator_id, action,
                reason, source, status, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                case_number,
                user_id,
                moderator_id,
                action,
                reason,
                source,
                status,
                json.dumps(metadata or {}),
            ),
        )
        return case_number

    async def create_case(
        self,
        *,
        guild_id: str,
        user_id: str,
        moderator_id: str,
        action: str,
        reason: str | None,
        source: str | None = None,
        status: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        async with immediate_transaction(self._db):
            return await self._insert_case(
                guild_id=guild_id,
                user_id=user_id,
                moderator_id=moderator_id,
                action=action,
                reason=reason,
                source=source,
                status=status,
                metadata=metadata,
            )

    async def get_case(self, guild_id: str, case_number: int) -> CaseRecord | None:
        row = await self._db.fetchone(
            "SELECT * FROM cases WHERE guild_id = ? AND case_number = ?",
            (guild_id, case_number),
        )
        return CaseRecord.from_row(row) if row else None

    async def list_for_user(self, guild_id: str, user_id: str, *, limit: int = 15) -> list[CaseRecord]:
        rows = await self._db.fetchall(
            """
            SELECT * FROM cases
            WHERE guild_id = ? AND user_id = ?
            ORDER BY case_number DESC
            LIMIT ?
            """,
            (guild_id, user_id, limit),
        )
        return [CaseRecord.from_row(row) for row in rows]

    async def list_recent(self, guild_id: str, *, limit: int = 10) -> list[CaseRecord]:
        rows = await self._db.fetchall(
            """
            SELECT * FROM cases WHERE guild_id = ?
            ORDER BY case_number DESC LIMIT ?
            """,
            (guild_id, limit),
        )
        return [CaseRecord.from_row(row) for row in rows]
