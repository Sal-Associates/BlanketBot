"""Moderation queue persistence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from bot.database.models import ModQueueStatus, WarningStatus
from bot.database.repositories.base import Repository
from bot.database.repositories.cases import CasesRepository
from bot.database.transaction import immediate_transaction


@dataclass(frozen=True, slots=True)
class ModQueueRecord:
    id: int
    guild_id: str
    channel_id: str
    author_id: str
    message_id: str | None
    queue_message_id: str | None
    content: str | None
    reason: str
    status: ModQueueStatus
    moderator_id: str | None
    created_at: str
    resolved_at: str | None

    @classmethod
    def from_row(cls, row: Any) -> ModQueueRecord:
        return cls(
            id=int(row["id"]),
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            author_id=row["author_id"],
            message_id=row["message_id"],
            queue_message_id=row["queue_message_id"],
            content=row["content"],
            reason=row["reason"] or "",
            status=ModQueueStatus(row["status"]),
            moderator_id=row["moderator_id"],
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
        )


@dataclass(frozen=True, slots=True)
class ModQueueDecisionResult:
    status: Literal["not_found", "already_processed", "success"]
    decision: Literal["approved", "denied"] | None = None
    case_number: int | None = None
    warning_id: int | None = None
    entry: ModQueueRecord | None = None
    current_status: str | None = None


class ModQueueRepository(Repository):
    async def add(
        self,
        *,
        guild_id: str,
        channel_id: str,
        author_id: str,
        content: str | None,
        reason: str,
        message_id: str | None = None,
    ) -> ModQueueRecord:
        cursor = await self._db.execute(
            """
            INSERT INTO mod_queue (
                guild_id, channel_id, author_id, message_id, content, reason, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                channel_id,
                author_id,
                message_id,
                content,
                reason,
                ModQueueStatus.PENDING.value,
            ),
        )
        await self._db.commit()
        assert cursor.lastrowid is not None
        entry = await self.get(int(cursor.lastrowid))
        assert entry is not None
        return entry

    async def get(self, entry_id: int) -> ModQueueRecord | None:
        row = await self._db.fetchone("SELECT * FROM mod_queue WHERE id = ?", (entry_id,))
        return ModQueueRecord.from_row(row) if row else None

    async def set_queue_message_id(self, entry_id: int, queue_message_id: str) -> bool:
        cursor = await self._db.execute(
            "UPDATE mod_queue SET queue_message_id = ? WHERE id = ?",
            (queue_message_id, entry_id),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def process_decision(
        self,
        *,
        entry_id: int,
        moderator_id: str,
        decision: Literal["approve", "deny"],
        cases: CasesRepository,
        warn_reason: str | None = None,
        case_action: str,
        case_reason: str,
    ) -> ModQueueDecisionResult:
        entry = await self.get(entry_id)
        if not entry:
            return ModQueueDecisionResult(status="not_found")
        if entry.status != ModQueueStatus.PENDING:
            return ModQueueDecisionResult(
                status="already_processed",
                current_status=entry.status.value,
            )

        new_status = ModQueueStatus.APPROVED if decision == "approve" else ModQueueStatus.DENIED
        cursor = await self._db.execute(
            """
            UPDATE mod_queue
            SET status = ?, moderator_id = ?,
                resolved_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ? AND status = ?
            """,
            (new_status.value, moderator_id, entry_id, ModQueueStatus.PENDING.value),
        )
        await self._db.commit()
        if cursor.rowcount == 0:
            current = await self.get(entry_id)
            return ModQueueDecisionResult(
                status="already_processed",
                current_status=current.status.value if current else None,
            )

        entry = await self.get(entry_id)
        assert entry is not None

        if decision == "approve":
            case_number = await cases.create_case(
                guild_id=entry.guild_id,
                user_id=entry.author_id,
                moderator_id=moderator_id,
                action=case_action,
                reason=case_reason,
                source="mod_queue",
                metadata={"queue_id": entry_id},
            )
            updated = await self.get(entry_id)
            assert updated is not None
            return ModQueueDecisionResult(
                status="success",
                decision="approved",
                case_number=case_number,
                entry=updated,
            )

        if not warn_reason:
            return ModQueueDecisionResult(
                status="success",
                decision="denied",
                entry=entry,
            )

        async with immediate_transaction(self._db):
            warning_cursor = await self._db.execute(
                """
                INSERT INTO warnings (guild_id, user_id, moderator_id, reason, source, status)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.guild_id,
                    entry.author_id,
                    moderator_id,
                    warn_reason,
                    "mod_queue",
                    WarningStatus.ACTIVE.value,
                ),
            )
            warning_id = int(warning_cursor.lastrowid)
            case_number = await cases._insert_case(
                guild_id=entry.guild_id,
                user_id=entry.author_id,
                moderator_id=moderator_id,
                action=case_action,
                reason=case_reason,
                source="mod_queue",
                metadata={"warning_id": warning_id, "queue_id": entry_id},
            )
        updated = await self.get(entry_id)
        assert updated is not None
        return ModQueueDecisionResult(
            status="success",
            decision="denied",
            warning_id=warning_id,
            case_number=case_number,
            entry=updated,
        )
