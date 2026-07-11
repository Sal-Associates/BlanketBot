"""Server lockdown enable/disable workflows."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import discord

from bot.database.repositories.cases import CasesRepository
from bot.database.repositories.guild_settings import GuildSettingsRepository
from bot.database.repositories.lockdown import LockdownRepository
from bot.database.repositories.timed_actions import TimedActionsRepository
from bot.result_types import ServiceResult
from bot.services.mod_log import send_mod_log
from bot.utils.channel_permissions import (
    PermissionState,
    apply_permission_state,
    get_permission_state,
    restore_channel_from_timed_action,
)
from bot.utils.helpers import error, success

logger = logging.getLogger(__name__)

LOCKDOWN_PERMISSION = "SendMessages"


@dataclass(frozen=True, slots=True)
class LockdownReply:
    message: str
    case_number: int | None = None


def bot_has_manage_channels(guild: discord.Guild) -> bool:
    me = guild.me
    return bool(me and me.guild_permissions.manage_channels)


def is_lockdown_eligible_channel(channel: discord.abc.GuildChannel | None) -> bool:
    return isinstance(channel, discord.TextChannel | discord.VoiceChannel | discord.StageChannel)


def _parse_iso_timestamp(value: str | None) -> int | None:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return int(datetime.fromisoformat(normalized).timestamp())
    except ValueError:
        return None


async def build_lockdown_status(
    guild: discord.Guild,
    *,
    lockdown: LockdownRepository,
    timed_actions: TimedActionsRepository,
) -> str:
    configured = await lockdown.list_channels(str(guild.id))
    state = await lockdown.get_state(str(guild.id))
    restores = await timed_actions.get_lockdown_restore_diagnostics(str(guild.id))

    channel_lines = []
    for channel_id in configured:
        channel = guild.get_channel(int(channel_id))
        if channel:
            channel_lines.append(f"• {channel} (`{channel_id}`)")
        else:
            channel_lines.append(f"• ~~deleted~~ (`{channel_id}`)")

    applied = [c for c in (state.channels if state else ()) if c.result == "applied"]
    failed = [c for c in (state.channels if state else ()) if c.result == "failed"]

    lines: list[str] = [
        f"**Active:** {'Yes' if state and state.active else 'No'}",
    ]
    if state.active and state.operation:
        started_ts = _parse_iso_timestamp(state.operation.started_at)
        if started_ts and state.operation.started_by:
            lines.append(f"**Started:** <t:{started_ts}:R> by <@{state.operation.started_by}>")
        lines.append(f"**Reason:** {state.operation.reason}")
    elif state is not None and state.operation and state.operation.disabled_at:
        disabled_ts = _parse_iso_timestamp(state.operation.disabled_at)
        if disabled_ts and state.operation.disabled_by:
            lines.append(
                f"**Last disabled:** <t:{disabled_ts}:R> by <@{state.operation.disabled_by}>",
            )

    lines.extend(
        [
            f"**Configured channels:** {len(configured)}",
            f"**Active snapshot:** {len(state.channels) if state else 0} channel(s)",
        ],
    )
    if state and state.active:
        lines.append(f"**Locked successfully:** {len(applied)}")
        lines.append(f"**Lock failures:** {len(failed)}")
    lines.append(f"**Pending restorations:** {len(restores['pending'])}")
    lines.append(f"**Failed restorations:** {len(restores['failed'])}")

    if channel_lines:
        lines.append("\n**Channel list:**\n" + "\n".join(channel_lines))
    else:
        lines.append("\n**Channel list:** none configured")

    return "\n".join(lines)


async def _rollback_applied_channels(
    guild: discord.Guild,
    applied_results: list[dict[str, Any]],
    role_id: int,
) -> list[dict[str, Any]]:
    rollbacks: list[dict[str, Any]] = []
    for entry in applied_results:
        channel = guild.get_channel(int(entry["channel_id"]))
        if channel is None or not is_lockdown_eligible_channel(channel):
            continue
        try:
            await apply_permission_state(
                channel,
                guild.get_role(role_id) or discord.Object(id=role_id),  # type: ignore[arg-type]
                LOCKDOWN_PERMISSION,
                entry["previous_state"],
                reason="Lockdown rollback",
            )
            rollbacks.append({"channel_id": entry["channel_id"], "ok": True})
        except discord.HTTPException as exc:
            rollbacks.append({"channel_id": entry["channel_id"], "ok": False, "error": str(exc)})
    return rollbacks


async def _apply_lock_to_channel(
    channel: discord.abc.GuildChannel,
    role: discord.Role,
) -> dict[str, Any]:
    overwrite = channel.overwrites_for(role)
    previous_state: PermissionState = get_permission_state(overwrite, LOCKDOWN_PERMISSION)
    await apply_permission_state(
        channel,
        role,
        LOCKDOWN_PERMISSION,
        "deny",
        reason="Server lockdown",
    )
    return {
        "channel_id": str(channel.id),
        "previous_state": previous_state,
        "applied_state": "deny",
        "result": "applied",
    }


async def enable_lockdown(
    guild: discord.Guild,
    moderator: discord.Member,
    reason: str | None,
    *,
    lockdown: LockdownRepository,
    cases: CasesRepository,
    guild_settings: GuildSettingsRepository,
    timed_actions: TimedActionsRepository,
) -> ServiceResult[LockdownReply]:
    if not bot_has_manage_channels(guild):
        return ServiceResult.failure("I need the **Manage Channels** permission to run lockdown.")

    existing = await lockdown.get_state(str(guild.id))
    if existing and existing.active:
        return ServiceResult.failure(
            "Lockdown is already active. Use `?channel lockdown disable` to end it.",
        )

    configured_ids = await lockdown.list_channels(str(guild.id))
    if not configured_ids:
        return ServiceResult.failure(
            "No lockdown channels configured. Use `?channel lockdown channel add #channel` first.",
        )

    role_id = guild.default_role.id
    trimmed_reason = (reason or "").strip() or "No reason provided"
    acquire = await lockdown.acquire_enable(
        str(guild.id),
        moderator_id=str(moderator.id),
        reason=trimmed_reason,
        role_id=str(role_id),
        permission=LOCKDOWN_PERMISSION,
    )
    if not acquire.ok or acquire.operation is None:
        return ServiceResult.failure("Lockdown is already active.")
    results: list[dict[str, Any]] = []
    applied: list[dict[str, Any]] = []

    for channel_id in configured_ids:
        channel = guild.get_channel(int(channel_id))
        if channel is None:
            results.append(
                {
                    "channel_id": channel_id,
                    "previous_state": None,
                    "applied_state": "deny",
                    "result": "failed",
                    "error": "channel_missing",
                },
            )
            continue
        if not is_lockdown_eligible_channel(channel):
            results.append(
                {
                    "channel_id": channel_id,
                    "previous_state": None,
                    "applied_state": "deny",
                    "result": "failed",
                    "error": "unsupported_channel",
                },
            )
            continue
        try:
            entry = await _apply_lock_to_channel(channel, guild.default_role)
            results.append(entry)
            applied.append(entry)
        except discord.HTTPException as exc:
            results.append(
                {
                    "channel_id": channel_id,
                    "previous_state": None,
                    "applied_state": "deny",
                    "result": "failed",
                    "error": str(exc),
                },
            )

    success_count = sum(1 for entry in results if entry.get("result") == "applied")
    fail_count = len(results) - success_count

    if success_count == 0:
        await lockdown.clear_active(str(guild.id))
        return ServiceResult.failure(
            f"Lockdown failed — none of the {len(results)} configured channel(s) could be locked.",
        )

    case_number: int | None = None
    try:
        await lockdown.finalize_enable(str(guild.id), results)
        case_action = "lockdown_enable_partial" if fail_count > 0 else "lockdown_enable"
        case_number = await cases.create_case(
            guild_id=str(guild.id),
            user_id=str(guild.id),
            moderator_id=str(moderator.id),
            action=case_action,
            reason=trimmed_reason,
            source="lockdown",
            metadata={
                "configured": len(results),
                "applied": success_count,
                "failed": fail_count,
            },
        )
    except Exception as exc:
        logger.error("[lockdown] Persistence failed after permission changes: %s", exc)
        rollbacks = await _rollback_applied_channels(guild, applied, role_id)
        await lockdown.clear_active(str(guild.id))
        rollback_failed = any(not entry["ok"] for entry in rollbacks)
        message = (
            "Lockdown persistence failed and rollback was incomplete. Manual permission review is required."
            if rollback_failed
            else "Lockdown persistence failed. Permission changes were rolled back."
        )
        return ServiceResult.failure(message)

    summary = (
        f"Lockdown enabled in {success_count} of {len(results)} configured channels. "
        f"{fail_count} channel(s) failed and require review."
        if fail_count > 0
        else f"Lockdown enabled on {success_count} configured channel(s)."
    )

    target = type("GuildTarget", (), {"id": guild.id, "__str__": lambda self: guild.name})()
    await send_mod_log(
        guild,
        action="lockdown_enable_partial" if fail_count > 0 else "lockdown_enable",
        target=target,
        moderator=moderator,
        reason=summary,
        case_number=case_number,
        guild_settings=guild_settings,
    )

    return ServiceResult.success(LockdownReply(f"{summary} — Case #{case_number}.", case_number))


async def disable_lockdown(
    guild: discord.Guild,
    moderator: discord.Member,
    reason: str | None,
    *,
    lockdown: LockdownRepository,
    cases: CasesRepository,
    guild_settings: GuildSettingsRepository,
    timed_actions: TimedActionsRepository,
) -> ServiceResult[LockdownReply]:
    if not bot_has_manage_channels(guild):
        return ServiceResult.failure("I need the **Manage Channels** permission to run lockdown.")

    acquired = await lockdown.acquire_disable(str(guild.id))
    if not acquired.ok or acquired.operation is None:
        return ServiceResult.failure("No active lockdown to disable.")

    operation = acquired.operation
    role_id = int(operation.role_id) if operation.role_id else guild.default_role.id
    permission = operation.permission or LOCKDOWN_PERMISSION
    snapshots = await lockdown.get_snapshots(operation.id)
    applied_entries = [entry for entry in snapshots if entry.result == "applied"]

    summary_counts = {
        "restored": 0,
        "manual_change": 0,
        "missing": 0,
        "failed": 0,
        "scheduled_retry": 0,
    }
    channel_results: list[dict[str, Any]] = []

    for entry in applied_entries:
        channel = guild.get_channel(int(entry.channel_id))
        if channel is None or not is_lockdown_eligible_channel(channel):
            summary_counts["missing"] += 1
            channel_results.append(
                {
                    "channel_id": entry.channel_id,
                    "disable_result": "missing",
                },
            )
            continue

        try:
            restore_result = await restore_channel_from_timed_action(
                channel,
                role_id,
                permission=permission,
                applied_state=entry.applied_state or "deny",  # type: ignore[arg-type]
                previous_state=entry.previous_state or "unset",  # type: ignore[arg-type]
                reason="Lockdown disable",
            )
        except discord.HTTPException as exc:
            summary_counts["failed"] += 1
            channel_results.append(
                {
                    "channel_id": entry.channel_id,
                    "disable_result": "failed",
                    "error": str(exc),
                },
            )
            await timed_actions.add_lockdown_restore_action(
                guild_id=str(guild.id),
                channel_id=entry.channel_id,
                role_id=str(role_id),
                permission=permission,
                previous_state=entry.previous_state or "unset",
                applied_state=entry.applied_state or "deny",
            )
            summary_counts["scheduled_retry"] += 1
            continue

        if restore_result.kind == "conflict":
            summary_counts["manual_change"] += 1
            channel_results.append(
                {
                    "channel_id": entry.channel_id,
                    "disable_result": "manual_change",
                    "current_state": restore_result.current_state,
                },
            )
            continue

        summary_counts["restored"] += 1
        channel_results.append(
            {
                "channel_id": entry.channel_id,
                "disable_result": "restored",
            },
        )

    trimmed_reason = (reason or "").strip() or "Server lockdown disabled"
    case_number: int | None = None
    try:
        await lockdown.finalize_disable(
            str(guild.id),
            moderator_id=str(moderator.id),
            reason=trimmed_reason,
            channel_results=channel_results,
            metadata=dict(summary_counts),
        )
        case_action = (
            "lockdown_restore_failed"
            if summary_counts["failed"] > 0 or summary_counts["scheduled_retry"] > 0
            else "lockdown_disable"
        )
        case_number = await cases.create_case(
            guild_id=str(guild.id),
            user_id=str(guild.id),
            moderator_id=str(moderator.id),
            action=case_action,
            reason=trimmed_reason,
            source="lockdown",
            metadata=dict(summary_counts),
        )
    except Exception as exc:
        logger.error("[lockdown] Disable persistence failed: %s", exc)
        return ServiceResult.failure("Lockdown was processed but the final state could not be saved.")

    parts = [
        f"restored {summary_counts['restored']}",
        f"{summary_counts['manual_change']} manual change(s) preserved" if summary_counts["manual_change"] else None,
        f"{summary_counts['missing']} missing" if summary_counts["missing"] else None,
        f"{summary_counts['scheduled_retry']} pending retry" if summary_counts["scheduled_retry"] else None,
        f"{summary_counts['failed']} failed" if summary_counts["failed"] else None,
    ]
    summary_text = f"Lockdown disabled — {', '.join(part for part in parts if part)}."

    target = type("GuildTarget", (), {"id": guild.id, "__str__": lambda self: guild.name})()
    await send_mod_log(
        guild,
        action=(
            "lockdown_restore_failed"
            if summary_counts["failed"] > 0 or summary_counts["scheduled_retry"] > 0
            else "lockdown_disable"
        ),
        target=target,
        moderator=moderator,
        reason=summary_text,
        case_number=case_number,
        guild_settings=guild_settings,
    )

    return ServiceResult.success(LockdownReply(f"{summary_text} — Case #{case_number}.", case_number))


def format_lockdown_reply(result: ServiceResult[LockdownReply]) -> str:
    if result.ok and result.value is not None:
        return success(result.value.message)
    return error(result.error or "Lockdown operation failed.")
