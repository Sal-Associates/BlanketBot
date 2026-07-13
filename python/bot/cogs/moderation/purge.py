"""?purge — bulk message deletion with filters."""

from __future__ import annotations

import asyncio
from datetime import timedelta

import discord
from discord.ext import commands

from bot.checks.decorators import moderator_required
from bot.cogs.deps import CogRepos
from bot.services.mod_log import send_mod_log
from bot.utils.helpers import INVITE_REGEX, LINK_REGEX, error, success
from bot.utils.resolvers import resolve_member

MAX_PURGE = 100
MAX_AGE = timedelta(days=14)
PURGE_FILTERS = frozenset(
    {
        "user",
        "match",
        "not",
        "startswith",
        "endswith",
        "links",
        "invites",
        "images",
        "mentions",
        "embeds",
        "bots",
        "humans",
        "text",
    },
)


def _is_old(message: discord.Message) -> bool:
    return (discord.utils.utcnow() - message.created_at) > MAX_AGE


async def _bulk_delete(channel: discord.TextChannel | discord.Thread, messages: list[discord.Message]) -> int:
    deletable = [m for m in messages if not _is_old(m)]
    if not deletable:
        return 0
    if len(deletable) == 1:
        await deletable[0].delete()
        return 1
    deleted = await channel.delete_messages(deletable)
    return len(deleted)


class PurgeCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repos = CogRepos(bot)

    @commands.command(name="purge")
    @moderator_required()
    async def purge(self, ctx: commands.Context[commands.Bot], *, args: str = "") -> None:
        parts = args.split()
        filter_name = parts[0].lower() if parts else "any"
        filter_args = " ".join(parts[1:]) if len(parts) > 1 else ""

        if filter_name in PURGE_FILTERS:
            arg_parts = filter_args.split()
        elif filter_name.isdigit():
            filter_args = filter_name
            filter_name = "any"
            arg_parts = []
        else:
            filter_name = "any"
            filter_args = args.strip()
            arg_parts = filter_args.split()

        count = min(int(arg_parts[-1]), MAX_PURGE) if arg_parts and arg_parts[-1].isdigit() else MAX_PURGE

        if not isinstance(ctx.channel, discord.TextChannel | discord.Thread):
            await ctx.reply(error("This command only works in text channels."))
            return

        fetched = [m async for m in ctx.channel.history(limit=100)]
        candidates = [m for m in fetched if m.id != ctx.message.id]

        if filter_name == "any":
            n = min(int(filter_args or MAX_PURGE), MAX_PURGE)
            to_delete = candidates[:n]
        elif filter_name == "user":
            user = resolve_member(ctx.guild, ctx.message, arg_parts[0] if arg_parts else None)  # type: ignore[arg-type]
            if user is None:
                await ctx.reply(error("Usage: `?purge user [user] [count]`"))
                return
            to_delete = [m for m in candidates if m.author.id == user.id][:count]
        elif filter_name == "match":
            text = " ".join(arg_parts[:-1] if arg_parts and arg_parts[-1].isdigit() else arg_parts)
            to_delete = [m for m in candidates if text and text in m.content][:count]
        elif filter_name == "not":
            text = " ".join(arg_parts[:-1] if arg_parts and arg_parts[-1].isdigit() else arg_parts)
            to_delete = [m for m in candidates if text and text not in m.content][:count]
        elif filter_name == "startswith":
            text = " ".join(arg_parts[:-1] if arg_parts and arg_parts[-1].isdigit() else arg_parts)
            to_delete = [m for m in candidates if text and m.content.startswith(text)][:count]
        elif filter_name == "endswith":
            text = " ".join(arg_parts[:-1] if arg_parts and arg_parts[-1].isdigit() else arg_parts)
            to_delete = [m for m in candidates if text and m.content.endswith(text)][:count]
        elif filter_name == "links":
            to_delete = [m for m in candidates if LINK_REGEX.search(m.content)][:count]
        elif filter_name == "invites":
            to_delete = [m for m in candidates if INVITE_REGEX.search(m.content)][:count]
        elif filter_name == "images":
            to_delete = [
                m
                for m in candidates
                if any(a.content_type and a.content_type.startswith("image/") for a in m.attachments)
            ][:count]
        elif filter_name == "mentions":
            to_delete = [m for m in candidates if m.mentions][:count]
        elif filter_name == "embeds":
            to_delete = [m for m in candidates if m.embeds][:count]
        elif filter_name == "bots":
            to_delete = [m for m in candidates if m.author.bot][:count]
        elif filter_name == "humans":
            to_delete = [m for m in candidates if not m.author.bot][:count]
        elif filter_name == "text":
            to_delete = [m for m in candidates if m.content and not m.attachments and not m.embeds][:count]
        else:
            await ctx.reply(
                error(
                    "Filters: any, user, match, not, startswith, endswith, links, invites, "
                    "images, mentions, embeds, bots, humans, text",
                ),
            )
            return

        deleted = await _bulk_delete(ctx.channel, to_delete)
        case_number = await self.repos.cases.create_case(
            guild_id=str(ctx.guild.id),  # type: ignore[union-attr]
            user_id=str(ctx.channel.id),
            moderator_id=str(ctx.author.id),
            action="purge",
            reason=f"Purged {deleted} messages ({filter_name})",
            source="moderation",
        )
        await send_mod_log(
            ctx.guild,  # type: ignore[arg-type]
            action="purge",
            target=ctx.channel,
            moderator=ctx.author,
            reason=f"Purged {deleted} messages ({filter_name})",
            case_number=case_number,
            guild_settings=self.repos.guild_settings,
        )
        reply = await ctx.reply(success(f"Deleted **{deleted}** message(s)."))
        await asyncio.sleep(5)
        try:
            await reply.delete()
        except discord.HTTPException:
            pass


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(PurgeCog(bot))
