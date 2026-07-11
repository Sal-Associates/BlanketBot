"""Moderation hierarchy validation."""

from __future__ import annotations

from typing import Any, Protocol

import discord

from bot.result_types import HierarchyResult

__all__ = [
    "HierarchyResult",
    "MODERATION_DENIAL",
    "check_bot_can_act_on",
    "check_moderation_target",
    "get_moderation_denied",
]

MODERATION_DENIAL = {
    "SELF": "You cannot moderate yourself.",
    "TARGET_IS_OWNER": "You cannot moderate the server owner.",
    "TARGET_ABOVE_ISSUER": "Your highest role must be above the target's highest role.",
    "BOT_CANNOT_ACT": "My highest role must be above the target's highest role.",
    "NOT_A_MEMBER": "That user is not currently a member of this server.",
}


class _HasId(Protocol):
    id: int


def _get_target_id(target: _HasId | Any) -> int | None:
    target_id = getattr(target, "id", None)
    if target_id is None:
        user = getattr(target, "user", None)
        target_id = getattr(user, "id", None) if user else None
    if target_id is None:
        return None
    if isinstance(target_id, int):
        return target_id
    text = str(target_id)
    return int(text) if text.isdigit() else None


def _is_guild_member(target: Any) -> bool:
    roles = getattr(target, "roles", None)
    if roles is None:
        return False
    highest = getattr(roles, "highest", None)
    return highest is not None


def check_bot_can_act_on(guild: discord.Guild, target: Any) -> HierarchyResult:
    if not _is_guild_member(target):
        return HierarchyResult(allowed=False, reason=MODERATION_DENIAL["NOT_A_MEMBER"])

    target_id = _get_target_id(target)
    if target_id == guild.owner_id:
        return HierarchyResult(allowed=False, reason=MODERATION_DENIAL["TARGET_IS_OWNER"])

    bot = guild.me
    if bot is None or bot.top_role.position <= target.top_role.position:
        return HierarchyResult(allowed=False, reason=MODERATION_DENIAL["BOT_CANNOT_ACT"])

    return HierarchyResult(allowed=True)


def check_moderation_target(
    guild: discord.Guild,
    issuer: discord.Member | None,
    target: Any,
    *,
    require_member: bool = True,
) -> HierarchyResult:
    target_id = _get_target_id(target)
    if issuer is None or target_id is None:
        return HierarchyResult(allowed=False, reason=MODERATION_DENIAL["NOT_A_MEMBER"])

    member_target = _is_guild_member(target)

    if require_member and not member_target:
        return HierarchyResult(allowed=False, reason=MODERATION_DENIAL["NOT_A_MEMBER"])

    if issuer.id == target_id:
        return HierarchyResult(allowed=False, reason=MODERATION_DENIAL["SELF"])

    if target_id == guild.owner_id:
        return HierarchyResult(allowed=False, reason=MODERATION_DENIAL["TARGET_IS_OWNER"])

    if member_target:
        bot_check = check_bot_can_act_on(guild, target)
        if not bot_check.allowed:
            return bot_check

        if issuer.id != guild.owner_id and issuer.top_role.position <= target.top_role.position:
            return HierarchyResult(allowed=False, reason=MODERATION_DENIAL["TARGET_ABOVE_ISSUER"])

    return HierarchyResult(allowed=True)


def get_moderation_denied(
    guild: discord.Guild,
    issuer: discord.Member | None,
    target: Any,
    *,
    require_member: bool = True,
) -> str | None:
    result = check_moderation_target(guild, issuer, target, require_member=require_member)
    if result.allowed:
        return None
    return result.reason
