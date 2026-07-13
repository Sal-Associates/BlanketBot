"""Strike escalation state per user."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bot.database.repositories.base import Repository
from bot.database.transaction import immediate_transaction


@dataclass(frozen=True, slots=True)
class StrikeStateRecord:
    guild_id: str
    user_id: str
    last_mute_at_count: int
    last_ban_at_count: int

    @classmethod
    def from_row(cls, row: Any) -> StrikeStateRecord:
        return cls(
            guild_id=row["guild_id"],
            user_id=row["user_id"],
            last_mute_at_count=int(row["last_mute_at_count"]),
            last_ban_at_count=int(row["last_ban_at_count"]),
        )


class StrikeStateRepository(Repository):
    async def get(self, guild_id: str, user_id: str) -> StrikeStateRecord | None:
        row = await self._db.fetchone(
            """
            SELECT * FROM strike_escalation_state
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id),
        )
        return StrikeStateRecord.from_row(row) if row else None

    async def get_or_create(self, guild_id: str, user_id: str) -> StrikeStateRecord:
        existing = await self.get(guild_id, user_id)
        if existing:
            return existing

        await self._db.execute(
            """
            INSERT INTO strike_escalation_state (guild_id, user_id)
            VALUES (?, ?)
            ON CONFLICT(guild_id, user_id) DO NOTHING
            """,
            (guild_id, user_id),
        )
        await self._db.commit()
        row = await self._db.fetchone(
            """
            SELECT * FROM strike_escalation_state
            WHERE guild_id = ? AND user_id = ?
            """,
            (guild_id, user_id),
        )
        assert row is not None
        return StrikeStateRecord.from_row(row)

    async def set_last_mute_at_count(
        self,
        guild_id: str,
        user_id: str,
        count: int,
    ) -> StrikeStateRecord:
        async with immediate_transaction(self._db):
            await self._db.execute(
                """
                INSERT INTO strike_escalation_state (guild_id, user_id, last_mute_at_count)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    last_mute_at_count = excluded.last_mute_at_count
                """,
                (guild_id, user_id, count),
            )
            row = await self._db.fetchone(
                """
                SELECT * FROM strike_escalation_state
                WHERE guild_id = ? AND user_id = ?
                """,
                (guild_id, user_id),
            )
            assert row is not None
            return StrikeStateRecord.from_row(row)

    async def set_last_ban_at_count(
        self,
        guild_id: str,
        user_id: str,
        count: int,
    ) -> StrikeStateRecord:
        async with immediate_transaction(self._db):
            await self._db.execute(
                """
                INSERT INTO strike_escalation_state (guild_id, user_id, last_ban_at_count)
                VALUES (?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    last_ban_at_count = excluded.last_ban_at_count
                """,
                (guild_id, user_id, count),
            )
            row = await self._db.fetchone(
                """
                SELECT * FROM strike_escalation_state
                WHERE guild_id = ? AND user_id = ?
                """,
                (guild_id, user_id),
            )
            assert row is not None
            return StrikeStateRecord.from_row(row)

    async def upsert(
        self,
        guild_id: str,
        user_id: str,
        *,
        last_mute_at_count: int | None = None,
        last_ban_at_count: int | None = None,
    ) -> StrikeStateRecord:
        current = await self.get_or_create(guild_id, user_id)
        mute_count = last_mute_at_count if last_mute_at_count is not None else current.last_mute_at_count
        ban_count = last_ban_at_count if last_ban_at_count is not None else current.last_ban_at_count

        async with immediate_transaction(self._db):
            await self._db.execute(
                """
                INSERT INTO strike_escalation_state (
                    guild_id, user_id, last_mute_at_count, last_ban_at_count
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    last_mute_at_count = excluded.last_mute_at_count,
                    last_ban_at_count = excluded.last_ban_at_count
                """,
                (guild_id, user_id, mute_count, ban_count),
            )
            row = await self._db.fetchone(
                """
                SELECT * FROM strike_escalation_state
                WHERE guild_id = ? AND user_id = ?
                """,
                (guild_id, user_id),
            )
            assert row is not None
            return StrikeStateRecord.from_row(row)
