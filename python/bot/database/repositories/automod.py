"""Automod ignore lists and link filters."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from bot.database.repositories.base import Repository
from bot.errors import DatabaseError


class AutomodLinkListType(StrEnum):
    BLACKLIST = "blacklist"
    WHITELIST = "whitelist"


@dataclass(frozen=True, slots=True)
class AutomodLinkRecord:
    id: int
    guild_id: str
    link: str
    list_type: AutomodLinkListType

    @classmethod
    def from_row(cls, row: Any) -> AutomodLinkRecord:
        return cls(
            id=int(row["id"]),
            guild_id=row["guild_id"],
            link=row["link"],
            list_type=AutomodLinkListType(row["list_type"]),
        )


class AutomodRepository(Repository):
    async def add_ignored_channel(self, guild_id: str, channel_id: str) -> bool:
        existing = await self._db.fetchone(
            """
            SELECT id FROM automod_ignored_channels
            WHERE guild_id = ? AND channel_id = ?
            """,
            (guild_id, channel_id),
        )
        if existing:
            raise DatabaseError("duplicate_ignored_channel")

        cursor = await self._db.execute(
            "INSERT INTO automod_ignored_channels (guild_id, channel_id) VALUES (?, ?)",
            (guild_id, channel_id),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def remove_ignored_channel(self, guild_id: str, channel_id: str) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM automod_ignored_channels WHERE guild_id = ? AND channel_id = ?",
            (guild_id, channel_id),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def list_ignored_channels(self, guild_id: str) -> list[str]:
        rows = await self._db.fetchall(
            """
            SELECT channel_id FROM automod_ignored_channels
            WHERE guild_id = ?
            ORDER BY channel_id
            """,
            (guild_id,),
        )
        return [str(row["channel_id"]) for row in rows]

    async def add_ignored_role(self, guild_id: str, role_id: str) -> bool:
        existing = await self._db.fetchone(
            """
            SELECT id FROM automod_ignored_roles
            WHERE guild_id = ? AND role_id = ?
            """,
            (guild_id, role_id),
        )
        if existing:
            raise DatabaseError("duplicate_ignored_role")

        cursor = await self._db.execute(
            "INSERT INTO automod_ignored_roles (guild_id, role_id) VALUES (?, ?)",
            (guild_id, role_id),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def remove_ignored_role(self, guild_id: str, role_id: str) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM automod_ignored_roles WHERE guild_id = ? AND role_id = ?",
            (guild_id, role_id),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def list_ignored_roles(self, guild_id: str) -> list[str]:
        rows = await self._db.fetchall(
            """
            SELECT role_id FROM automod_ignored_roles
            WHERE guild_id = ?
            ORDER BY role_id
            """,
            (guild_id,),
        )
        return [str(row["role_id"]) for row in rows]

    async def add_link(
        self,
        guild_id: str,
        link: str,
        list_type: AutomodLinkListType | str,
    ) -> bool:
        normalized_link = (link or "").strip().lower()
        if not normalized_link:
            raise DatabaseError("Link value cannot be empty")

        mode = list_type if isinstance(list_type, AutomodLinkListType) else AutomodLinkListType(str(list_type).lower())
        cursor = await self._db.execute(
            """
            INSERT OR IGNORE INTO automod_links (guild_id, link, list_type)
            VALUES (?, ?, ?)
            """,
            (guild_id, normalized_link, mode.value),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def remove_link(
        self,
        guild_id: str,
        link: str,
        list_type: AutomodLinkListType | str,
    ) -> bool:
        mode = list_type if isinstance(list_type, AutomodLinkListType) else AutomodLinkListType(str(list_type).lower())
        normalized_link = (link or "").strip().lower()
        cursor = await self._db.execute(
            """
            DELETE FROM automod_links
            WHERE guild_id = ? AND link = ? AND list_type = ?
            """,
            (guild_id, normalized_link, mode.value),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def list_links(
        self,
        guild_id: str,
        list_type: AutomodLinkListType | str,
    ) -> list[str]:
        mode = list_type if isinstance(list_type, AutomodLinkListType) else AutomodLinkListType(str(list_type).lower())
        rows = await self._db.fetchall(
            """
            SELECT link FROM automod_links
            WHERE guild_id = ? AND list_type = ?
            ORDER BY link
            """,
            (guild_id, mode.value),
        )
        return [str(row["link"]) for row in rows]
