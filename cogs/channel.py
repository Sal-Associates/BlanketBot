import discord
from discord import app_commands
from discord.ext import commands
import db
from checks import moderator_check, administrator_check, slash_mod_check


class Channel(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def _lock(self, channel, actor, guild):
        if not isinstance(channel, discord.TextChannel | discord.Thread):
            return False, "Can only lock text channels or threads."
        everyone = guild.default_role
        overwrite = channel.overwrites_for(everyone)
        db.save_permission_snapshot(guild.id, channel.id, "lock", overwrite.send_messages)
        try:
            await channel.set_permissions(everyone, send_messages=False)
        except discord.Forbidden:
            return False, "I don't have permission to lock that channel."
        self.bot.dispatch("mod_action", "lock", actor, channel, None, guild)
        return True, f"🔒 Locked {channel.mention}."

    async def _unlock(self, channel, actor, guild):
        if not isinstance(channel, discord.TextChannel | discord.Thread):
            return False, "Can only unlock text channels or threads."
        everyone = guild.default_role
        restore = db.pop_permission_snapshot(guild.id, channel.id, "lock")
        try:
            await channel.set_permissions(everyone, send_messages=restore)
        except discord.Forbidden:
            return False, "I don't have permission to unlock that channel."
        self.bot.dispatch("mod_action", "unlock", actor, channel, None, guild)
        return True, f"🔓 Unlocked {channel.mention}."

    @app_commands.command(name="lock", description="Lock a channel")
    @app_commands.describe(channel="Channel to lock (defaults to current)")
    @app_commands.check(slash_mod_check)
    async def slash_lock(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        target = channel or interaction.channel
        ok, msg = await self._lock(target, interaction.user, interaction.guild)
        await interaction.response.send_message(msg, ephemeral=not ok)

    @app_commands.command(name="unlock", description="Unlock a channel")
    @app_commands.describe(channel="Channel to unlock (defaults to current)")
    @app_commands.check(slash_mod_check)
    async def slash_unlock(self, interaction: discord.Interaction, channel: discord.TextChannel = None):
        target = channel or interaction.channel
        ok, msg = await self._unlock(target, interaction.user, interaction.guild)
        await interaction.response.send_message(msg, ephemeral=not ok)

    @app_commands.command(name="slowmode", description="Set slowmode for a channel (0 to disable)")
    @app_commands.describe(seconds="Delay in seconds (0-21600)", channel="Channel (defaults to current)")
    @app_commands.check(slash_mod_check)
    async def slash_slowmode(self, interaction: discord.Interaction, seconds: int, channel: discord.TextChannel = None):
        if not (0 <= seconds <= 21600):
            await interaction.response.send_message("Seconds must be between 0 and 21600.", ephemeral=True)
            return
        target = channel or interaction.channel
        await target.edit(slowmode_delay=seconds)
        msg = f"Slowmode disabled in {target.mention}." if seconds == 0 else f"Slowmode set to **{seconds}s** in {target.mention}."
        await interaction.response.send_message(msg)

    @commands.group(name="channel", invoke_without_command=True)
    @moderator_check()
    async def prefix_channel(self, ctx):
        await ctx.send("❌ Usage: `?channel lock|unlock|slowmode`")

    @prefix_channel.command(name="lock")
    @moderator_check()
    async def channel_lock(self, ctx, channel: discord.TextChannel = None):
        _, msg = await self._lock(channel or ctx.channel, ctx.author, ctx.guild)
        await ctx.send(msg)

    @prefix_channel.command(name="unlock")
    @moderator_check()
    async def channel_unlock(self, ctx, channel: discord.TextChannel = None):
        _, msg = await self._unlock(channel or ctx.channel, ctx.author, ctx.guild)
        await ctx.send(msg)

    @prefix_channel.command(name="slowmode")
    @moderator_check()
    async def channel_slowmode(self, ctx, seconds: int, channel: discord.TextChannel = None):
        if not (0 <= seconds <= 21600):
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
            await ctx.send(f"❌ {error}")


async def setup(bot):
    await bot.add_cog(Channel(bot))