import discord
from discord import app_commands
from discord.ext import commands
import db
from checks import moderator_check, slash_mod_check


class Notes(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="note", description="Add a staff note for a member")
    @app_commands.describe(member="Who the note is about", content="Note content")
    @app_commands.check(slash_mod_check)
    async def slash_note(self, interaction: discord.Interaction, member: discord.Member, content: str):
        with db.get_db() as conn:
            note_id = conn.execute(
                "INSERT INTO notes (guild_id, user_id, author_id, content) VALUES (?, ?, ?, ?)",
                (interaction.guild.id, member.id, interaction.user.id, content)
            ).lastrowid
        await interaction.response.send_message(f"Added note `#{note_id}` for **{member}**.", ephemeral=True)

    @app_commands.command(name="notes", description="View notes for a member")
    @app_commands.describe(member="Who to check")
    @app_commands.check(slash_mod_check)
    async def slash_notes(self, interaction: discord.Interaction, member: discord.Member):
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT id, author_id, content, created_at FROM notes "
                "WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC",
                (interaction.guild.id, member.id)
            ).fetchall()
        if not rows:
            await interaction.response.send_message(f"No notes for **{member}**.", ephemeral=True)
            return
        lines = [f"`#{r['id']}` {r['content']} — <@{r['author_id']}> on {r['created_at'][:10]}" for r in rows]
        embed = discord.Embed(title=f"Notes for {member}", description="\n".join(lines), color=0xEB459E)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="notedel", description="Delete a note by ID")
    @app_commands.describe(note_id="Note ID to delete")
    @app_commands.check(slash_mod_check)
    async def slash_notedel(self, interaction: discord.Interaction, note_id: int):
        with db.get_db() as conn:
            row = conn.execute("SELECT id FROM notes WHERE id = ? AND guild_id = ?", (note_id, interaction.guild.id)).fetchone()
            if not row:
                await interaction.response.send_message("Note not found.", ephemeral=True)
                return
            conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        await interaction.response.send_message(f"Deleted note `#{note_id}`.", ephemeral=True)

    @commands.group(name="note", invoke_without_command=True)
    @moderator_check()
    async def prefix_note(self, ctx):
        await ctx.send("❌ Usage: `?note add|list|edit|del`")

    @prefix_note.command(name="add")
    @moderator_check()
    async def note_add(self, ctx, member: discord.Member, *, content: str):
        with db.get_db() as conn:
            note_id = conn.execute(
                "INSERT INTO notes (guild_id, user_id, author_id, content) VALUES (?, ?, ?, ?)",
                (ctx.guild.id, member.id, ctx.author.id, content)
            ).lastrowid
        await ctx.send(f"Added note `#{note_id}` for **{member}**.")

    @prefix_note.command(name="list")
    @moderator_check()
    async def note_list(self, ctx, member: discord.Member):
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT id, author_id, content, created_at FROM notes "
                "WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC",
                (ctx.guild.id, member.id)
            ).fetchall()
        if not rows:
            await ctx.send(f"No notes for **{member}**.")
            return
        lines = [f"`#{r['id']}` {r['content']} — <@{r['author_id']}> on {r['created_at'][:10]}" for r in rows]
        embed = discord.Embed(title=f"Notes for {member}", description="\n".join(lines), color=0xEB459E)
        await ctx.send(embed=embed)

    @prefix_note.command(name="edit")
    @moderator_check()
    async def note_edit(self, ctx, note_id: str, *, content: str):
        try:
            parsed = int(note_id.replace("#", ""))
        except ValueError:
            await ctx.send("❌ Invalid note ID.")
            return
        with db.get_db() as conn:
            row = conn.execute("SELECT id FROM notes WHERE id = ? AND guild_id = ?", (parsed, ctx.guild.id)).fetchone()
            if not row:
                await ctx.send("Note not found.")
                return
            conn.execute("UPDATE notes SET content = ? WHERE id = ?", (content, parsed))
        await ctx.send(f"Updated note `#{parsed}`.")

    @prefix_note.command(name="del")
    @moderator_check()
    async def note_del(self, ctx, note_id: str):
        try:
            parsed = int(note_id.replace("#", ""))
        except ValueError:
            await ctx.send("❌ Invalid note ID.")
            return
        with db.get_db() as conn:
            row = conn.execute("SELECT id FROM notes WHERE id = ? AND guild_id = ?", (parsed, ctx.guild.id)).fetchone()
            if not row:
                await ctx.send("Note not found.")
                return
            conn.execute("DELETE FROM notes WHERE id = ?", (parsed,))
        await ctx.send(f"Deleted note `#{parsed}`.")

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.MemberNotFound):
            await ctx.send("Member not found.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing argument: `{error.param.name}`.")


async def setup(bot):
    await bot.add_cog(Notes(bot))