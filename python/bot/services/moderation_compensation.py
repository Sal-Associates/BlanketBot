"""Rollback helpers when moderation persistence fails."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import discord

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RollbackResult:
    success: bool
    error: str | None = None


async def rollback_temporary_mute(
    target: discord.Member,
    mute_role: discord.Role,
) -> RollbackResult:
    try:
        await target.remove_roles(
            mute_role,
            reason="Rollback: moderation record could not be saved",
        )
        return RollbackResult(success=True)
    except discord.HTTPException as exc:
        logger.error("[moderation] Mute rollback failed: %s", exc)
        return RollbackResult(success=False, error=str(exc))


async def rollback_temporary_ban(guild: discord.Guild, user_id: int | str) -> RollbackResult:
    try:
        user_int = int(user_id) if isinstance(user_id, int) or str(user_id).isdigit() else None
        if user_int is None:
            return RollbackResult(success=False, error="invalid_user_id")
        await guild.unban(
            discord.Object(id=user_int),
            reason="Rollback: moderation record could not be saved",
        )
        return RollbackResult(success=True)
    except discord.HTTPException as exc:
        logger.error("[moderation] Ban rollback failed: %s", exc)
        return RollbackResult(success=False, error=str(exc))


def persistence_rollback_message(action_label: str, rollback: RollbackResult) -> str:
    if rollback.success:
        return f"The {action_label} was applied but could not be safely scheduled. The {action_label} was reversed."
    return (
        f"The {action_label} was applied but recordkeeping failed. Rollback also failed—manual intervention required."
    )


def persistence_logging_failure_message(action_label: str) -> str:
    return f"The user was {action_label}, but the moderation record could not be saved."
