"""Migration runner tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from bot.database.connection import Database
from bot.database.migrations import discover_migrations, run_migrations
from tests.conftest import INITIAL_TABLES, MIGRATIONS_DIR


@pytest.mark.asyncio
async def test_migrations_create_initial_tables(migrated_database: Database) -> None:
    for table in INITIAL_TABLES:
        assert await migrated_database.table_exists(table) is True


@pytest.mark.asyncio
async def test_migration_rerun_is_safe(database: Database) -> None:
    first = await run_migrations(database, MIGRATIONS_DIR)
    second = await run_migrations(database, MIGRATIONS_DIR)
    assert first == [1, 2]
    assert second == []


@pytest.mark.asyncio
async def test_discover_migrations_ordered() -> None:
    migrations = discover_migrations(MIGRATIONS_DIR)
    assert len(migrations) >= 1
    assert migrations[0].version == 1
    assert migrations[0].name == "initial"


@pytest.mark.asyncio
async def test_isolated_migration_database(tmp_path: Path) -> None:
    db = Database(tmp_path / "migrate.sqlite3")
    await db.connect()
    try:
        applied = await run_migrations(db, MIGRATIONS_DIR)
        assert applied == [1, 2]
        row = await db.fetchone("SELECT version, name FROM schema_migrations WHERE version = 1")
        assert row is not None
        assert row["name"] == "initial"
    finally:
        await db.close()
