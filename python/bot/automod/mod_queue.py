"""Send flagged automod messages to the moderation queue."""

from __future__ import annotations

import logging

import discord
from discord.ext import commands

from bot.database.repositories.guild_settings import GuildSettingsRepository
from bot.database.repositories.mod_queue import ModQueueRepository
from bot.views.mod_queue import ModQueueReviewView, build_mod_queue_embed

logger = logging.getLogger(__name__)


async def send_to_mod_queue(
    message: discord.Message,
    reason: str,
    *,
    bot: commands.Bot,
    guild_settings: GuildSettingsRepository,
    mod_queue: ModQueueRepository,
) -> bool:
    try:
        settings = await guild_settings.get(str(message.guild.id))  # type: ignore[union-attr]
        if not settings.mod_queue_enabled or not settings.mod_queue_channel_id:
            return False

        queue_channel = message.guild.get_channel(int(settings.mod_queue_channel_id))  # type: ignore[union-attr]
        if queue_channel is None or not isinstance(queue_channel, discord.TextChannel):
            return False

        try:
            await message.delete()
        except discord.HTTPException:
            pass

        entry = await mod_queue.add(
            guild_id=str(message.guild.id),
            channel_id=str(message.channel.id),
            author_id=str(message.author.id),
            content=message.content[:1000],
            reason=reason,
            message_id=str(message.id),
        )

        embed = build_mod_queue_embed(message, reason)
        view = ModQueueReviewView(entry.id)
        bot.add_view(view)

        queue_msg = await queue_channel.send(embed=embed, view=view)
        await mod_queue.set_queue_message_id(entry.id, str(queue_msg.id))
        return True
    except Exception as exc:
        logger.error("[modQueue] Database error: %s", exc)
        return False
