"""Automod message evaluation and spam tracking."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import discord
from discord.ext import commands

from bot.automod.banned_words import find_banned_word_match, format_banned_word_reason
from bot.automod.ignore import is_channel_ignored, is_member_role_ignored
from bot.automod.mod_queue import send_to_mod_queue
from bot.automod.thresholds import caps_percentage, is_mass_mention, resolve_automod_thresholds
from bot.config import Settings
from bot.database.connection import Database
from bot.database.repositories.automod import AutomodLinkListType, AutomodRepository
from bot.database.repositories.banned_words import BannedWordsRepository
from bot.database.repositories.guild_settings import GuildSettingsRepository
from bot.database.repositories.mod_queue import ModQueueRepository
from bot.database.repositories.staff_roles import StaffRolesRepository
from bot.services.authorization import is_moderator
from bot.utils.helpers import INVITE_REGEX, LINK_REGEX

logger = logging.getLogger(__name__)

SPAM_TRACKER_MAX_AGE_MS = 120_000

_spam_tracker: dict[str, _SpamEntry] = {}


@dataclass
class _SpamEntry:
    count: int
    first: float


def _spam_key(guild_id: str | int, user_id: str | int) -> str:
    return f"{guild_id}:{user_id}"


def prune_spam_tracker(now: float | None = None) -> None:
    now_value = now if now is not None else time.time() * 1000
    stale = [key for key, entry in _spam_tracker.items() if now_value - entry.first > SPAM_TRACKER_MAX_AGE_MS]
    for key in stale:
        del _spam_tracker[key]


def track_spam(guild_id: str | int, user_id: str | int, threshold: int, interval_ms: int) -> bool:
    key = _spam_key(guild_id, user_id)
    now = time.time() * 1000
    existing = _spam_tracker.get(key)

    if existing is None or now - existing.first > interval_ms:
        _spam_tracker[key] = _SpamEntry(count=1, first=now)
        if len(_spam_tracker) % 50 == 0:
            prune_spam_tracker(now)
        return False

    existing.count += 1
    _spam_tracker[key] = existing
    return existing.count >= threshold


def reset_spam_tracker() -> None:
    _spam_tracker.clear()


def check_links(content: str, blacklist: list[str], whitelist: list[str]) -> str | None:
    links = LINK_REGEX.findall(content)
    if not links:
        return None

    for link in links:
        lower = link.lower()
        if any(fragment in lower for fragment in whitelist):
            continue
        if not blacklist or any(fragment in lower for fragment in blacklist):
            return link
    return None


async def handle_automod(
    message: discord.Message,
    *,
    bot: commands.Bot,
    database: Database,
    settings: Settings,
) -> bool:
    """Evaluate a message against automod rules. Returns True if action was taken."""
    if message.guild is None or message.author.bot:
        return False

    guild_settings = GuildSettingsRepository(database)
    if await guild_settings.is_module_disabled(str(message.guild.id), "Automod"):
        return False

    automod_repo = AutomodRepository(database)
    ignored_channels = await automod_repo.list_ignored_channels(str(message.guild.id))
    if is_channel_ignored(message.channel.id, ignored_channels):
        return False

    member = message.author if isinstance(message.author, discord.Member) else None
    if member is None:
        return False

    ignored_roles = await automod_repo.list_ignored_roles(str(message.guild.id))
    if is_member_role_ignored(member, ignored_roles):
        return False

    staff_roles_repo = StaffRolesRepository(database)
    if await is_moderator(member, settings=settings, staff_roles=staff_roles_repo):
        return False

    guild_config = resolve_automod_thresholds(await guild_settings.get(str(message.guild.id)))
    content = message.content
    reason: str | None = None

    banned_words = BannedWordsRepository(database)
    entries = await banned_words.list_for_guild(str(message.guild.id))
    banned_match = find_banned_word_match(content, entries)
    if banned_match:
        reason = format_banned_word_reason(banned_match)

    if not reason and guild_config.anti_invite and INVITE_REGEX.search(content):
        reason = "Discord invite link"

    if not reason and guild_config.anti_mention and is_mass_mention(message, guild_config.mention_threshold):
        reason = "Mass mention"

    if not reason:
        blacklist = await automod_repo.list_links(str(message.guild.id), AutomodLinkListType.BLACKLIST)
        whitelist = await automod_repo.list_links(str(message.guild.id), AutomodLinkListType.WHITELIST)
        bad_link = check_links(content, blacklist, whitelist)
        if bad_link:
            reason = f"Blocked link: {bad_link}"

    if not reason and guild_config.anti_caps and caps_percentage(content) >= guild_config.caps_threshold:
        reason = "Excessive caps"

    if not reason and guild_config.anti_spam:
        is_spam = track_spam(
            message.guild.id,
            message.author.id,
            guild_config.spam_threshold,
            guild_config.spam_interval_ms,
        )
        if is_spam:
            reason = "Spam detected"

    if not reason:
        return False

    if guild_config.mod_queue_enabled and guild_config.mod_queue_channel_id:
        mod_queue = ModQueueRepository(database)
        queued = await send_to_mod_queue(
            message,
            reason,
            bot=bot,
            guild_settings=guild_settings,
            mod_queue=mod_queue,
        )
        if queued:
            return True

    try:
        await message.delete()
    except discord.HTTPException:
        pass

    try:
        warning = await message.channel.send(
            f"{message.author.mention}, your message was removed: **{reason}**",
        )
        asyncio.create_task(_delete_warning(warning))
    except discord.HTTPException:
        pass

    return True


async def _delete_warning(message: discord.Message) -> None:
    await asyncio.sleep(5)
    try:
        await message.delete()
    except discord.HTTPException:
        pass
