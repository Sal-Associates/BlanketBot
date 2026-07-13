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

        bot_member = ctx.guild.me
        if not bot_member.guild_permissions.manage_channels:
            await ctx.send("❌ I need **Manage Channels** permission to lock channels.")
            return

        everyone = ctx.guild.default_role
        locked, failed = [], []

        for row in channels:
            channel = ctx.guild.get_channel(row["channel_id"])
            if not channel:
                continue
            try:
                await channel.set_permissions(everyone, send_messages=False, reason=f"Lockdown: {reason or 'No reason'}")
                locked.append(channel.mention)
            except discord.HTTPException:
                failed.append(channel.mention)

        with db.get_db() as conn:
            case_number = conn.execute(
                "SELECT COALESCE(MAX(case_number), 0) + 1 FROM mod_actions WHERE guild_id = ?",
                (ctx.guild.id,)
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO mod_actions (guild_id, case_number, action, target_id, moderator_id, reason) VALUES (?, ?, ?, ?, ?, ?)",
                (ctx.guild.id, case_number, "lockdown_enable", ctx.guild.id, ctx.author.id, reason or "Lockdown enabled")
            )

        msg = f"🔒 Server locked — Case #{case_number}.\nLocked: {', '.join(locked) or 'none'}"
        if failed:
            msg += f"\nFailed: {', '.join(failed)}"
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
            try:
                await channel.set_permissions(everyone, send_messages=None, reason=f"Lockdown lifted: {reason or 'No reason'}")
                unlocked.append(channel.mention)
            except discord.HTTPException:
                failed.append(channel.mention)

        with db.get_db() as conn:
            case_number = conn.execute(
                "SELECT COALESCE(MAX(case_number), 0) + 1 FROM mod_actions WHERE guild_id = ?",
                (ctx.guild.id,)
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO mod_actions (guild_id, case_number, action, target_id, moderator_id, reason) VALUES (?, ?, ?, ?, ?, ?)",
                (ctx.guild.id, case_number, "lockdown_disable", ctx.guild.id, ctx.author.id, reason or "Lockdown lifted")
            )

        msg = f"🔓 Server unlocked — Case #{case_number}.\nUnlocked: {', '.join(unlocked) or 'none'}"
        if failed:
            msg += f"\nFailed: {', '.join(failed)}"
        await ctx.send(msg)

    @lockdown.command(name="status")
    @administrator_check()
    async def lockdown_status(self, ctx):
        with db.get_db() as conn:
            channels = conn.execute(
                "SELECT channel_id FROM lockdown_channels WHERE guild_id = ?", (ctx.guild.id,)
            ).fetchall()

        if not channels:
            await ctx.send("No lockdown channels configured. Use `?lockdown channel add #channel`.")
            return

        everyone = ctx.guild.default_role
        lines = []
        for row in channels:
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
        lines = [f"<#{r['channel_id']}>" for r in rows]
        await ctx.send("Lockdown channels: " + ", ".join(lines))

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("You don't have permission to use lockdown commands.")
        elif isinstance(error, (commands.BadArgument, commands.MissingRequiredArgument)):
            await ctx.send(f"❌ {error}")


async def setup(bot):
    await bot.add_cog(Lockdown(bot))
