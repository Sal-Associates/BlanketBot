"""Staff role persistence."""

from __future__ import annotations

import pytest
from bot.database.models import StaffRoleType
from tests.conftest import Repositories


@pytest.mark.asyncio
async def test_add_and_list_staff_roles(repos: Repositories, guild_id: str) -> None:
    added = await repos.staff_roles.add_role(guild_id, "role-mod", StaffRoleType.MODERATOR)
    assert added is True
    mods = await repos.staff_roles.list_roles(guild_id, StaffRoleType.MODERATOR)
    assert mods == ["role-mod"]

    duplicate = await repos.staff_roles.add_role(guild_id, "role-mod", StaffRoleType.MODERATOR)
    assert duplicate is False


@pytest.mark.asyncio
async def test_remove_staff_role(repos: Repositories, guild_id: str) -> None:
    await repos.staff_roles.add_role(guild_id, "role-admin", StaffRoleType.ADMINISTRATOR)
    removed = await repos.staff_roles.remove_role(guild_id, "role-admin", StaffRoleType.ADMINISTRATOR)
    assert removed is True
    assert await repos.staff_roles.list_roles(guild_id, StaffRoleType.ADMINISTRATOR) == []

    missing = await repos.staff_roles.remove_role(guild_id, "missing", StaffRoleType.ADMINISTRATOR)
    assert missing is False
