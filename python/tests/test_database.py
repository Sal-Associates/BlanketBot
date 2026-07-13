"""Database connection and pragma tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from bot.database.connection import Database


@pytest.mark.asyncio
async def test_foreign_keys_enabled(database: Database) -> None:
    assert await database.get_foreign_keys_enabled() is True


@pytest.mark.asyncio
async def test_wal_journal_mode(database: Database) -> None:
    mode = await database.get_journal_mode()
    assert mode.lower() == "wal"


@pytest.mark.asyncio
async def test_isolated_temporary_database(tmp_path: Path) -> None:
    path_a = tmp_path / "a.sqlite3"
    path_b = tmp_path / "b.sqlite3"

    db_a = Database(path_a)
    db_b = Database(path_b)
    await db_a.connect()
    await db_b.connect()
    try:
        await db_a.execute("CREATE TABLE probe (id INTEGER PRIMARY KEY)")
        await db_a.commit()
        assert await db_b.table_exists("probe") is False
    finally:
        await db_a.close()
        await db_b.close()


@pytest.mark.asyncio
async def test_close_clears_connection(database: Database) -> None:
    assert database._connection is not None
    await database.close()
    assert database._connection is None
