"""Staff authorization checks."""

from __future__ import annotations

import discord

from bot.config import Settings
from bot.database.models import StaffRoleType
from bot.database.repositories.staff_roles import StaffRolesRepository


async def is_superuser(user_id: int | str, settings: Settings) -> bool:
    return str(user_id) in settings.superuser_ids


async def is_admin(
    member: discord.Member | None,
    *,
    settings: Settings,
    staff_roles: StaffRolesRepository,
) -> bool:
    if member is None:
        return False
    if await is_superuser(member.id, settings):
        return True
    if member.id == member.guild.owner_id:
        return True
    if member.guild_permissions.administrator:
        return True
    admin_roles = await staff_roles.list_roles(str(member.guild.id), StaffRoleType.ADMINISTRATOR)
    return any(role_id in {str(role.id) for role in member.roles} for role_id in admin_roles)


async def is_moderator(
    member: discord.Member | None,
    *,
    settings: Settings,
    staff_roles: StaffRolesRepository,
) -> bool:
    if member is None:
        return False
    if await is_admin(member, settings=settings, staff_roles=staff_roles):
        return True
    if member.guild_permissions.moderate_members or member.guild_permissions.manage_messages:
        return True
    mod_roles = await staff_roles.list_roles(str(member.guild.id), StaffRoleType.MODERATOR)
    member_role_ids = {str(role.id) for role in member.roles}
    return any(role_id in member_role_ids for role_id in mod_roles)
