import discord
from discord import app_commands
from discord.ext import commands
import db


class Whois(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _build_embed(self, target: discord.Member, guild_id: int) -> discord.Embed:
        with db.get_db() as conn:
            warning_count = conn.execute(
                "SELECT COUNT(*) FROM warnings WHERE guild_id = ? AND user_id = ?",
                (guild_id, target.id)
            ).fetchone()[0]
            note_count = conn.execute(
                "SELECT COUNT(*) FROM notes WHERE guild_id = ? AND user_id = ?",
                (guild_id, target.id)
            ).fetchone()[0]
            recent_cases = conn.execute(
                "SELECT case_number, action, reason, created_at FROM mod_actions "
                "WHERE guild_id = ? AND target_id = ? ORDER BY created_at DESC LIMIT 5",
                (guild_id, target.id)
            ).fetchall()

        color = target.colour.value if target.colour.value else 0x5865F2
        embed = discord.Embed(title=str(target), color=color)
        embed.set_thumbnail(url=target.display_avatar.url)

        embed.add_field(name="ID", value=str(target.id), inline=True)
        joined = f"<t:{int(target.joined_at.timestamp())}:R>" if target.joined_at else "Unknown"
        embed.add_field(name="Joined", value=joined, inline=True)
        embed.add_field(name="Created", value=f"<t:{int(target.created_at.timestamp())}:R>", inline=True)

        roles = [r.mention for r in target.roles if r.name != "@everyone"]
        embed.add_field(name="Roles", value=" ".join(roles) if roles else "None", inline=False)

        embed.add_field(name="Warnings", value=str(warning_count), inline=True)
        embed.add_field(name="Notes", value=str(note_count), inline=True)

        if recent_cases:
            lines = [
                f"**#{c['case_number']}** {c['action']} — {c['reason'] or 'No reason'} ({c['created_at'][:10]})"
                for c in recent_cases
            ]
            embed.add_field(name="Recent Cases", value="\n".join(lines), inline=False)

        return embed

    @app_commands.command(name="whois", description="View a member's profile and mod history")
    @app_commands.describe(member="Member to look up (defaults to you)")
    async def slash_whois(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        embed = self._build_embed(target, interaction.guild.id)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @commands.command(name="whois")
    async def prefix_whois(self, ctx, member: discord.Member = None):
        target = member or ctx.author
        embed = self._build_embed(target, ctx.guild.id)
        await ctx.send(embed=embed)

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.MemberNotFound):
            await ctx.send("Member not found.")


async def setup(bot):
    await bot.add_cog(Whois(bot))
