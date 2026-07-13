import os
import discord
from discord.ext import commands
import db

# env var kept as fallback for servers that haven't run ?settings logchannel yet
_FALLBACK_LOG_CHANNEL = int(os.getenv("LOG_CHANNEL_ID", 0))

ACTION_COLORS = {
    "kick":             discord.Color.orange(),
    "ban":              discord.Color.red(),
    "unban":            discord.Color.green(),
    "mute":             discord.Color.dark_orange(),
    "unmute":           discord.Color.teal(),
    "warn":             discord.Color.yellow(),
    "softban":          discord.Color.dark_red(),
    "lock":             discord.Color.dark_gray(),
    "unlock":           discord.Color.light_gray(),
    "lockdown_enable":  discord.Color.red(),
    "lockdown_disable": discord.Color.green(),
}


class ModLog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_log_channel_id(self, guild_id: int) -> int:
        settings = db.get_guild_settings(guild_id)
        if settings and settings["log_channel"]:
            return settings["log_channel"]
        return _FALLBACK_LOG_CHANNEL

    async def post(self, guild: discord.Guild, embed: discord.Embed):
        channel_id = self._get_log_channel_id(guild.id)
        if not channel_id:
            return
        channel = guild.get_channel(channel_id)
        if channel:
            await channel.send(embed=embed)

    @commands.Cog.listener()
    async def on_mod_action(self, action: str, moderator, target, reason: str | None, guild: discord.Guild, duration: str = None):
        with db.get_db() as conn:
            case_number = conn.execute(
                "SELECT COALESCE(MAX(case_number), 0) + 1 FROM mod_actions WHERE guild_id = ?",
                (guild.id,)
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO mod_actions (guild_id, case_number, action, target_id, moderator_id, reason, duration) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (guild.id, case_number, action, target.id, moderator.id, reason, duration)
            )

        embed = discord.Embed(
            title=f"Case #{case_number} — {action.capitalize()}",
            color=ACTION_COLORS.get(action, discord.Color.blurple()),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="User", value=f"{target} ({target.id})", inline=True)
        embed.add_field(name="Moderator", value=f"{moderator} ({moderator.id})", inline=True)
        if duration:
            embed.add_field(name="Duration", value=duration, inline=True)
        if reason:
            embed.add_field(name="Reason", value=reason, inline=False)
        await self.post(guild, embed)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = discord.Embed(
            title="Member joined",
            description=f"{member.mention} ({member})",
            color=discord.Color.green(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Account age", value=discord.utils.format_dt(member.created_at, "R"))
        embed.set_thumbnail(url=member.display_avatar.url)
        await self.post(member.guild, embed)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = discord.Embed(
            title="Member left",
            description=f"{member} ({member.id})",
            color=discord.Color.dark_gray(),
            timestamp=discord.utils.utcnow()
        )
        await self.post(member.guild, embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        embed = discord.Embed(
            title="Message deleted",
            description=message.content or "*[no text content]*",
            color=discord.Color.dark_red(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Author", value=f"{message.author} ({message.author.id})", inline=True)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        await self.post(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.author.bot or not before.guild or before.content == after.content:
            return
        embed = discord.Embed(
            title="Message edited",
            color=discord.Color.blue(),
            timestamp=discord.utils.utcnow()
        )
        embed.add_field(name="Before", value=before.content or "*empty*", inline=False)
        embed.add_field(name="After", value=after.content or "*empty*", inline=False)
        embed.add_field(name="Author", value=f"{before.author} ({before.author.id})", inline=True)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        await self.post(before.guild, embed)


async def setup(bot):
    await bot.add_cog(ModLog(bot))
