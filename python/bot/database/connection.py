"""SQLite connection and lifecycle management."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import aiosqlite

from bot.errors import DatabaseError

logger = logging.getLogger(__name__)


class Database:
    """Async SQLite wrapper with explicit connection lifecycle."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._connection: aiosqlite.Connection | None = None

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise DatabaseError("Database is not connected")
        return self._connection

    async def connect(self) -> None:
        if self._connection is not None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self.path)
        self._connection.row_factory = aiosqlite.Row
        await self._configure_pragmas()

    async def _configure_pragmas(self) -> None:
        conn = self.connection
        await conn.execute("PRAGMA foreign_keys = ON")
        cursor = await conn.execute("PRAGMA journal_mode = WAL")
        row = await cursor.fetchone()
        await cursor.close()
        if row:
            logger.debug("SQLite journal_mode=%s", row[0])

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def execute(self, sql: str, parameters: tuple[Any, ...] | list[Any] = ()) -> aiosqlite.Cursor:
        return await self.connection.execute(sql, parameters)

    async def executemany(
        self,
        sql: str,
        parameters: list[tuple[Any, ...]],
    ) -> aiosqlite.Cursor:
        return await self.connection.executemany(sql, parameters)

    async def executescript(self, script: str) -> None:
        await self.connection.executescript(script)

    async def commit(self) -> None:
        await self.connection.commit()

    async def rollback(self) -> None:
        await self.connection.rollback()

    async def fetchone(self, sql: str, parameters: tuple[Any, ...] = ()) -> aiosqlite.Row | None:
        cursor = await self.execute(sql, parameters)
        row = await cursor.fetchone()
        await cursor.close()
        return row

    async def fetchall(self, sql: str, parameters: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
        cursor = await self.execute(sql, parameters)
        rows = await cursor.fetchall()
        await cursor.close()
        return list(rows)

    async def get_foreign_keys_enabled(self) -> bool:
        row = await self.fetchone("PRAGMA foreign_keys")
        return bool(row and row[0])

    async def get_journal_mode(self) -> str:
        row = await self.fetchone("PRAGMA journal_mode")
        return str(row[0]) if row else ""

    async def table_exists(self, name: str) -> bool:
        row = await self.fetchone(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (name,),
        )
        return row is not None
