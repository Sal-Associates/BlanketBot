from datetime import datetime
import discord
from discord import app_commands
from discord.ext import commands
from checks import moderator_check, administrator_check
import db

CASES_PER_PAGE = 5


class ModlogsPaginator(discord.ui.View):
    def __init__(self, pages: list[discord.Embed]):
        super().__init__(timeout=60)
        self.pages = pages
        self.current = 0
        self._refresh()

    def _refresh(self):
        self.prev.disabled = self.current == 0
        self.next.disabled = self.current == len(self.pages) - 1

    @discord.ui.button(label="Previous", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current -= 1
        self._refresh()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)

    @discord.ui.button(label="Next", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current += 1
        self._refresh()
        await interaction.response.edit_message(embed=self.pages[self.current], view=self)


def build_modlogs_pages(member: discord.Member, rows) -> list[discord.Embed] | str:
    if not rows:
        return f"No recorded mod actions for **{member}**."

    chunks = [rows[i:i + CASES_PER_PAGE] for i in range(0, len(rows), CASES_PER_PAGE)]
    total_pages = len(chunks)
    pages = []

    for page_num, chunk in enumerate(chunks, 1):
        lines = []
        for row in chunk:
            try:
                dt = datetime.fromisoformat(row["created_at"])
                date_str = dt.strftime("%b %d %Y %H:%M:%S")
            except (ValueError, TypeError):
                date_str = row["created_at"]

            case_label = f"Case {row['case_number']}" if row["case_number"] else "Case —"
            reason = row["reason"] or "No reason provided"
            duration_str = f" · {row['duration']}" if row["duration"] else ""

            lines.append(
                f"**{case_label}**\n"
                f"Type: {row['action'].capitalize()}\n"
                f"User: {member} ({member.id})\n"
                f"Moderator: <@{row['moderator_id']}>\n"
                f"Reason: {reason}{duration_str} — {date_str}"
            )

        embed = discord.Embed(
            title=f"Modlogs for {member} (Page {page_num} of {total_pages})",
            description="\n\n".join(lines),
            color=discord.Color.blurple()
        )
        pages.append(embed)

    return pages


def build_modstats_embed(target, rows) -> discord.Embed | str:
    target_name = str(target) if hasattr(target, "__str__") else "Server"
    if not rows:
        return f"No recorded mod actions for **{target_name}**."

    data = {
        row["action"]: {"d7": row["d7"], "d30": row["d30"], "total": row["total"]}
        for row in rows
    }

    embed = discord.Embed(description="Moderation Statistics", color=discord.Color.blurple())

    if hasattr(target, "display_avatar"):
        embed.set_author(name=target_name, icon_url=target.display_avatar.url)
    else:
        embed.set_author(name=target_name)

    for action_key, label in [("mute", "Mutes"), ("ban", "Bans"), ("kick", "Kicks"), ("warn", "Warns")]:
        s = data.get(action_key, {"d7": 0, "d30": 0, "total": 0})
        embed.add_field(name=f"{label} (last 7 days):",  value=str(s["d7"]),    inline=True)
        embed.add_field(name=f"{label} (last 30 days):", value=str(s["d30"]),   inline=True)
        embed.add_field(name=f"{label} (all time):",     value=str(s["total"]), inline=True)

    total_d7  = sum(d["d7"]    for d in data.values())
    total_d30 = sum(d["d30"]   for d in data.values())
    total_all = sum(d["total"] for d in data.values())
    embed.add_field(name="Total (last 7 days):",  value=str(total_d7),  inline=True)
    embed.add_field(name="Total (last 30 days):", value=str(total_d30), inline=True)
    embed.add_field(name="Total (all time):",     value=str(total_all), inline=True)

    if hasattr(target, "id"):
        embed.set_footer(text=f"ID: {target.id}")

    return embed


class ModLogs(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _fetch_modlogs(self, guild_id, user_id):
        with db.get_db() as conn:
            return conn.execute(
                "SELECT case_number, action, moderator_id, reason, duration, created_at "
                "FROM mod_actions WHERE guild_id = ? AND target_id = ? ORDER BY created_at DESC",
                (guild_id, user_id)
            ).fetchall()

    def _fetch_modstats(self, guild_id, moderator_id=None):
        with db.get_db() as conn:
            if moderator_id:
                return conn.execute("""
                    SELECT action,
                        SUM(CASE WHEN created_at >= datetime('now', '-7 days')  THEN 1 ELSE 0 END) as d7,
                        SUM(CASE WHEN created_at >= datetime('now', '-30 days') THEN 1 ELSE 0 END) as d30,
                        COUNT(*) as total
                    FROM mod_actions WHERE guild_id = ? AND moderator_id = ?
                    GROUP BY action
                """, (guild_id, moderator_id)).fetchall()
            else:
                return conn.execute("""
                    SELECT action,
                        SUM(CASE WHEN created_at >= datetime('now', '-7 days')  THEN 1 ELSE 0 END) as d7,
                        SUM(CASE WHEN created_at >= datetime('now', '-30 days') THEN 1 ELSE 0 END) as d30,
                        COUNT(*) as total
                    FROM mod_actions WHERE guild_id = ?
                    GROUP BY action
                """, (guild_id,)).fetchall()

    @app_commands.command(name="modlogs", description="View mod history for a user")
    @app_commands.describe(member="Member to look up")
    @app_commands.default_permissions(kick_members=True)
    async def slash_modlogs(self, interaction: discord.Interaction, member: discord.Member):
        rows = self._fetch_modlogs(interaction.guild.id, member.id)
        result = build_modlogs_pages(member, rows)
        if isinstance(result, str):
            await interaction.response.send_message(result, ephemeral=True)
            return
        view = ModlogsPaginator(result) if len(result) > 1 else None
        await interaction.response.send_message(embed=result[0], view=view, ephemeral=True)

    @app_commands.command(name="modstats", description="View moderation stats for a moderator or the server")
    @app_commands.describe(moderator="Moderator to check (omit for server-wide stats)")
    @app_commands.default_permissions(kick_members=True)
    async def slash_modstats(self, interaction: discord.Interaction, moderator: discord.Member = None):
        target = moderator or interaction.guild
        rows = self._fetch_modstats(interaction.guild.id, moderator.id if moderator else None)
        result = build_modstats_embed(target, rows)
        if isinstance(result, str):
            await interaction.response.send_message(result, ephemeral=True)
        else:
            await interaction.response.send_message(embed=result, ephemeral=True)

    @commands.command(name="modlogs")
    @moderator_check()
    async def prefix_modlogs(self, ctx, member: discord.Member):
        rows = self._fetch_modlogs(ctx.guild.id, member.id)
        result = build_modlogs_pages(member, rows)
        if isinstance(result, str):
            await ctx.send(result)
            return
        view = ModlogsPaginator(result) if len(result) > 1 else None
        await ctx.send(embed=result[0], view=view)

    @commands.command(name="modstats")
    @moderator_check()
    async def prefix_modstats(self, ctx, moderator: discord.Member = None):
        target = moderator or ctx.guild
        rows = self._fetch_modstats(ctx.guild.id, moderator.id if moderator else None)
        result = build_modstats_embed(target, rows)
        if isinstance(result, str):
            await ctx.send(result)
        else:
            await ctx.send(embed=result)

    def _fetch_case(self, guild_id, case_number):
        with db.get_db() as conn:
            return conn.execute(
                "SELECT case_number, action, target_id, moderator_id, reason, duration, created_at "
                "FROM mod_actions WHERE guild_id = ? AND case_number = ?",
                (guild_id, case_number)
            ).fetchone()

    def _build_case_embed(self, row) -> discord.Embed:
        embed = discord.Embed(title=f"Case #{row['case_number']} — {row['action'].capitalize()}", color=discord.Color.blurple())
        embed.add_field(name="User", value=f"<@{row['target_id']}> ({row['target_id']})", inline=True)
        embed.add_field(name="Moderator", value=f"<@{row['moderator_id']}>", inline=True)
        if row["duration"]:
            embed.add_field(name="Duration", value=row["duration"], inline=True)
        embed.add_field(name="Reason", value=row["reason"] or "No reason provided", inline=False)
        embed.add_field(name="Date", value=row["created_at"][:10], inline=True)
        return embed

    @app_commands.command(name="case", description="Look up a specific case by number")
    @app_commands.describe(number="Case number to look up")
    @app_commands.default_permissions(kick_members=True)
    async def slash_case(self, interaction: discord.Interaction, number: int):
        row = self._fetch_case(interaction.guild.id, number)
        if not row:
            await interaction.response.send_message(f"Case #{number} not found.", ephemeral=True)
            return
        await interaction.response.send_message(embed=self._build_case_embed(row), ephemeral=True)

    @commands.command(name="case")
    @moderator_check()
    async def prefix_case(self, ctx, number: int):
        row = self._fetch_case(ctx.guild.id, number)
        if not row:
            await ctx.send(f"Case #{number} not found.")
            return
        await ctx.send(embed=self._build_case_embed(row))

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.MemberNotFound):
            await ctx.send("Member not found.")
        elif isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to do that.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"Bad argument: {error}")


async def setup(bot):
    await bot.add_cog(ModLogs(bot))
