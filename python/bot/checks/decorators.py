"""discord.py command check decorators."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Any

import discord
from discord.ext import commands

from bot.database.repositories.staff_roles import StaffRolesRepository
from bot.services.authorization import is_admin, is_moderator

MODERATOR_DENIED = "You need moderator permissions to use this command."
ADMINISTRATOR_DENIED = "You need admin permissions to use this command."


def _staff_roles_repo(bot: commands.Bot | discord.Client) -> StaffRolesRepository:
    database = getattr(bot, "database", None)
    if database is None:
        raise RuntimeError("Bot database is not configured")
    return StaffRolesRepository(database)


def moderator_required() -> Callable[[Callable[..., Coroutine[Any, Any, Any]]], commands.check]:
    async def predicate(ctx: commands.Context) -> bool:
        if not isinstance(ctx.author, discord.Member):
            raise commands.CheckFailure(MODERATOR_DENIED)
        repo = _staff_roles_repo(ctx.bot)
        settings = ctx.bot.settings  # type: ignore[attr-defined]
        if not await is_moderator(ctx.author, settings=settings, staff_roles=repo):
            raise commands.CheckFailure(MODERATOR_DENIED)
        return True

    return commands.check(predicate)


def administrator_required() -> Callable[[Callable[..., Coroutine[Any, Any, Any]]], commands.check]:
    async def predicate(ctx: commands.Context) -> bool:
        if not isinstance(ctx.author, discord.Member):
            raise commands.CheckFailure(ADMINISTRATOR_DENIED)
        repo = _staff_roles_repo(ctx.bot)
        settings = ctx.bot.settings  # type: ignore[attr-defined]
        if not await is_admin(ctx.author, settings=settings, staff_roles=repo):
            raise commands.CheckFailure(ADMINISTRATOR_DENIED)
        return True

    return commands.check(predicate)
