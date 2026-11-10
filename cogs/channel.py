import re

import discord
from discord import app_commands
from discord.ext import commands
import db
from checks import moderator_check, administrator_check, slash_mod_check


MESSAGE_LINK_RE = re.compile(r"discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)")


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

    async def _resolve_message(self, guild, default_channel, ref: str):
        ref = ref.strip()
        match = MESSAGE_LINK_RE.search(ref)
        if match:
            guild_id, channel_id, message_id = (int(g) for g in match.groups())
            if guild_id != guild.id:
                return None, "That message link is from a different server."
            channel = guild.get_channel_or_thread(channel_id)
            if channel is None:
                return None, "I can't find that channel."
        elif ref.isdigit():
            channel, message_id = default_channel, int(ref)
        else:
            return None, "Provide a message link or a message ID."
        try:
            return await channel.fetch_message(message_id), None
        except discord.NotFound:
            return None, "Message not found."
        except discord.Forbidden:
            return None, "I can't read that channel."

    async def _pin(self, actor, message):
        if message.pinned:
            return False, "That message is already pinned."
        try:
            await message.pin(reason=f"Pinned by {actor}")
        except discord.Forbidden:
            return False, "I don't have permission to pin messages there. The bot needs the Pin Messages permission."
        except discord.HTTPException as e:
            if e.code == 30003:
                return False, "That channel has reached its pin limit."
            return False, f"Pin failed: {e.text}"
        return True, f"📌 Pinned [message]({message.jump_url})."

    @app_commands.command(name="pin", description="Pin a message")
    @app_commands.describe(message="Message link or ID (an ID is looked up in the current channel)")
    @app_commands.check(slash_mod_check)
    async def slash_pin(self, interaction: discord.Interaction, message: str):
        msg, err = await self._resolve_message(interaction.guild, interaction.channel, message)
        if err:
            await interaction.response.send_message(f"❌ {err}", ephemeral=True)
            return
        ok, text = await self._pin(interaction.user, msg)
        await interaction.response.send_message(text, ephemeral=not ok)

    @commands.command(name="pin")
    @moderator_check()
    async def prefix_pin(self, ctx, *, message: str = None):
        if message is None:
            ref = ctx.message.reference
            if not ref or not ref.message_id:
                await ctx.send("❌ Reply to a message, or provide a message link or ID.")
                return
            try:
                msg = await ctx.channel.fetch_message(ref.message_id)
            except discord.HTTPException:
                await ctx.send("❌ Couldn't fetch the replied message.")
                return
        else:
            msg, err = await self._resolve_message(ctx.guild, ctx.channel, message)
            if err:
                await ctx.send(f"❌ {err}")
                return
        _, text = await self._pin(ctx.author, msg)
        await ctx.send(text)

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You don't have permission to do that.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"❌ {error}")


async def setup(bot):
    await bot.add_cog(Channel(bot))