"""Database transaction helpers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from bot.database.connection import Database


@asynccontextmanager
async def immediate_transaction(db: Database) -> AsyncIterator[None]:
    await db.execute("BEGIN IMMEDIATE")
    try:
        yield
        await db.commit()
    except Exception:
        await db.rollback()
        raise
