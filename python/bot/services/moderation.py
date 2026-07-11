"""Core moderation action orchestration."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import discord

from bot.database.repositories.cases import CasesRepository
from bot.database.repositories.guild_settings import GuildSettingsRepository
from bot.database.repositories.timed_actions import TimedActionsRepository
from bot.result_types import ServiceResult
from bot.services.mod_log import get_or_create_mute_role, send_mod_log
from bot.services.moderation_compensation import (
    persistence_logging_failure_message,
    persistence_rollback_message,
    rollback_temporary_ban,
    rollback_temporary_mute,
)
from bot.utils.helpers import success
from bot.utils.time import format_duration

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _UserTarget:
    id: str

    def __str__(self) -> str:
        return f"<@{self.id}>"


@dataclass(frozen=True, slots=True)
class ModerationReply:
    message: str
    case_number: int | None = None


class ModerationService:
    """Orchestrates moderation actions with case and timed-action persistence."""

    def __init__(
        self,
        *,
        cases: CasesRepository,
        timed_actions: TimedActionsRepository,
        guild_settings: GuildSettingsRepository,
    ) -> None:
        self._cases = cases
        self._timed_actions = timed_actions
        self._guild_settings = guild_settings

    async def _persist_permanent_case(
        self,
        guild: discord.Guild,
        *,
        target: Any,
        moderator: discord.abc.User,
        action: str,
        reason: str,
        success_text: str,
    ) -> ServiceResult[ModerationReply]:
        try:
            case_number = await self._cases.create_case(
                guild_id=str(guild.id),
                user_id=str(getattr(target, "id", target)),
                moderator_id=str(moderator.id),
                action=action,
                reason=reason,
                source="moderation",
            )
            notified = await send_mod_log(
                guild,
                action=action,
                target=target,
                moderator=moderator,
                reason=reason,
                case_number=case_number,
                guild_settings=self._guild_settings,
            )
            if not notified:
                logger.error(
                    "[mod] Mod-log channel notification failed for %s case #%s",
                    action,
                    case_number,
                )
            return ServiceResult.success(
                ModerationReply(f"{success_text} — Case #{case_number}.", case_number),
            )
        except Exception as exc:
            logger.error("[mod] Case persistence failed for %s: %s", action, exc)
            return ServiceResult.failure(persistence_logging_failure_message(action))

    async def ban(
        self,
        guild: discord.Guild,
        moderator: discord.abc.User,
        *,
        user_id: str,
        target_display: Any,
        reason: str,
        duration_ms: int | None = None,
    ) -> ServiceResult[ModerationReply]:
        try:
            await guild.ban(
                discord.Object(id=int(user_id)),
                reason=f"{moderator}: {reason}",
                delete_message_seconds=86400,
            )
        except discord.HTTPException:
            return ServiceResult.failure("Could not ban that user.")

        if duration_ms is not None:
            ends_at = int(time.time() * 1000) + duration_ms
            try:
                case_number, _ = await self._timed_actions.create_temporary_punishment_records(
                    guild_id=str(guild.id),
                    user_id=user_id,
                    moderator_id=str(moderator.id),
                    case_action="ban",
                    case_reason=reason,
                    timed_action="unban",
                    ends_at_ms=ends_at,
                    cases=self._cases,
                )
                notified = await send_mod_log(
                    guild,
                    action="ban",
                    target=target_display,
                    moderator=moderator,
                    reason=reason,
                    case_number=case_number,
                    guild_settings=self._guild_settings,
                )
                if not notified:
                    logger.error("[mod] Mod-log channel notification failed for ban case #%s", case_number)
                display = getattr(target_display, "display_name", None) or user_id
                message = (
                    f"Banned **{display}** — Case #{case_number}. "
                    f"Reason: {reason} (expires in {format_duration(duration_ms)})"
                )
                return ServiceResult.success(ModerationReply(message, case_number))
            except Exception as exc:
                logger.error("[mod] Temporary ban persistence failed: %s", exc)
                rollback = await rollback_temporary_ban(guild, user_id)
                return ServiceResult.failure(persistence_rollback_message("ban", rollback))

        try:
            case_number = await self._cases.create_case(
                guild_id=str(guild.id),
                user_id=user_id,
                moderator_id=str(moderator.id),
                action="ban",
                reason=reason,
                source="moderation",
            )
            notified = await send_mod_log(
                guild,
                action="ban",
                target=target_display,
                moderator=moderator,
                reason=reason,
                case_number=case_number,
                guild_settings=self._guild_settings,
            )
            if not notified:
                logger.error("[mod] Mod-log channel notification failed for ban case #%s", case_number)
            display = getattr(target_display, "display_name", None) or user_id
            return ServiceResult.success(
                ModerationReply(f"Banned **{display}** — Case #{case_number}. Reason: {reason}", case_number),
            )
        except Exception as exc:
            logger.error("[mod] Ban case persistence failed: %s", exc)
            return ServiceResult.failure(persistence_logging_failure_message("banned"))

    async def unban(
        self,
        guild: discord.Guild,
        moderator: discord.abc.User,
        *,
        user_id: str,
        reason: str,
    ) -> ServiceResult[ModerationReply]:
        try:
            await guild.unban(discord.Object(id=int(user_id)), reason=f"{moderator}: {reason}")
        except discord.HTTPException:
            return ServiceResult.failure("Could not unban that user.")
        target = _UserTarget(id=user_id)
        result = await self._persist_permanent_case(
            guild,
            target=target,
            moderator=moderator,
            action="unban",
            reason=reason,
            success_text=f"Unbanned `{user_id}`",
        )
        return result

    async def kick(
        self,
        guild: discord.Guild,
        moderator: discord.abc.User,
        target: discord.Member,
        *,
        reason: str,
    ) -> ServiceResult[ModerationReply]:
        try:
            await target.kick(reason=f"{moderator}: {reason}")
        except discord.HTTPException:
            return ServiceResult.failure("Could not kick that user.")
        return await self._persist_permanent_case(
            guild,
            target=target,
            moderator=moderator,
            action="kick",
            reason=reason,
            success_text=f"Kicked **{target.display_name}**",
        )

    async def softban(
        self,
        guild: discord.Guild,
        moderator: discord.abc.User,
        target: discord.Member,
        *,
        reason: str,
    ) -> ServiceResult[ModerationReply]:
        try:
            await target.ban(reason=f"Softban: {reason}", delete_message_seconds=604800)
            await guild.unban(target, reason="Softban complete")
        except discord.HTTPException:
            return ServiceResult.failure("Could not softban that user.")
        return await self._persist_permanent_case(
            guild,
            target=target,
            moderator=moderator,
            action="softban",
            reason=reason,
            success_text=f"Softbanned **{target.display_name}**",
        )

    async def mute(
        self,
        guild: discord.Guild,
        moderator: discord.abc.User,
        target: discord.Member,
        *,
        reason: str,
        duration_ms: int | None = None,
    ) -> ServiceResult[ModerationReply]:
        mute_role = await get_or_create_mute_role(guild, guild_settings=self._guild_settings)
        try:
            await target.add_roles(mute_role, reason=reason)
        except discord.HTTPException:
            return ServiceResult.failure("Could not mute that user.")

        if duration_ms is not None:
            ends_at = int(time.time() * 1000) + duration_ms
            try:
                case_number, _ = await self._timed_actions.create_temporary_punishment_records(
                    guild_id=str(guild.id),
                    user_id=str(target.id),
                    moderator_id=str(moderator.id),
                    case_action="mute",
                    case_reason=reason,
                    timed_action="unmute",
                    ends_at_ms=ends_at,
                    cases=self._cases,
                )
                notified = await send_mod_log(
                    guild,
                    action="mute",
                    target=target,
                    moderator=moderator,
                    reason=reason,
                    case_number=case_number,
                    guild_settings=self._guild_settings,
                )
                if not notified:
                    logger.error("[mod] Mod-log channel notification failed for mute case #%s", case_number)
                message = (
                    f"Muted **{target.display_name}** — Case #{case_number}. "
                    f"(expires in {format_duration(duration_ms)})"
                )
                return ServiceResult.success(ModerationReply(message, case_number))
            except Exception as exc:
                logger.error("[mod] Temporary mute persistence failed: %s", exc)
                rollback = await rollback_temporary_mute(target, mute_role)
                return ServiceResult.failure(persistence_rollback_message("mute", rollback))

        return await self._persist_permanent_case(
            guild,
            target=target,
            moderator=moderator,
            action="mute",
            reason=reason,
            success_text=f"Muted **{target.display_name}**",
        )

    async def unmute(
        self,
        guild: discord.Guild,
        moderator: discord.abc.User,
        target: discord.Member,
        *,
        reason: str,
    ) -> ServiceResult[ModerationReply]:
        mute_role = await get_or_create_mute_role(guild, guild_settings=self._guild_settings)
        if mute_role not in target.roles:
            return ServiceResult.failure("That user is not muted.")
        try:
            await target.remove_roles(mute_role, reason=reason)
        except discord.HTTPException:
            return ServiceResult.failure("Could not unmute that user.")
        return await self._persist_permanent_case(
            guild,
            target=target,
            moderator=moderator,
            action="unmute",
            reason=reason,
            success_text=f"Unmuted **{target.display_name}**",
        )

    async def deafen(
        self,
        guild: discord.Guild,
        moderator: discord.abc.User,
        target: discord.Member,
        *,
        reason: str,
    ) -> ServiceResult[ModerationReply]:
        if target.voice is None or target.voice.channel is None:
            return ServiceResult.failure("User is not in a voice channel.")
        try:
            await target.edit(deafen=True, reason=reason)
        except discord.HTTPException:
            return ServiceResult.failure("Could not deafen that user.")
        return await self._persist_permanent_case(
            guild,
            target=target,
            moderator=moderator,
            action="deafen",
            reason=reason,
            success_text=f"Deafened **{target.display_name}**",
        )

    async def undeafen(
        self,
        guild: discord.Guild,
        moderator: discord.abc.User,
        target: discord.Member,
        *,
        reason: str = "Undeafened",
    ) -> ServiceResult[ModerationReply]:
        try:
            await target.edit(deafen=False, reason=reason)
        except discord.HTTPException:
            return ServiceResult.failure("Could not undeafen that user.")
        return await self._persist_permanent_case(
            guild,
            target=target,
            moderator=moderator,
            action="undeafen",
            reason=reason,
            success_text=f"Undeafened **{target.display_name}**",
        )

    @staticmethod
    def format_reply(result: ServiceResult[ModerationReply], *, use_success_helper: bool = True) -> str:
        if result.ok and result.value is not None:
            return success(result.value.message) if use_success_helper else result.value.message
        return result.error or "Moderation action failed."
