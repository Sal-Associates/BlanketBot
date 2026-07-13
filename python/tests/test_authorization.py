"""Authorization checks (ported from verify-moderation.mjs hierarchy-adjacent tests)."""

from __future__ import annotations

import pytest
from bot.config import Settings
from bot.database.models import StaffRoleType
from bot.services.authorization import is_admin, is_moderator, is_superuser
from tests.conftest import Repositories, make_guild, make_member


@pytest.mark.asyncio
async def test_is_superuser(settings: Settings) -> None:
    assert await is_superuser("super", settings) is True
    assert await is_superuser("other", settings) is False


@pytest.mark.asyncio
async def test_is_admin_includes_owner_and_superuser(settings: Settings, repos: Repositories) -> None:
    guild = make_guild()
    owner = make_member("owner", 0, guild=guild)
    superuser = make_member("super", 3, guild=guild)
    assert await is_admin(owner, settings=settings, staff_roles=repos.staff_roles) is True
    assert await is_admin(superuser, settings=settings, staff_roles=repos.staff_roles) is True


@pytest.mark.asyncio
async def test_is_moderator_via_configured_role(settings: Settings, repos: Repositories, guild_id: str) -> None:
    guild = make_guild()
    member = make_member("mod", 5, guild=guild)
    member.guild_permissions = type(
        "Perms",
        (),
        {"moderate_members": False, "manage_messages": False, "administrator": False},
    )()
    member.roles = []
    assert await is_moderator(member, settings=settings, staff_roles=repos.staff_roles) is False

    role_id = "987654321098765432"
    await repos.staff_roles.add_role(guild_id, role_id, StaffRoleType.MODERATOR)
    member.roles = [type("Role", (), {"id": int(role_id)})()]
    assert await is_moderator(member, settings=settings, staff_roles=repos.staff_roles) is True
