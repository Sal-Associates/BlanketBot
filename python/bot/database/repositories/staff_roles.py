"""Staff role persistence."""

from __future__ import annotations

from bot.database.models import StaffRoleType
from bot.database.repositories.base import Repository


class StaffRolesRepository(Repository):
    async def list_roles(self, guild_id: str, role_type: StaffRoleType) -> list[str]:
        rows = await self._db.fetchall(
            "SELECT role_id FROM staff_roles WHERE guild_id = ? AND role_type = ? ORDER BY role_id",
            (guild_id, role_type.value),
        )
        return [str(row["role_id"]) for row in rows]

    async def add_role(self, guild_id: str, role_id: str, role_type: StaffRoleType) -> bool:
        cursor = await self._db.execute(
            """
            INSERT OR IGNORE INTO staff_roles (guild_id, role_id, role_type)
            VALUES (?, ?, ?)
            """,
            (guild_id, role_id, role_type.value),
        )
        await self._db.commit()
        return cursor.rowcount > 0

    async def remove_role(self, guild_id: str, role_id: str, role_type: StaffRoleType) -> bool:
        cursor = await self._db.execute(
            "DELETE FROM staff_roles WHERE guild_id = ? AND role_id = ? AND role_type = ?",
            (guild_id, role_id, role_type.value),
        )
        await self._db.commit()
        return cursor.rowcount > 0
