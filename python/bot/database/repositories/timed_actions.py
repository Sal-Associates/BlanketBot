"""Timed action persistence and scheduler claims."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from bot.database.models import TimedActionStatus
from bot.database.repositories.base import Repository
from bot.database.repositories.cases import CasesRepository
from bot.database.transaction import immediate_transaction

_PROCESSING_STATUS = "processing"


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%fZ")


@dataclass(frozen=True, slots=True)
class TimedActionRecord:
    id: int
    guild_id: str
    action: str
    user_id: str | None
    channel_id: str | None
    role_id: str | None
    permission: str | None
    previous_state: str | None
    applied_state: str | None
    ends_at: str
    status: str
    attempt_count: int
    next_retry_at: str | None
    last_error: str | None
    last_logged_error: str | None
    moderator_id: str | None
    metadata: dict[str, Any]
    created_at: str

    @classmethod
    def from_row(cls, row: Any) -> TimedActionRecord:
        metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        return cls(
            id=int(row["id"]),
            guild_id=row["guild_id"],
            action=row["action"],
            user_id=row["user_id"],
            channel_id=row["channel_id"],
            role_id=row["role_id"],
            permission=row["permission"],
            previous_state=row["previous_state"],
            applied_state=row["applied_state"],
            ends_at=row["ends_at"],
            status=row["status"],
            attempt_count=int(row["attempt_count"]),
            next_retry_at=row["next_retry_at"],
            last_error=row["last_error"],
            last_logged_error=row["last_logged_error"],
            moderator_id=row["moderator_id"],
            metadata=metadata,
            created_at=row["created_at"],
        )


class TimedActionsRepository(Repository):
    async def add(
        self,
        *,
        guild_id: str,
        action: str,
        ends_at: str,
        user_id: str | None = None,
        channel_id: str | None = None,
        role_id: str | None = None,
        permission: str | None = None,
        previous_state: str | None = None,
        applied_state: str | None = None,
        moderator_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        cursor = await self._db.execute(
            """
            INSERT INTO timed_actions (
                guild_id, action, user_id, channel_id, role_id, permission,
                previous_state, applied_state, ends_at, moderator_id, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                guild_id,
                action,
                user_id,
                channel_id,
                role_id,
                permission,
                previous_state,
                applied_state,
                ends_at,
                moderator_id,
                json.dumps(metadata or {}),
            ),
        )
        await self._db.commit()
        assert cursor.lastrowid is not None
        return int(cursor.lastrowid)

    async def get(self, action_id: int) -> TimedActionRecord | None:
        row = await self._db.fetchone("SELECT * FROM timed_actions WHERE id = ?", (action_id,))
        return TimedActionRecord.from_row(row) if row else None

    async def upsert_channel(
        self,
        *,
        guild_id: str,
        channel_id: str,
        role_id: str | None,
        action: str,
        permission: str,
        previous_state: str | None,
        applied_state: str | None,
        ends_at: str,
        moderator_id: str | None = None,
    ) -> int:
        async with immediate_transaction(self._db):
            row = await self._db.fetchone(
                """
                SELECT id FROM timed_actions
                WHERE guild_id = ? AND channel_id = ? AND action = ?
                  AND permission = ? AND status = ?
                """,
                (guild_id, channel_id, action, permission, TimedActionStatus.PENDING.value),
            )
            if row:
                action_id = int(row["id"])
                await self._db.execute(
                    """
                    UPDATE timed_actions
                    SET ends_at = ?, applied_state = ?, moderator_id = ?, role_id = ?,
                        previous_state = COALESCE(previous_state, ?),
                        attempt_count = 0, next_retry_at = NULL,
                        last_error = NULL, last_logged_error = NULL
                    WHERE id = ?
                    """,
                    (
                        ends_at,
                        applied_state,
                        moderator_id,
                        role_id,
                        previous_state,
                        action_id,
                    ),
                )
                return action_id

            cursor = await self._db.execute(
                """
                INSERT INTO timed_actions (
                    guild_id, channel_id, role_id, user_id, action, permission,
                    previous_state, applied_state, ends_at, moderator_id, status
                ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    guild_id,
                    channel_id,
                    role_id,
                    action,
                    permission,
                    previous_state,
                    applied_state,
                    ends_at,
                    moderator_id,
                    TimedActionStatus.PENDING.value,
                ),
            )
            assert cursor.lastrowid is not None
            return int(cursor.lastrowid)

    async def get_due(self, *, now: str | None = None, limit: int = 50) -> list[TimedActionRecord]:
        now_value = now or _utc_now_iso()
        rows = await self._db.fetchall(
            """
            SELECT * FROM timed_actions
            WHERE status = ?
              AND (
                (next_retry_at IS NOT NULL AND next_retry_at <= ?)
                OR (next_retry_at IS NULL AND ends_at <= ?)
              )
            ORDER BY ends_at ASC
            LIMIT ?
            """,
            (TimedActionStatus.PENDING.value, now_value, now_value, limit),
        )
        return [TimedActionRecord.from_row(row) for row in rows]

    async def claim(self, action_id: int) -> TimedActionRecord | None:
        async with immediate_transaction(self._db):
            cursor = await self._db.execute(
                """
                UPDATE timed_actions
                SET status = ?
                WHERE id = ? AND status = ?
                """,
                (_PROCESSING_STATUS, action_id, TimedActionStatus.PENDING.value),
            )
            if cursor.rowcount == 0:
                return None
            row = await self._db.fetchone("SELECT * FROM timed_actions WHERE id = ?", (action_id,))
            return TimedActionRecord.from_row(row) if row else None

    async def claim_due(self, *, now: str | None = None, limit: int = 50) -> list[TimedActionRecord]:
        due = await self.get_due(now=now, limit=limit)
        claimed: list[TimedActionRecord] = []
        for action in due:
            record = await self.claim(action.id)
            if record:
                claimed.append(record)
        return claimed

    async def complete(self, action_id: int) -> bool:
        cursor = await self._db.execute("DELETE FROM timed_actions WHERE id = ?", (action_id,))
        await self._db.commit()
        return cursor.rowcount > 0

    async def retry(
        self,
        action_id: int,
        *,
        attempt_count: int,
        last_error: str,
        next_retry_at: str,
        last_logged_error: str | None = None,
    ) -> bool:
        if last_logged_error is not None:
            cursor = await self._db.execute(
                """
                UPDATE timed_actions
                SET status = ?, attempt_count = ?, last_error = ?,
                    next_retry_at = ?, last_logged_error = ?
                WHERE id = ?
                """,
                (
                    TimedActionStatus.PENDING.value,
                    attempt_count,
                    last_error,
                    next_retry_at,
                    last_logged_error,
                    action_id,
                ),
            )
        else:
            cursor = await self._db.execute(
                """
                UPDATE timed_actions
                SET status = ?, attempt_count = ?, last_error = ?, next_retry_at = ?
                WHERE id = ?
                """,
                (
                    TimedActionStatus.PENDING.value,
                    attempt_count,
                    last_error,
                    next_retry_at,
                    action_id,
                ),
            )
        await self._db.commit()
        return cursor.rowcount > 0

    async def fail(
        self,
        action_id: int,
        *,
        last_error: str,
        attempt_count: int | None = None,
    ) -> bool:
        if attempt_count is not None:
            cursor = await self._db.execute(
                """
                UPDATE timed_actions
                SET status = ?, attempt_count = ?, last_error = ?, next_retry_at = NULL
                WHERE id = ?
                """,
                (TimedActionStatus.FAILED.value, attempt_count, last_error, action_id),
            )
        else:
            cursor = await self._db.execute(
                """
                UPDATE timed_actions
                SET status = ?, last_error = ?, next_retry_at = NULL
                WHERE id = ?
                """,
                (TimedActionStatus.FAILED.value, last_error, action_id),
            )
        await self._db.commit()
        return cursor.rowcount > 0

    async def cancel_channel(
        self,
        guild_id: str,
        channel_id: str,
        action: str,
        permission: str,
    ) -> int:
        cursor = await self._db.execute(
            """
            DELETE FROM timed_actions
            WHERE guild_id = ? AND channel_id = ? AND action = ?
              AND permission = ? AND status = ?
            """,
            (guild_id, channel_id, action, permission, TimedActionStatus.PENDING.value),
        )
        await self._db.commit()
        return cursor.rowcount

    async def list_pending_channel(
        self,
        guild_id: str,
        channel_id: str,
        action: str,
        permission: str,
    ) -> list[TimedActionRecord]:
        rows = await self._db.fetchall(
            """
            SELECT * FROM timed_actions
            WHERE guild_id = ? AND channel_id = ? AND action = ?
              AND permission = ? AND status = ?
            """,
            (guild_id, channel_id, action, permission, TimedActionStatus.PENDING.value),
        )
        return [TimedActionRecord.from_row(row) for row in rows]

    async def create_temporary_punishment_records(
        self,
        *,
        guild_id: str,
        user_id: str,
        moderator_id: str,
        case_action: str,
        case_reason: str,
        timed_action: str,
        ends_at_ms: int,
        cases: CasesRepository,
        extra: dict[str, Any] | None = None,
    ) -> tuple[int, int]:
        ends_at = datetime.fromtimestamp(ends_at_ms / 1000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%fZ")
        async with immediate_transaction(self._db):
            cursor = await self._db.execute(
                """
                INSERT INTO timed_actions (guild_id, user_id, action, ends_at, status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (guild_id, user_id, timed_action, ends_at, TimedActionStatus.PENDING.value),
            )
            timed_action_id = int(cursor.lastrowid)
            metadata = {
                "source": "moderation",
                "ends_at": ends_at_ms,
                "timed_action": timed_action,
                "timed_action_id": timed_action_id,
                **(extra or {}),
            }
            case_number = await cases._insert_case(
                guild_id=guild_id,
                user_id=user_id,
                moderator_id=moderator_id,
                action=case_action,
                reason=case_reason,
                source="moderation",
                metadata=metadata,
            )
            return case_number, timed_action_id

    async def add_lockdown_restore_action(
        self,
        *,
        guild_id: str,
        channel_id: str,
        role_id: str,
        permission: str,
        previous_state: str,
        applied_state: str,
        ends_at_ms: int | None = None,
    ) -> int:
        ends_at = (
            datetime.fromtimestamp(ends_at_ms / 1000, tz=UTC).strftime("%Y-%m-%dT%H:%M:%fZ")
            if ends_at_ms is not None
            else _utc_now_iso()
        )
        return await self.add(
            guild_id=guild_id,
            action="lockdown_channel_restore",
            ends_at=ends_at,
            channel_id=channel_id,
            role_id=role_id,
            permission=permission,
            previous_state=previous_state,
            applied_state=applied_state,
        )

    async def get_lockdown_restore_diagnostics(self, guild_id: str) -> dict[str, list[TimedActionRecord]]:
        rows = await self._db.fetchall(
            """
            SELECT * FROM timed_actions
            WHERE guild_id = ? AND action = ?
            ORDER BY id ASC
            """,
            (guild_id, "lockdown_channel_restore"),
        )
        records = [TimedActionRecord.from_row(row) for row in rows]
        pending = [record for record in records if record.status == TimedActionStatus.PENDING.value]
        failed = [record for record in records if record.status == TimedActionStatus.FAILED.value]
        return {"pending": pending, "failed": failed}
