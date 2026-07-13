"""?note — staff notes."""

from __future__ import annotations

from discord.ext import commands

from bot.checks.decorators import moderator_required
from bot.cogs.deps import CogRepos
from bot.utils.helpers import basic_embed, error, success
from bot.utils.resolvers import resolve_member
from bot.utils.time import format_iso_date


class NoteCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repos = CogRepos(bot)

    @commands.group(name="note", invoke_without_command=True)
    @moderator_required()
    async def note(self, ctx: commands.Context[commands.Bot]) -> None:
        await ctx.reply(error("Usage: `?note add|list|edit|del`"))

    @note.command(name="add")
    @moderator_required()
    async def note_add(self, ctx: commands.Context[commands.Bot], *, args: str) -> None:
        parts = args.split()
        target = resolve_member(ctx.guild, ctx.message, parts[0])  # type: ignore[arg-type]
        content = " ".join(parts[1:])
        if target is None or not content:
            await ctx.reply(error("Usage: `?note add <user> <text>`"))
            return
        note_id = await self.repos.notes.create(
            guild_id=str(ctx.guild.id),  # type: ignore[union-attr]
            user_id=str(target.id),
            author_id=str(ctx.author.id),
            content=content,
        )
        await ctx.reply(success(f"Added note #{note_id} for **{target.display_name}**."))

    @note.command(name="list")
    @moderator_required()
    async def note_list(self, ctx: commands.Context[commands.Bot], *, user_arg: str) -> None:
        target = resolve_member(ctx.guild, ctx.message, user_arg)  # type: ignore[arg-type]
        if target is None:
            await ctx.reply(error("Usage: `?note list <user>`"))
            return
        notes = await self.repos.notes.list_for_user(str(ctx.guild.id), str(target.id))  # type: ignore[union-attr]
        if not notes:
            await ctx.reply(error(f"No notes for **{target.display_name}**."))
            return
        lines = [f"**#{n.id}** — {n.content} ({format_iso_date(n.created_at)})" for n in notes]
        await ctx.reply(
            embed=basic_embed(f"Notes: {target.display_name}", "\n".join(lines), color=0xEB459E),
        )

    @note.command(name="edit")
    @moderator_required()
    async def note_edit(self, ctx: commands.Context[commands.Bot], *, args: str) -> None:
        parts = args.split()
        note_id = int(parts[0].replace("#", ""), 10) if parts else 0
        content = " ".join(parts[1:])
        if not note_id or not content:
            await ctx.reply(error("Usage: `?note edit <note ID> <text>`"))
            return
        if not await self.repos.notes.update(note_id, author_id=str(ctx.author.id), content=content):
            await ctx.reply(error("Note not found."))
            return
        await ctx.reply(success(f"Updated note #{note_id}."))

    @note.command(name="del")
    @moderator_required()
    async def note_del(self, ctx: commands.Context[commands.Bot], note_id: str) -> None:
        parsed = int(note_id.replace("#", ""), 10)
        if not parsed:
            await ctx.reply(error("Usage: `?note del <note ID>`"))
            return
        if not await self.repos.notes.delete(parsed):
            await ctx.reply(error("Note not found."))
            return
        await ctx.reply(success(f"Deleted note #{parsed}."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(NoteCog(bot))
