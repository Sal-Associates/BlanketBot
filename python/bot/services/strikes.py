"""Strike escalation after warnings."""

from __future__ import annotations

import logging

import discord

from bot.database.repositories.cases import CasesRepository
from bot.database.repositories.guild_settings import GuildSettingsRepository
from bot.database.repositories.strike_state import StrikeStateRepository
from bot.database.repositories.warnings import WarningsRepository
from bot.result_types import ServiceResult
from bot.services.hierarchy import check_bot_can_act_on
from bot.services.mod_log import get_or_create_mute_role, send_mod_log
from bot.services.moderation_compensation import persistence_logging_failure_message
from bot.utils.helpers import success

logger = logging.getLogger(__name__)


async def _record_strike_failure(
    *,
    guild: discord.Guild,
    target: discord.Member,
    moderator: discord.abc.User,
    action: str,
    reason: str,
    log_action: str,
    cases: CasesRepository,
    guild_settings: GuildSettingsRepository,
) -> int | None:
    try:
        case_number = await cases.create_case(
            guild_id=str(guild.id),
            user_id=str(target.id),
            moderator_id=str(moderator.id),
            action=action,
            reason=reason,
            source="strike",
            status="failed",
        )
        notified = await send_mod_log(
            guild,
            action=log_action,
            target=target,
            moderator=moderator,
            reason=reason,
            case_number=case_number,
            guild_settings=guild_settings,
        )
        if not notified:
            logger.error(
                "[strikes] Mod-log channel notification failed for %s case #%s",
                action,
                case_number,
            )
        return case_number
    except Exception as exc:
        logger.error("[strikes] Failed to record %s: %s", action, exc)
        return None


async def check_strike_escalation(
    guild: discord.Guild,
    target: discord.Member,
    moderator: discord.abc.User,
    *,
    guild_settings: GuildSettingsRepository,
    warnings: WarningsRepository,
    cases: CasesRepository,
    strike_state: StrikeStateRepository,
) -> ServiceResult[str] | None:
    """Evaluate strike thresholds after a warning commit. Returns a user message or None."""
    settings = await guild_settings.get(str(guild.id))
    if not settings.strike_enabled:
        return None

    warn_count = await warnings.active_count(str(guild.id), str(target.id))
    mute_at = settings.strike_mute_at
    ban_at = settings.strike_ban_at

    if warn_count >= ban_at:
        if not await strike_state.try_claim_ban_escalation(str(guild.id), str(target.id), ban_at):
            return None

        bot_check = check_bot_can_act_on(guild, target)
        if not bot_check.allowed:
            await _record_strike_failure(
                guild=guild,
                target=target,
                moderator=moderator,
                action="strike_ban_failed",
                reason=f"Auto-ban failed at {warn_count} warnings: {bot_check.reason}",
                log_action="strike_ban_failed",
                cases=cases,
                guild_settings=guild_settings,
            )
            return ServiceResult.failure(f"Strike escalation failed: {bot_check.reason}")

        try:
            await guild.ban(
                target,
                reason=f"Strike escalation: {warn_count} warnings",
                delete_message_seconds=0,
            )
        except discord.HTTPException:
            await _record_strike_failure(
                guild=guild,
                target=target,
                moderator=moderator,
                action="strike_ban_failed",
                reason=f"Auto-ban failed at {warn_count} warnings: Discord rejected the ban",
                log_action="strike_ban_failed",
                cases=cases,
                guild_settings=guild_settings,
            )
            return ServiceResult.failure("Strike escalation failed: could not ban that user.")

        try:
            case_number = await cases.create_case(
                guild_id=str(guild.id),
                user_id=str(target.id),
                moderator_id=str(moderator.id),
                action="strike_ban",
                reason=f"Auto-ban at {warn_count} warnings",
                source="strike",
                status="success",
            )
            notified = await send_mod_log(
                guild,
                action="strike_ban",
                target=target,
                moderator=moderator,
                reason=f"Auto-ban at {warn_count} warnings (threshold: {ban_at})",
                case_number=case_number,
                guild_settings=guild_settings,
            )
            if not notified:
                logger.error(
                    "[strikes] Mod-log channel notification failed for strike_ban case #%s",
                    case_number,
                )
            message = success(
                f"**{target.display_name}** auto-banned — reached **{warn_count}** "
                f"warnings (ban threshold: {ban_at}). Case #{case_number}",
            )
            return ServiceResult.success(message)
        except Exception as exc:
            logger.error("[strikes] Ban succeeded but case logging failed: %s", exc)
            return ServiceResult.failure(persistence_logging_failure_message("auto-banned"))

    if warn_count >= mute_at:
        mute_role = await get_or_create_mute_role(guild, guild_settings=guild_settings)
        if mute_role in target.roles:
            return None

        if not await strike_state.try_claim_mute_escalation(str(guild.id), str(target.id), mute_at):
            return None

        bot_check = check_bot_can_act_on(guild, target)
        if not bot_check.allowed:
            await _record_strike_failure(
                guild=guild,
                target=target,
                moderator=moderator,
                action="strike_mute_failed",
                reason=f"Auto-mute failed at {warn_count} warnings: {bot_check.reason}",
                log_action="strike_mute_failed",
                cases=cases,
                guild_settings=guild_settings,
            )
            return ServiceResult.failure(f"Strike escalation failed: {bot_check.reason}")

        try:
            await target.add_roles(mute_role, reason=f"Strike escalation: {warn_count} warnings")
        except discord.HTTPException:
            await _record_strike_failure(
                guild=guild,
                target=target,
                moderator=moderator,
                action="strike_mute_failed",
                reason=f"Auto-mute failed at {warn_count} warnings: Discord rejected the mute",
                log_action="strike_mute_failed",
                cases=cases,
                guild_settings=guild_settings,
            )
            return ServiceResult.failure("Strike escalation failed: could not mute that user.")

        try:
            case_number = await cases.create_case(
                guild_id=str(guild.id),
                user_id=str(target.id),
                moderator_id=str(moderator.id),
                action="strike_mute",
                reason=f"Auto-mute at {warn_count} warnings",
                source="strike",
                status="success",
            )
            notified = await send_mod_log(
                guild,
                action="strike_mute",
                target=target,
                moderator=moderator,
                reason=f"Auto-mute at {warn_count} warnings (threshold: {mute_at})",
                case_number=case_number,
                guild_settings=guild_settings,
            )
            if not notified:
                logger.error(
                    "[strikes] Mod-log channel notification failed for strike_mute case #%s",
                    case_number,
                )
            message = success(
                f"**{target.display_name}** auto-muted — reached **{warn_count}** "
                f"warnings (mute threshold: {mute_at}). Case #{case_number}",
            )
            return ServiceResult.success(message)
        except Exception as exc:
            logger.error("[strikes] Mute succeeded but case logging failed: %s", exc)
            return ServiceResult.failure(persistence_logging_failure_message("auto-muted"))

    return None
