"""Base repository with shared database access."""

from __future__ import annotations

from bot.database.connection import Database


class Repository:
    """Thin data-access base class for SQLite repositories."""

    def __init__(self, db: Database) -> None:
        self._db = db
