import discord
from discord import app_commands
from discord.ext import commands
from checks import moderator_check, administrator_check
import db


class Channel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _lock(self, channel, actor, guild):
        if not isinstance(channel, discord.TextChannel | discord.Thread):
            return False, "Can only lock text channels or threads."
        everyone = guild.default_role
        try:
            await channel.set_permissions(everyone, send_messages=False)
        except discord.Forbidden:
            return False, "I don't have permission to lock that channel."

        with db.get_db() as conn:
            case_number = conn.execute(
                "SELECT COALESCE(MAX(case_number), 0) + 1 FROM mod_actions WHERE guild_id = ?",
                (guild.id,)
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO mod_actions (guild_id, case_number, action, target_id, moderator_id, reason) VALUES (?, ?, ?, ?, ?, ?)",
                (guild.id, case_number, "lock", channel.id, actor.id, "Channel locked")
            )
        return True, f"🔒 Locked {channel.mention} — Case #{case_number}."

    async def _unlock(self, channel, actor, guild):
        if not isinstance(channel, discord.TextChannel | discord.Thread):
            return False, "Can only unlock text channels or threads."
        everyone = guild.default_role
        overwrite = channel.overwrites_for(everyone)
        if overwrite.send_messages is not False:
            return False, "That channel isn't locked."
        try:
            await channel.set_permissions(everyone, send_messages=None)
        except discord.Forbidden:
            return False, "I don't have permission to unlock that channel."

        with db.get_db() as conn:
            case_number = conn.execute(
                "SELECT COALESCE(MAX(case_number), 0) + 1 FROM mod_actions WHERE guild_id = ?",
                (guild.id,)
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO mod_actions (guild_id, case_number, action, target_id, moderator_id, reason) VALUES (?, ?, ?, ?, ?, ?)",
                (guild.id, case_number, "unlock", channel.id, actor.id, "Channel unlocked")
            )
        return True, f"🔓 Unlocked {channel.mention} — Case #{case_number}."

    @app_commands.command(name="lock", description="Lock a channel (deny @everyone from sending messages)")
    @app_commands.describe(channel="Channel to lock (defaults to current)")
    @app_commands.default_permissions(manage_channels=True)
    async def slash_lock(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        target = channel or interaction.channel
        ok, msg = await self._lock(target, interaction.user, interaction.guild)
        await interaction.response.send_message(msg, ephemeral=not ok)

    @app_commands.command(name="unlock", description="Unlock a channel")
    @app_commands.describe(channel="Channel to unlock (defaults to current)")
    @app_commands.default_permissions(manage_channels=True)
    async def slash_unlock(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        target = channel or interaction.channel
        ok, msg = await self._unlock(target, interaction.user, interaction.guild)
        await interaction.response.send_message(msg, ephemeral=not ok)

    @app_commands.command(name="slowmode", description="Set slowmode for a channel (0 to disable)")
    @app_commands.describe(seconds="Delay in seconds (0-21600)", channel="Channel (defaults to current)")
    @app_commands.default_permissions(manage_channels=True)
    async def slash_slowmode(self, interaction: discord.Interaction, seconds: int, channel: discord.TextChannel = None):
        if seconds < 0 or seconds > 21600:
            await interaction.response.send_message("Seconds must be between 0 and 21600.", ephemeral=True)
            return
        target = channel or interaction.channel
        await target.edit(slowmode_delay=seconds)
        msg = f"Slowmode disabled in {target.mention}." if seconds == 0 else f"Slowmode set to **{seconds}s** in {target.mention}."
        await interaction.response.send_message(msg)

    @commands.group(name="channel", invoke_without_command=True)
    @administrator_check()
    async def prefix_channel(self, ctx):
        await ctx.send("❌ Usage: `?channel lock|unlock|slowmode`")

    @prefix_channel.command(name="lock")
    @administrator_check()
    async def channel_lock(self, ctx, channel: discord.TextChannel = None):
        target = channel or ctx.channel
        _, msg = await self._lock(target, ctx.author, ctx.guild)
        await ctx.send(msg)

    @prefix_channel.command(name="unlock")
    @administrator_check()
    async def channel_unlock(self, ctx, channel: discord.TextChannel = None):
        target = channel or ctx.channel
        _, msg = await self._unlock(target, ctx.author, ctx.guild)
        await ctx.send(msg)

    @prefix_channel.command(name="slowmode")
    @administrator_check()
    async def channel_slowmode(self, ctx, seconds: int, channel: discord.TextChannel = None):
        if seconds < 0 or seconds > 21600:
            await ctx.send("Seconds must be between 0 and 21600.")
            return
        target = channel or ctx.channel
        await target.edit(slowmode_delay=seconds)
        msg = f"Slowmode disabled in {target.mention}." if seconds == 0 else f"Slowmode set to **{seconds}s** in {target.mention}."
        await ctx.send(msg)

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to do that.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"Bad argument: {error}")


async def setup(bot):
    await bot.add_cog(Channel(bot))
