"""Background scheduler loop for timed moderation actions."""

from __future__ import annotations

import logging

from discord.ext import commands, tasks

from bot.scheduler.timed_actions import process_due_timed_actions
from bot.utils.timed_action_retry import SCHEDULER_POLL_INTERVAL_SECONDS

logger = logging.getLogger(__name__)

_scheduler_started = False


@tasks.loop(seconds=SCHEDULER_POLL_INTERVAL_SECONDS)
async def _scheduler_loop() -> None:
    bot = _scheduler_loop.bot  # type: ignore[attr-defined]
    await process_due_timed_actions(
        bot,
        database=bot.database,  # type: ignore[attr-defined]
        configured_guild_id=bot.settings.guild_id,  # type: ignore[attr-defined]
    )


@_scheduler_loop.before_loop
async def _before_scheduler_loop() -> None:
    await _scheduler_loop.bot.wait_until_ready()  # type: ignore[attr-defined]


async def start_scheduler(bot: commands.Bot) -> None:
    """Run due actions immediately, then poll every 15 seconds."""
    global _scheduler_started
    if _scheduler_started:
        return

    await process_due_timed_actions(
        bot,
        database=bot.database,  # type: ignore[attr-defined]
        configured_guild_id=bot.settings.guild_id,  # type: ignore[attr-defined]
    )

    _scheduler_loop.bot = bot  # type: ignore[attr-defined]
    if not _scheduler_loop.is_running():
        _scheduler_loop.start()
    _scheduler_started = True
    logger.info("Timed action scheduler started (interval=%ss)", SCHEDULER_POLL_INTERVAL_SECONDS)


def stop_scheduler() -> None:
    global _scheduler_started
    if _scheduler_loop.is_running():
        _scheduler_loop.cancel()
    _scheduler_started = False
