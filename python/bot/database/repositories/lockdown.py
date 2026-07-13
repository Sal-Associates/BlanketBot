"""Server lockdown persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from bot.database.repositories.base import Repository
from bot.database.transaction import immediate_transaction
from bot.errors import DatabaseError


@dataclass(frozen=True, slots=True)
class LockdownOperationRecord:
    id: int
    guild_id: str
    active: bool
    disabling: bool
    started_at: str | None
    started_by: str | None
    reason: str | None
    disabled_at: str | None
    disabled_by: str | None
    disable_reason: str | None
    role_id: str | None
    permission: str
    metadata: dict[str, Any]
    created_at: str

    @classmethod
    def from_row(cls, row: Any) -> LockdownOperationRecord:
        metadata = json.loads(row["metadata_json"]) if row["metadata_json"] else {}
        return cls(
            id=int(row["id"]),
            guild_id=row["guild_id"],
            active=bool(row["active"]),
            disabling=bool(row["disabling"]),
            started_at=row["started_at"],
            started_by=row["started_by"],
            reason=row["reason"],
            disabled_at=row["disabled_at"],
            disabled_by=row["disabled_by"],
            disable_reason=row["disable_reason"],
            role_id=row["role_id"],
            permission=row["permission"] or "SendMessages",
            metadata=metadata,
            created_at=row["created_at"],
        )


@dataclass(frozen=True, slots=True)
class LockdownSnapshotRecord:
    id: int
    operation_id: int
    channel_id: str
    previous_state: str | None
    applied_state: str | None
    result: str | None
    disable_result: str | None
    error: str | None

    @classmethod
    def from_row(cls, row: Any) -> LockdownSnapshotRecord:
        return cls(
            id=int(row["id"]),
            operation_id=int(row["operation_id"]),
            channel_id=row["channel_id"],
            previous_state=row["previous_state"],
            applied_state=row["applied_state"],
            result=row["result"],
            disable_result=row["disable_result"],
            error=row["error"],
        )


@dataclass(frozen=True, slots=True)
class LockdownState:
    operation: LockdownOperationRecord | None
    channels: tuple[LockdownSnapshotRecord, ...]

    @property
    def active(self) -> bool:
        return bool(self.operation and self.operation.active)


@dataclass(frozen=True, slots=True)
class LockdownAcquireResult:
    ok: bool
    reason: Literal["already_active", "not_active"] | None = None
    operation: LockdownOperationRecord | None = None


class LockdownRepository(Repository):
    async def add_channel(self, guild_id: str, channel_id: str) -> list[str]:
        existing = await self._db.fetchone(
            """
            SELECT 1 FROM lockdown_channels
            WHERE guild_id = ? AND channel_id = ?
            """,
            (guild_id, channel_id),
        )
        if existing:
            raise DatabaseError("duplicate_lockdown_channel")

        await self._db.execute(
            "INSERT INTO lockdown_channels (guild_id, channel_id) VALUES (?, ?)",
            (guild_id, channel_id),
        )
        await self._db.commit()
        return await self.list_channels(guild_id)

    async def remove_channel(self, guild_id: str, channel_id: str) -> int:
        cursor = await self._db.execute(
            "DELETE FROM lockdown_channels WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id),
        )
        await self._db.commit()
        return cursor.rowcount

    async def list_channels(self, guild_id: str) -> list[str]:
        rows = await self._db.fetchall(
            """
            SELECT channel_id FROM lockdown_channels
            WHERE guild_id = ?
            ORDER BY channel_id
            """,
            (guild_id,),
        )
        return [str(row["channel_id"]) for row in rows]

    async def get_active_operation(self, guild_id: str) -> LockdownOperationRecord | None:
        row = await self._db.fetchone(
            """
            SELECT * FROM lockdown_operations
            WHERE guild_id = ? AND active = 1
            ORDER BY id DESC
            LIMIT 1
            """,
            (guild_id,),
        )
        return LockdownOperationRecord.from_row(row) if row else None

    async def get_snapshots(self, operation_id: int) -> list[LockdownSnapshotRecord]:
        rows = await self._db.fetchall(
            """
            SELECT * FROM lockdown_channel_snapshots
            WHERE operation_id = ?
            ORDER BY id ASC
            """,
            (operation_id,),
        )
        return [LockdownSnapshotRecord.from_row(row) for row in rows]

    async def get_state(self, guild_id: str) -> LockdownState:
        operation = await self.get_active_operation(guild_id)
        if not operation:
            latest = await self._db.fetchone(
                """
                SELECT * FROM lockdown_operations
                WHERE guild_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (guild_id,),
            )
            operation = LockdownOperationRecord.from_row(latest) if latest else None

        if not operation:
            return LockdownState(operation=None, channels=())

        snapshots = await self.get_snapshots(operation.id)
        return LockdownState(operation=operation, channels=tuple(snapshots))

    async def acquire_enable(
        self,
        guild_id: str,
        *,
        moderator_id: str,
        reason: str,
        role_id: str,
        permission: str = "SendMessages",
        metadata: dict[str, Any] | None = None,
    ) -> LockdownAcquireResult:
        async with immediate_transaction(self._db):
            existing = await self.get_active_operation(guild_id)
            if existing:
                return LockdownAcquireResult(
                    ok=False,
                    reason="already_active",
                    operation=existing,
                )

            cursor = await self._db.execute(
                """
                INSERT INTO lockdown_operations (
                    guild_id, active, disabling, started_at, started_by, reason,
                    role_id, permission, metadata_json
                ) VALUES (
                    ?, 1, 0,
                    strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                    ?, ?, ?, ?, ?
                )
                """,
                (
                    guild_id,
                    moderator_id,
                    reason,
                    role_id,
                    permission,
                    json.dumps(metadata or {}),
                ),
            )
            assert cursor.lastrowid is not None
            row = await self._db.fetchone(
                "SELECT * FROM lockdown_operations WHERE id = ?",
                (int(cursor.lastrowid),),
            )
            assert row is not None
            return LockdownAcquireResult(
                ok=True,
                operation=LockdownOperationRecord.from_row(row),
            )

    async def acquire_disable(self, guild_id: str) -> LockdownAcquireResult:
        async with immediate_transaction(self._db):
            operation = await self.get_active_operation(guild_id)
            if not operation:
                return LockdownAcquireResult(ok=False, reason="not_active")

            await self._db.execute(
                "UPDATE lockdown_operations SET disabling = 1 WHERE id = ?",
                (operation.id,),
            )
            row = await self._db.fetchone(
                "SELECT * FROM lockdown_operations WHERE id = ?",
                (operation.id,),
            )
            assert row is not None
            return LockdownAcquireResult(
                ok=True,
                operation=LockdownOperationRecord.from_row(row),
            )

    async def _replace_enable_snapshots(
        self,
        operation_id: int,
        channel_results: list[dict[str, Any]],
    ) -> list[LockdownSnapshotRecord]:
        await self._db.execute(
            "DELETE FROM lockdown_channel_snapshots WHERE operation_id = ?",
            (operation_id,),
        )
        for entry in channel_results:
            await self._db.execute(
                """
                INSERT INTO lockdown_channel_snapshots (
                    operation_id, channel_id, previous_state, applied_state, result, error
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    operation_id,
                    entry["channel_id"],
                    entry.get("previous_state"),
                    entry.get("applied_state"),
                    entry.get("result"),
                    entry.get("error"),
                ),
            )
        return await self.get_snapshots(operation_id)

    async def replace_enable_snapshots(
        self,
        operation_id: int,
        channel_results: list[dict[str, Any]],
    ) -> list[LockdownSnapshotRecord]:
        async with immediate_transaction(self._db):
            return await self._replace_enable_snapshots(operation_id, channel_results)

    async def finalize_enable(
        self,
        guild_id: str,
        channel_results: list[dict[str, Any]],
    ) -> LockdownState:
        async with immediate_transaction(self._db):
            operation = await self.get_active_operation(guild_id)
            if not operation:
                raise DatabaseError("no_active_lockdown")

            snapshots = await self._replace_enable_snapshots(operation.id, channel_results)
            row = await self._db.fetchone(
                "SELECT * FROM lockdown_operations WHERE id = ?",
                (operation.id,),
            )
            assert row is not None
            return LockdownState(
                operation=LockdownOperationRecord.from_row(row),
                channels=tuple(snapshots),
            )

    async def finalize_disable(
        self,
        guild_id: str,
        *,
        moderator_id: str,
        reason: str,
        channel_results: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LockdownState:
        async with immediate_transaction(self._db):
            operation = await self.get_active_operation(guild_id)
            if not operation:
                row = await self._db.fetchone(
                    """
                    SELECT * FROM lockdown_operations
                    WHERE guild_id = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (guild_id,),
                )
                operation = LockdownOperationRecord.from_row(row) if row else None

            if not operation:
                raise DatabaseError("no_active_lockdown")

            if channel_results is not None:
                for entry in channel_results:
                    await self._db.execute(
                        """
                        UPDATE lockdown_channel_snapshots
                        SET disable_result = ?, error = COALESCE(?, error)
                        WHERE operation_id = ? AND channel_id = ?
                        """,
                        (
                            entry.get("disable_result") or entry.get("result"),
                            entry.get("error"),
                            operation.id,
                            entry["channel_id"],
                        ),
                    )

            merged_metadata = {**operation.metadata, **(metadata or {})}
            await self._db.execute(
                """
                UPDATE lockdown_operations
                SET active = 0, disabling = 0,
                    disabled_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now'),
                    disabled_by = ?, disable_reason = ?, metadata_json = ?
                WHERE id = ?
                """,
                (moderator_id, reason, json.dumps(merged_metadata), operation.id),
            )

            row = await self._db.fetchone(
                "SELECT * FROM lockdown_operations WHERE id = ?",
                (operation.id,),
            )
            assert row is not None
            snapshots = await self.get_snapshots(operation.id)
            return LockdownState(
                operation=LockdownOperationRecord.from_row(row),
                channels=tuple(snapshots),
            )

    async def clear_active(self, guild_id: str) -> bool:
        cursor = await self._db.execute(
            """
            UPDATE lockdown_operations
            SET active = 0, disabling = 0
            WHERE guild_id = ? AND active = 1
            """,
            (guild_id,),
        )
        await self._db.commit()
        return cursor.rowcount > 0
