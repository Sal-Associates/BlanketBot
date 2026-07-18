import discord
from discord.ext import commands
import db
from checks import administrator_check


class Lockdown(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="lockdown", invoke_without_command=True)
    @administrator_check()
    async def lockdown(self, ctx):
        await ctx.send("❌ Usage: `?lockdown enable|disable|status|channel`")

    @lockdown.command(name="enable")
    @administrator_check()
    async def lockdown_enable(self, ctx, *, reason: str = ""):
        with db.get_db() as conn:
            channels = conn.execute(
                "SELECT channel_id FROM lockdown_channels WHERE guild_id = ?", (ctx.guild.id,)
            ).fetchall()
        if not channels:
            await ctx.send("❌ No lockdown channels configured. Use `?lockdown channel add #channel` first.")
            return
        if not ctx.guild.me.guild_permissions.manage_channels:
            await ctx.send("❌ I need **Manage Channels** permission to lock channels.")
            return

        everyone = ctx.guild.default_role
        locked, failed = [], []
        for row in channels:
            channel = ctx.guild.get_channel(row["channel_id"])
            if not channel:
                continue
            previous = channel.overwrites_for(everyone).send_messages
            try:
                await channel.set_permissions(everyone, send_messages=False, reason=f"Lockdown: {reason or 'No reason'}")
                db.save_permission_snapshot(ctx.guild.id, channel.id, "lockdown", previous)
                locked.append(channel.mention)
            except discord.HTTPException:
                failed.append(channel.mention)

        self.bot.dispatch("mod_action", "lockdown_enable", ctx.author, ctx.guild, reason or None, ctx.guild)
        msg = f"🔒 Server locked. Channels: {', '.join(locked) or 'none'}"
        if failed:
            msg += f"\n⚠️ Failed: {', '.join(failed)}"
        await ctx.send(msg)

    @lockdown.command(name="disable")
    @administrator_check()
    async def lockdown_disable(self, ctx, *, reason: str = ""):
        with db.get_db() as conn:
            channels = conn.execute(
                "SELECT channel_id FROM lockdown_channels WHERE guild_id = ?", (ctx.guild.id,)
            ).fetchall()
        if not channels:
            await ctx.send("❌ No lockdown channels configured.")
            return

        everyone = ctx.guild.default_role
        unlocked, failed = [], []
        for row in channels:
            channel = ctx.guild.get_channel(row["channel_id"])
            if not channel:
                continue
            restore, found = db.get_permission_snapshot(ctx.guild.id, channel.id, "lockdown")
            if not found:
                restore = None
            try:
                await channel.set_permissions(everyone, send_messages=restore, reason=f"Lockdown lifted: {reason or 'No reason'}")
                if found:
                    db.delete_permission_snapshot(ctx.guild.id, channel.id, "lockdown")
                unlocked.append(channel.mention)
            except discord.HTTPException:
                failed.append(channel.mention)

        self.bot.dispatch("mod_action", "lockdown_disable", ctx.author, ctx.guild, reason or None, ctx.guild)
        msg = f"🔓 Server unlocked. Channels: {', '.join(unlocked) or 'none'}"
        if failed:
            msg += f"\n⚠️ Failed: {', '.join(failed)}"
        await ctx.send(msg)

    @lockdown.command(name="status")
    @administrator_check()
    async def lockdown_status(self, ctx):
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT channel_id FROM lockdown_channels WHERE guild_id = ?", (ctx.guild.id,)
            ).fetchall()
        if not rows:
            await ctx.send("No lockdown channels configured. Use `?lockdown channel add #channel`.")
            return
        everyone = ctx.guild.default_role
        lines = []
        for row in rows:
            channel = ctx.guild.get_channel(row["channel_id"])
            if not channel:
                lines.append(f"~~{row['channel_id']}~~ (deleted)")
                continue
            overwrite = channel.overwrites_for(everyone)
            status = "🔒 Locked" if overwrite.send_messages is False else "🔓 Open"
            lines.append(f"{status} {channel.mention}")
        embed = discord.Embed(title="Lockdown Status", description="\n".join(lines), color=discord.Color.blurple())
        await ctx.send(embed=embed)

    @lockdown.group(name="channel", invoke_without_command=True)
    @administrator_check()
    async def lockdown_channel(self, ctx):
        await ctx.send("❌ Usage: `?lockdown channel add|remove|list [#channel]`")

    @lockdown_channel.command(name="add")
    @administrator_check()
    async def lockdown_channel_add(self, ctx, channel: discord.TextChannel):
        with db.get_db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO lockdown_channels (guild_id, channel_id) VALUES (?, ?)",
                (ctx.guild.id, channel.id)
            )
        await ctx.send(f"✅ {channel.mention} added to lockdown channels.")

    @lockdown_channel.command(name="remove", aliases=["del"])
    @administrator_check()
    async def lockdown_channel_remove(self, ctx, channel: discord.TextChannel):
        with db.get_db() as conn:
            conn.execute(
                "DELETE FROM lockdown_channels WHERE guild_id = ? AND channel_id = ?",
                (ctx.guild.id, channel.id)
            )
        await ctx.send(f"✅ {channel.mention} removed from lockdown channels.")

    @lockdown_channel.command(name="list")
    @administrator_check()
    async def lockdown_channel_list(self, ctx):
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT channel_id FROM lockdown_channels WHERE guild_id = ?", (ctx.guild.id,)
            ).fetchall()
        if not rows:
            await ctx.send("No lockdown channels configured.")
            return
        await ctx.send("Lockdown channels: " + ", ".join(f"<#{r['channel_id']}>" for r in rows))

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("You don't have permission to use lockdown commands.")
        elif isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
            await ctx.send(f"❌ {error}")


async def setup(bot):
    await bot.add_cog(Lockdown(bot))