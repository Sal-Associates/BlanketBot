"""Persistent mod queue review buttons and interaction handling."""

from __future__ import annotations

import logging
import re

import discord
from discord.ext import commands

from bot.config import Settings
from bot.database.connection import Database
from bot.database.models import ModQueueStatus
from bot.database.repositories.cases import CasesRepository
from bot.database.repositories.guild_settings import GuildSettingsRepository
from bot.database.repositories.mod_queue import ModQueueRepository
from bot.database.repositories.staff_roles import StaffRolesRepository
from bot.database.repositories.strike_state import StrikeStateRepository
from bot.database.repositories.warnings import WarningsRepository
from bot.services.authorization import is_moderator
from bot.services.hierarchy import get_moderation_denied
from bot.services.mod_log import send_mod_log
from bot.services.strikes import check_strike_escalation
from bot.utils.helpers import error, success

logger = logging.getLogger(__name__)

_QUEUE_BUTTON_RE = re.compile(r"^queue_(approve|deny)_(\d+)$")


def build_mod_queue_embed(message: discord.Message, reason: str) -> discord.Embed:
    content = message.content[:1000] or "*empty*"
    return (
        discord.Embed(
            title="Automod Flag — Review Required",
            colour=0xE67E22,
            timestamp=discord.utils.utcnow(),
        )
        .add_field(name="User", value=f"{message.author} (`{message.author.id}`)", inline=True)
        .add_field(
            name="Channel",
            value=str(message.channel),
            inline=True,
        )
        .add_field(name="Violation", value=reason, inline=False)
        .add_field(
            name="Message Content",
            value=content,
            inline=False,
        )
    )


class ModQueueReviewView(discord.ui.View):
    """Persistent approve/deny buttons for a single queue entry."""

    def __init__(self, entry_id: int) -> None:
        super().__init__(timeout=None)
        self.entry_id = entry_id
        self.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.success,
                label="Approve (false positive)",
                custom_id=f"queue_approve_{entry_id}",
            ),
        )
        self.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.danger,
                label="Deny & Warn",
                custom_id=f"queue_deny_{entry_id}",
            ),
        )


def _queue_already_handled(result_status: str) -> str | None:
    if result_status == "already_processed":
        return error("This queue item was already reviewed.")
    if result_status == "not_found":
        return error("This queue item was not found.")
    return None


async def handle_mod_queue_interaction(
    interaction: discord.Interaction,
    *,
    database: Database,
    settings: Settings,
) -> bool:
    """Handle mod queue button presses. Returns True if the interaction was consumed."""
    if interaction.guild is None or interaction.user is None:
        return False

    custom_id = interaction.custom_id
    if not custom_id:
        return False

    match = _QUEUE_BUTTON_RE.match(custom_id)
    if not match:
        return False

    staff_roles = StaffRolesRepository(database)
    member = interaction.user if isinstance(interaction.user, discord.Member) else None
    if not await is_moderator(member, settings=settings, staff_roles=staff_roles):
        await interaction.response.send_message(
            error("Only moderators can review queue items."),
            ephemeral=True,
        )
        return True

    is_approve = match.group(1) == "approve"
    entry_id = int(match.group(2))

    mod_queue = ModQueueRepository(database)
    try:
        entry = await mod_queue.get(entry_id)
    except Exception as exc:
        logger.error("[interaction] Database read failed: %s", exc)
        await interaction.response.send_message(
            error("Could not load that queue item."),
            ephemeral=True,
        )
        return True

    if entry is None:
        await interaction.response.send_message(
            error("This queue item was not found."),
            ephemeral=True,
        )
        return True

    target = interaction.guild.get_member(int(entry.author_id))
    if target is None:
        try:
            target = await interaction.guild.fetch_member(int(entry.author_id))
        except discord.HTTPException:
            target = None

    if not is_approve and target is not None and member is not None:
        hierarchy_denied = get_moderation_denied(interaction.guild, member, target)
        if hierarchy_denied:
            await interaction.response.send_message(hierarchy_denied, ephemeral=True)
            return True

    cases = CasesRepository(database)
    guild_settings = GuildSettingsRepository(database)

    try:
        if is_approve:
            result = await mod_queue.process_decision(
                entry_id=entry_id,
                moderator_id=str(interaction.user.id),
                decision="approve",
                case_action="queue_approve",
                case_reason=f"False positive: {entry.reason}",
                cases=cases,
            )
            handled = _queue_already_handled(result.status)
            if handled:
                await interaction.response.send_message(handled, ephemeral=True)
                return True

            await send_mod_log(
                interaction.guild,
                action="queue_approve",
                target=target or discord.Object(id=int(entry.author_id)),
                moderator=interaction.user,
                reason=f"Approved (false positive): {entry.reason}",
                case_number=result.case_number,
                guild_settings=guild_settings,
            )

            if interaction.message and interaction.message.embeds:
                embed = interaction.message.embeds[0].copy()
                embed.title = "Approved — False Positive"
                embed.colour = 0x57F287
                embed.set_footer(
                    text=f"Reviewed by {interaction.user} · Case #{result.case_number}",
                )
                await interaction.message.edit(embed=embed, view=None)

            await interaction.response.send_message(
                success(f"Approved — Case #{result.case_number} logged."),
                ephemeral=True,
            )
            return True

        if target is None:
            result = await mod_queue.process_decision(
                entry_id=entry_id,
                moderator_id=str(interaction.user.id),
                decision="deny",
                case_action="queue_deny",
                case_reason=f"Automod violation: {entry.reason} (user left)",
                cases=cases,
            )
            handled = _queue_already_handled(result.status)
            if handled:
                await interaction.response.send_message(handled, ephemeral=True)
                return True

            if interaction.message:
                await interaction.message.edit(view=None)
            await interaction.response.send_message(
                success("Denied — user has left the server."),
                ephemeral=True,
            )
            return True

        result = await mod_queue.process_decision(
            entry_id=entry_id,
            moderator_id=str(interaction.user.id),
            decision="deny",
            warn_reason=f"Automod: {entry.reason}",
            case_action="queue_deny",
            case_reason=f"Automod violation: {entry.reason}",
            cases=cases,
        )
        handled = _queue_already_handled(result.status)
        if handled:
            await interaction.response.send_message(handled, ephemeral=True)
            return True

        await send_mod_log(
            interaction.guild,
            action="queue_deny",
            target=target,
            moderator=interaction.user,
            reason=f"Denied & warned: {entry.reason}",
            case_number=result.case_number,
            guild_settings=guild_settings,
        )

        warnings_repo = WarningsRepository(database)
        strike_state = StrikeStateRepository(database)
        escalation = await check_strike_escalation(
            interaction.guild,
            target,
            interaction.user,
            guild_settings=guild_settings,
            warnings=warnings_repo,
            cases=cases,
            strike_state=strike_state,
        )

        if interaction.message and interaction.message.embeds:
            embed = interaction.message.embeds[0].copy()
            embed.title = "Denied — User Warned"
            embed.colour = 0xED4245
            embed.set_footer(
                text=f"Reviewed by {interaction.user} · Case #{result.case_number}",
            )
            await interaction.message.edit(embed=embed, view=None)

        reply = success(f"Denied — warned user. Case #{result.case_number}.")
        if escalation and escalation.ok and escalation.value:
            reply = f"{reply}\n{escalation.value}"
        await interaction.response.send_message(reply, ephemeral=True)
        return True
    except Exception as exc:
        logger.error("[interaction] Database write failed: %s", exc)
        if interaction.response.is_done():
            await interaction.followup.send(
                error("Could not save the queue review."),
                ephemeral=True,
            )
        else:
            await interaction.response.send_message(
                error("Could not save the queue review."),
                ephemeral=True,
            )
        return True


async def register_persistent_mod_queue_views(bot: commands.Bot) -> None:
    """Re-register persistent views for pending queue entries after restart."""
    database: Database = bot.database  # type: ignore[attr-defined]
    guild_id: str = bot.settings.guild_id  # type: ignore[attr-defined]
    rows = await database.fetchall(
        """
        SELECT id FROM mod_queue
        WHERE guild_id = ? AND status = ? AND queue_message_id IS NOT NULL
        ORDER BY id
        """,
        (guild_id, ModQueueStatus.PENDING.value),
    )
    for row in rows:
        bot.add_view(ModQueueReviewView(int(row["id"])))
    if rows:
        logger.info("Registered %s persistent mod queue view(s)", len(rows))
