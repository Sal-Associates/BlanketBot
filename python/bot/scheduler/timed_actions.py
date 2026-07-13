"""Execute due timed moderation actions."""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import discord
from discord.ext import commands

from bot.database.connection import Database
from bot.database.repositories.guild_settings import GuildSettingsRepository
from bot.database.repositories.timed_actions import TimedActionRecord, TimedActionsRepository
from bot.services.guild_guard import is_configured_guild
from bot.services.hierarchy import check_bot_can_act_on
from bot.services.mod_log import get_or_create_mute_role, send_mod_log
from bot.utils.channel_permissions import (
    PermissionState,
    channel_permission_matches,
    get_permission_state,
    restore_channel_from_timed_action,
)
from bot.utils.timed_action_retry import (
    MAX_CHANNEL_UNLOCK_ATTEMPTS,
    get_retry_delay_ms,
    sanitize_timed_action_error,
)

logger = logging.getLogger(__name__)

TimedActionOutcome = Literal["completed", "terminal", "retryable", "failed_max"]


def _utc_now_iso_from_ms(delay_ms: int) -> str:
    when = datetime.now(UTC) + timedelta(milliseconds=delay_ms)
    return when.strftime("%Y-%m-%dT%H:%M:%fZ")


async def execute_timed_action(
    bot: commands.Bot,
    action: TimedActionRecord,
    *,
    database: Database,
    configured_guild_id: str,
) -> dict[str, Any]:
    if not is_configured_guild(action.guild_id, configured_guild_id):
        return {"outcome": "terminal", "reason": "guild_not_configured"}

    if action.action == "unban":
        return await _execute_unban(bot, action)
    if action.action == "unmute":
        return await _execute_unmute(bot, action, database=database)
    if action.action == "channel_unlock":
        return await _execute_channel_unlock(bot, action, database=database)
    if action.action == "lockdown_channel_restore":
        return await _execute_channel_unlock(
            bot,
            replace(
                action,
                action="channel_unlock",
                applied_state=action.applied_state or "deny",
            ),
            database=database,
        )

    logger.warning("[scheduler] Unknown timed action type: %s", action.action)
    return {"outcome": "terminal", "reason": "unknown_action"}


async def _execute_unban(bot: commands.Bot, action: TimedActionRecord) -> dict[str, Any]:
    guild = bot.get_guild(int(action.guild_id))
    if guild is None:
        try:
            guild = await bot.fetch_guild(int(action.guild_id))
        except discord.HTTPException:
            guild = None
    if guild is None:
        logger.warning("[scheduler] Timed unban skipped — guild missing (%s)", action.guild_id)
        return {"outcome": "terminal", "reason": "guild_missing"}

    try:
        await guild.unban(
            discord.Object(id=int(action.user_id)),  # type: ignore[arg-type]
            reason="Timed ban expired",
        )
        return {"outcome": "completed"}
    except discord.HTTPException as exc:
        logger.error("[scheduler] Timed unban failed for user %s: %s", action.user_id, exc)
        return {"outcome": "retryable", "reason": "api_error", "error": exc}


async def _execute_unmute(
    bot: commands.Bot,
    action: TimedActionRecord,
    *,
    database: Database,
) -> dict[str, Any]:
    guild = bot.get_guild(int(action.guild_id))
    if guild is None:
        try:
            guild = await bot.fetch_guild(int(action.guild_id))
        except discord.HTTPException:
            guild = None
    if guild is None:
        logger.warning("[scheduler] Timed unmute skipped — guild missing (%s)", action.guild_id)
        return {"outcome": "terminal", "reason": "guild_missing"}

    member = guild.get_member(int(action.user_id))  # type: ignore[arg-type]
    if member is None:
        try:
            member = await guild.fetch_member(int(action.user_id))  # type: ignore[arg-type]
        except discord.HTTPException:
            member = None
    if member is None:
        logger.warning("[scheduler] Timed unmute skipped — member missing (%s)", action.user_id)
        return {"outcome": "terminal", "reason": "member_missing"}

    bot_check = check_bot_can_act_on(guild, member)
    if not bot_check.allowed:
        logger.warning("[scheduler] Timed unmute skipped — bot cannot act on %s", action.user_id)
        return {"outcome": "retryable", "reason": "bot_cannot_act"}

    guild_settings = GuildSettingsRepository(database)
    try:
        mute_role = await get_or_create_mute_role(guild, guild_settings=guild_settings)
        await member.remove_roles(mute_role)
        return {"outcome": "completed"}
    except discord.HTTPException as exc:
        logger.error("[scheduler] Timed unmute failed for user %s: %s", action.user_id, exc)
        return {"outcome": "retryable", "reason": "api_error", "error": exc}


def _validate_channel_unlock_action(action: TimedActionRecord) -> bool:
    if not action.channel_id or not action.permission:
        return False
    previous_state = action.previous_state or "unset"
    return previous_state in {"allow", "deny", "unset"}


async def _execute_channel_unlock(
    bot: commands.Bot,
    action: TimedActionRecord,
    *,
    database: Database,
) -> dict[str, Any]:
    if not _validate_channel_unlock_action(action):
        logger.error("[scheduler] Malformed channel_unlock action %s", action.id)
        return {"outcome": "terminal", "reason": "malformed"}

    permission = action.permission or "SendMessages"
    guild = bot.get_guild(int(action.guild_id))
    if guild is None:
        try:
            guild = await bot.fetch_guild(int(action.guild_id))
        except discord.HTTPException as exc:
            logger.warning("[scheduler] Channel unlock retry — guild fetch failed (%s)", action.guild_id)
            return {"outcome": "retryable", "reason": "fetch_failed", "error": exc}

    channel = guild.get_channel(int(action.channel_id))  # type: ignore[arg-type]
    if channel is None:
        try:
            channel = await guild.fetch_channel(int(action.channel_id))  # type: ignore[arg-type]
        except discord.HTTPException as exc:
            logger.warning(
                "[scheduler] Channel unlock retry — channel fetch failed (%s)",
                action.channel_id,
            )
            return {"outcome": "retryable", "reason": "fetch_failed", "error": exc}

    if not hasattr(channel, "overwrites_for"):
        logger.warning("[scheduler] Channel unlock removed — channel missing (%s)", action.channel_id)
        await _log_channel_timed_action(
            guild,
            action,
            log_action="channel_unlock_skipped",
            reason="Channel no longer exists; timed unlock removed.",
            database=database,
        )
        return {"outcome": "terminal", "reason": "channel_missing"}

    role_id = int(action.role_id) if action.role_id else guild.id
    if role_id == guild.id:
        role: discord.Role | discord.Object = guild.default_role
    else:
        resolved_role = guild.get_role(role_id)
        if resolved_role is None:
            try:
                roles = await guild.fetch_roles()
                resolved_role = discord.utils.get(roles, id=role_id)
            except discord.HTTPException:
                resolved_role = None
        if resolved_role is None:
            logger.warning("[scheduler] Channel unlock removed — role missing (%s)", role_id)
            return {"outcome": "terminal", "reason": "role_missing"}
        role = resolved_role

    me = guild.me
    if me is None or not me.guild_permissions.manage_channels:
        logger.warning(
            "[scheduler] Channel unlock retry — missing ManageChannels (%s)",
            action.channel_id,
        )
        return {"outcome": "retryable", "reason": "missing_permissions"}

    overwrite = channel.overwrites_for(role)  # type: ignore[arg-type]
    applied_state: PermissionState = action.applied_state or "deny"  # type: ignore[assignment]

    if not channel_permission_matches(overwrite, permission, applied_state):
        current_state = get_permission_state(overwrite, permission)
        logger.warning(
            "[scheduler] Channel unlock skipped — manual change in %s (expected %s, found %s)",
            action.channel_id,
            applied_state,
            current_state,
        )
        await _log_channel_timed_action(
            guild,
            action,
            log_action="channel_unlock_skipped",
            reason=f"Timed unlock skipped: {permission} was changed manually (now {current_state}).",
            channel=channel,  # type: ignore[arg-type]
            database=database,
        )
        return {"outcome": "terminal", "reason": "manual_change"}

    try:
        result = await restore_channel_from_timed_action(
            channel,  # type: ignore[arg-type]
            role_id,
            permission=permission,
            applied_state=applied_state,
            previous_state=(action.previous_state or "unset"),  # type: ignore[arg-type]
            reason="Timed lock expired",
        )
        if result.kind == "conflict":
            return {"outcome": "terminal", "reason": "manual_change"}

        await _log_channel_timed_action(
            guild,
            action,
            log_action="unlock",
            reason=f"Timed lock expired; restored {permission} to {result.previous_state}.",
            channel=channel,  # type: ignore[arg-type]
            database=database,
        )
        return {"outcome": "completed", "previous_state": result.previous_state}
    except discord.HTTPException as exc:
        logger.error(
            "[scheduler] Channel unlock retry — API error for %s: %s",
            action.channel_id,
            exc,
        )
        return {"outcome": "retryable", "reason": "api_error", "error": exc}


async def _log_channel_timed_action(
    guild: discord.Guild,
    action: TimedActionRecord,
    *,
    log_action: str,
    reason: str,
    channel: discord.abc.GuildChannel | None = None,
    database: Database,
) -> None:
    target_channel = channel or discord.Object(id=int(action.channel_id))  # type: ignore[arg-type]
    moderator: Any
    if action.moderator_id:
        moderator = discord.Object(id=int(action.moderator_id))
    else:
        moderator = "Scheduler"

    guild_settings = GuildSettingsRepository(database)
    await send_mod_log(
        guild,
        action=log_action,
        target=target_channel,
        moderator=moderator,
        reason=reason,
        case_number=None,
        guild_settings=guild_settings,
    )


def _should_log_channel_failure(action: TimedActionRecord, sanitized_error: str) -> bool:
    attempt_count = action.attempt_count
    if attempt_count == 0:
        return True
    if action.last_logged_error != sanitized_error:
        return True
    return attempt_count + 1 >= MAX_CHANNEL_UNLOCK_ATTEMPTS


async def _handle_channel_unlock_retry(
    bot: commands.Bot,
    action: TimedActionRecord,
    result: dict[str, Any],
    *,
    database: Database,
) -> dict[str, str]:
    timed_actions = TimedActionsRepository(database)
    attempt_count = action.attempt_count + 1
    sanitized_error = sanitize_timed_action_error(result.get("error") or result.get("reason"))

    if attempt_count >= MAX_CHANNEL_UNLOCK_ATTEMPTS:
        await timed_actions.fail(
            action.id,
            last_error=sanitized_error,
            attempt_count=attempt_count,
        )
        guild = bot.get_guild(int(action.guild_id))
        if guild is not None:
            await _log_channel_timed_action(
                guild,
                action,
                log_action="channel_unlock_failed",
                reason=(
                    f"Timed unlock abandoned after {MAX_CHANNEL_UNLOCK_ATTEMPTS} attempts. "
                    f"Manual intervention required. Last error: {sanitized_error}"
                ),
                database=database,
            )
        logger.error(
            "[scheduler] Channel unlock %s marked failed after %s attempts",
            action.id,
            MAX_CHANNEL_UNLOCK_ATTEMPTS,
        )
        return {"outcome": "failed_max"}

    next_retry_at = _utc_now_iso_from_ms(get_retry_delay_ms(attempt_count))
    should_log = _should_log_channel_failure(action, sanitized_error)
    await timed_actions.retry(
        action.id,
        attempt_count=attempt_count,
        last_error=sanitized_error,
        next_retry_at=next_retry_at,
        last_logged_error=sanitized_error if should_log else None,
    )

    if should_log:
        logger.warning(
            "[scheduler] Channel unlock %s attempt %s failed (%s); retry at %s",
            action.id,
            attempt_count,
            sanitized_error,
            next_retry_at,
        )
    else:
        logger.warning(
            "[scheduler] Channel unlock %s attempt %s failed (%s); retry scheduled",
            action.id,
            attempt_count,
            sanitized_error,
        )

    return {"outcome": "retryable"}


async def handle_timed_action_result(
    bot: commands.Bot,
    action: TimedActionRecord,
    result: dict[str, Any],
    *,
    database: Database,
) -> None:
    timed_actions = TimedActionsRepository(database)
    outcome = result.get("outcome")

    if outcome in {"completed", "terminal"}:
        removed = await timed_actions.complete(action.id)
        if not removed:
            logger.error(
                "[scheduler] Permission change succeeded but timed action %s could not be removed",
                action.id,
            )
        return

    if outcome == "failed_max":
        return

    if outcome == "retryable" and action.action in {"channel_unlock", "lockdown_channel_restore"}:
        retry_result = await _handle_channel_unlock_retry(bot, action, result, database=database)
        if retry_result.get("outcome") == "failed_max":
            return
        return

    if outcome == "retryable":
        attempt_count = action.attempt_count + 1
        sanitized_error = sanitize_timed_action_error(result.get("error") or result.get("reason"))
        next_retry_at = _utc_now_iso_from_ms(get_retry_delay_ms(attempt_count))
        await timed_actions.retry(
            action.id,
            attempt_count=attempt_count,
            last_error=sanitized_error,
            next_retry_at=next_retry_at,
        )


async def process_due_timed_actions(
    bot: commands.Bot,
    *,
    database: Database,
    configured_guild_id: str,
) -> None:
    timed_actions = TimedActionsRepository(database)
    try:
        actions = await timed_actions.claim_due()
    except Exception as exc:
        logger.error("[scheduler] Database read failed: %s", exc)
        return

    for action in actions:
        try:
            result = await execute_timed_action(
                bot,
                action,
                database=database,
                configured_guild_id=configured_guild_id,
            )
        except Exception as exc:
            logger.error("[scheduler] Action failed: %s", exc)
            result = {"outcome": "retryable", "reason": "unexpected", "error": exc}

        try:
            await handle_timed_action_result(bot, action, result, database=database)
        except Exception as exc:
            logger.error("[scheduler] Failed to persist timed action result: %s", exc)
