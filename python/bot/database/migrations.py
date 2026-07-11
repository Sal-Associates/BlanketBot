"""Schema migration runner."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

from bot.database.connection import Database
from bot.errors import MigrationError

logger = logging.getLogger(__name__)

_MIGRATION_FILE_RE = re.compile(r"^(\d+)_(.+)\.sql$")


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    path: Path


def discover_migrations(migrations_dir: Path) -> list[Migration]:
    if not migrations_dir.is_dir():
        raise MigrationError(f"Migrations directory not found: {migrations_dir}")

    migrations: list[Migration] = []
    for path in sorted(migrations_dir.glob("*.sql")):
        match = _MIGRATION_FILE_RE.match(path.name)
        if not match:
            logger.warning("Skipping non-migration file: %s", path.name)
            continue
        migrations.append(Migration(version=int(match.group(1)), name=match.group(2), path=path))

    migrations.sort(key=lambda m: m.version)
    return migrations


async def ensure_migrations_table(db: Database) -> None:
    await db.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
        )
        """,
    )
    await db.commit()


async def get_applied_versions(db: Database) -> set[int]:
    await ensure_migrations_table(db)
    rows = await db.fetchall("SELECT version FROM schema_migrations ORDER BY version")
    return {int(row["version"]) for row in rows}


async def apply_migration(db: Database, migration: Migration) -> None:
    sql = migration.path.read_text(encoding="utf-8")
    logger.info("Applying migration %03d_%s", migration.version, migration.name)
    try:
        await db.executescript(sql)
        await db.execute(
            "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
            (migration.version, migration.name),
        )
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise MigrationError(
            f"Migration {migration.version} ({migration.name}) failed: {exc}",
        ) from exc


async def run_migrations(db: Database, migrations_dir: Path) -> list[int]:
    """Apply pending migrations. Returns list of newly applied version numbers."""
    await ensure_migrations_table(db)
    applied = await get_applied_versions(db)
    pending = [m for m in discover_migrations(migrations_dir) if m.version not in applied]

    if pending and applied:
        known = max(applied)
        for migration in pending:
            if migration.version <= known and migration.version not in applied:
                raise MigrationError(
                    f"Migration version gap detected: {migration.version} pending but not recorded",
                )

    newly_applied: list[int] = []
    for migration in pending:
        await apply_migration(db, migration)
        newly_applied.append(migration.version)

    if newly_applied:
        logger.info("Applied migrations: %s", newly_applied)
    else:
        logger.info("Database schema is up to date")

    return newly_applied
