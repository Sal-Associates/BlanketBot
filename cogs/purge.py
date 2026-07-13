import asyncio
from datetime import timedelta
import discord
from discord import app_commands
from discord.ext import commands
from checks import moderator_check, administrator_check
import db
from utils import LINK_RE, INVITE_RE, resolve_member

MAX_PURGE = 100
MAX_AGE = timedelta(days=14)


def _too_old(msg: discord.Message) -> bool:
    return (discord.utils.utcnow() - msg.created_at) > MAX_AGE


async def _delete(channel, messages: list[discord.Message]) -> int:
    deletable = [m for m in messages if not _too_old(m)]
    if not deletable:
        return 0
    if len(deletable) == 1:
        await deletable[0].delete()
        return 1
    deleted = await channel.delete_messages(deletable)
    return len(deleted)


def _filter_messages(candidates, filter_name, arg, count) -> list[discord.Message]:
    if filter_name == "user":
        return [m for m in candidates if m.author.id == arg.id][:count]
    if filter_name == "match":
        return [m for m in candidates if arg and arg in m.content][:count]
    if filter_name == "not":
        return [m for m in candidates if arg and arg not in m.content][:count]
    if filter_name == "startswith":
        return [m for m in candidates if arg and m.content.startswith(arg)][:count]
    if filter_name == "endswith":
        return [m for m in candidates if arg and m.content.endswith(arg)][:count]
    if filter_name == "links":
        return [m for m in candidates if LINK_RE.search(m.content)][:count]
    if filter_name == "invites":
        return [m for m in candidates if INVITE_RE.search(m.content)][:count]
    if filter_name == "images":
        return [m for m in candidates if any(a.content_type and a.content_type.startswith("image/") for a in m.attachments)][:count]
    if filter_name == "mentions":
        return [m for m in candidates if m.mentions][:count]
    if filter_name == "embeds":
        return [m for m in candidates if m.embeds][:count]
    if filter_name == "bots":
        return [m for m in candidates if m.author.bot][:count]
    if filter_name == "humans":
        return [m for m in candidates if not m.author.bot][:count]
    if filter_name == "text":
        return [m for m in candidates if m.content and not m.attachments and not m.embeds][:count]
    return candidates[:count]


FILTERS = frozenset({"user", "match", "not", "startswith", "endswith", "links",
                      "invites", "images", "mentions", "embeds", "bots", "humans", "text"})
FILTER_HELP = "Filters: user, match, not, startswith, endswith, links, invites, images, mentions, embeds, bots, humans, text"


class Purge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _do_purge(self, channel, invoker_msg_id, guild, actor, filter_name, arg, count):
        if not isinstance(channel, discord.TextChannel | discord.Thread):
            return None, "This command only works in text channels."

        fetched = [m async for m in channel.history(limit=100)]
        candidates = [m for m in fetched if m.id != invoker_msg_id]
        to_delete = _filter_messages(candidates, filter_name, arg, count)
        deleted = await _delete(channel, to_delete)

        with db.get_db() as conn:
            case_number = conn.execute(
                "SELECT COALESCE(MAX(case_number), 0) + 1 FROM mod_actions WHERE guild_id = ?",
                (guild.id,)
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO mod_actions (guild_id, case_number, action, target_id, moderator_id, reason) VALUES (?, ?, ?, ?, ?, ?)",
                (guild.id, case_number, "purge", channel.id, actor.id, f"Purged {deleted} messages ({filter_name})")
            )

        return deleted, None

    @commands.command(name="purge")
    @moderator_check()
    async def prefix_purge(self, ctx, *, args: str = ""):
        parts = args.split()
        filter_name = parts[0].lower() if parts else "any"
        rest = parts[1:] if len(parts) > 1 else []

        if filter_name.isdigit():
            count = min(int(filter_name), MAX_PURGE)
            filter_name = "any"
            arg = None
        elif filter_name in FILTERS:
            count = min(int(rest[-1]), MAX_PURGE) if rest and rest[-1].isdigit() else MAX_PURGE
            arg_parts = rest[:-1] if rest and rest[-1].isdigit() else rest
            if filter_name == "user":
                arg = resolve_member(ctx.guild, arg_parts[0] if arg_parts else None)
                if arg is None:
                    await ctx.send("❌ User not found.")
                    return
            else:
                arg = " ".join(arg_parts)
        elif filter_name == "any":
            count = MAX_PURGE
            arg = None
        else:
            await ctx.send(f"❌ Unknown filter. {FILTER_HELP}")
            return

        deleted, err = await self._do_purge(ctx.channel, ctx.message.id, ctx.guild, ctx.author, filter_name, arg, count)
        if err:
            await ctx.send(f"❌ {err}")
            return

        reply = await ctx.send(f"✅ Deleted **{deleted}** message(s).")
        await asyncio.sleep(5)
        try:
            await reply.delete()
        except discord.HTTPException:
            pass

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to do that.")


async def setup(bot):
    await bot.add_cog(Purge(bot))
