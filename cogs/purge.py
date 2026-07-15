import asyncio
from datetime import timedelta
import discord
from discord import app_commands
from discord.ext import commands
from checks import moderator_check, slash_mod_check
from utils import LINK_RE, INVITE_RE, resolve_member

MAX_PURGE = 100
MAX_AGE = timedelta(days=14)
FILTERS = frozenset({"user", "match", "not", "startswith", "endswith", "links",
                     "invites", "images", "mentions", "embeds", "bots", "humans", "text"})


def _too_old(msg: discord.Message) -> bool:
    return (discord.utils.utcnow() - msg.created_at) > MAX_AGE


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
        return [m for m in candidates if any(
            a.content_type and a.content_type.startswith("image/") for a in m.attachments
        )][:count]
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


async def _do_purge(bot, channel, skip_id, guild, actor, filter_name, arg, count):
    fetched = [m async for m in channel.history(limit=200)]
    candidates = [m for m in fetched if m.id != skip_id and not _too_old(m)]
    to_delete = _filter_messages(candidates, filter_name, arg, count)

    if not to_delete:
        return 0

    if len(to_delete) == 1:
        await to_delete[0].delete()
    else:
        await channel.delete_messages(to_delete)

    bot.dispatch("mod_action", "purge", actor, channel,
                 f"Purged {len(to_delete)} messages (filter: {filter_name})", guild)
    return len(to_delete)


class Purge(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _parse_args(self, guild, args: str):
        """Returns (filter_name, arg, count, error_str)."""
        parts = args.split()
        if not parts:
            return "any", None, MAX_PURGE, None

        first = parts[0].lower()

        if first.isdigit():
            return "any", None, min(int(first), MAX_PURGE), None

        if first not in FILTERS and first != "any":
            return None, None, 0, f"Unknown filter `{first}`. Valid filters: {', '.join(sorted(FILTERS))}"

        filter_name = first
        rest = parts[1:]
        count = min(int(rest[-1]), MAX_PURGE) if rest and rest[-1].isdigit() else MAX_PURGE
        arg_parts = rest[:-1] if rest and rest[-1].isdigit() else rest

        if filter_name == "user":
            member = resolve_member(guild, arg_parts[0] if arg_parts else None)
            if not member:
                return None, None, 0, "User not found."
            return filter_name, member, count, None

        return filter_name, " ".join(arg_parts), count, None

    @commands.command(name="purge")
    @moderator_check()
    async def prefix_purge(self, ctx, *, args: str = ""):
        filter_name, arg, count, err = self._parse_args(ctx.guild, args)
        if err:
            await ctx.send(f"❌ {err}")
            return

        deleted = await _do_purge(self.bot, ctx.channel, ctx.message.id, ctx.guild, ctx.author, filter_name, arg, count)
        reply = await ctx.send(f"✅ Deleted **{deleted}** message(s).")
        await asyncio.sleep(5)
        try:
            await reply.delete()
        except discord.HTTPException:
            pass

    @app_commands.command(name="purge", description="Bulk delete messages")
    @app_commands.describe(
        count="Number of messages to delete (max 100)",
        filter="Filter: any, user, match, links, invites, images, mentions, embeds, bots, humans, text",
        target="For 'user' filter: mention or ID of the user"
    )
    @app_commands.check(slash_mod_check)
    async def slash_purge(self, interaction: discord.Interaction, count: int = 50,
                          filter: str = "any", target: str = None):
        await interaction.response.defer(ephemeral=True)
        filter = filter.lower()
        if filter not in FILTERS and filter != "any":
            await interaction.followup.send(f"❌ Unknown filter `{filter}`.", ephemeral=True)
            return
        arg = None
        if filter == "user":
            arg = resolve_member(interaction.guild, target)
            if not arg:
                await interaction.followup.send("❌ User not found.", ephemeral=True)
                return
        elif target:
            arg = target

        deleted = await _do_purge(self.bot, interaction.channel, None, interaction.guild,
                                   interaction.user, filter, arg, min(count, MAX_PURGE))
        await interaction.followup.send(f"✅ Deleted **{deleted}** message(s).", ephemeral=True)

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("You don't have permission to do that.")


async def setup(bot):
    await bot.add_cog(Purge(bot))