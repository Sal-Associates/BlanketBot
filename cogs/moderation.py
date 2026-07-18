import asyncio
import time
import discord
from discord import app_commands
from discord.ext import commands
from datetime import timedelta
import db
from checks import moderator_check, administrator_check, slash_mod_check, slash_admin_check
from utils import parse_duration, format_duration, role_check, auto_unmute as _auto_unmute


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_mute_role(self, guild: discord.Guild) -> discord.Role | None:
        settings = db.get_guild_settings(guild.id)
        if not settings or not settings["mute_role_id"]:
            return None
        return guild.get_role(settings["mute_role_id"])

    async def _kick(self, actor, member, reason, guild):
        if not role_check(actor, member):
            return False, "You can't kick someone with a higher or equal role."
        try:
            await member.kick(reason=reason)
        except discord.Forbidden:
            return False, "I don't have permission to kick that member."
        self.bot.dispatch("mod_action", "kick", actor, member, reason, guild)
        return True, f"Kicked **{member}**." + (f" Reason: {reason}" if reason else "")

    async def _ban(self, actor, member, reason, guild, delete_days=0):
        if not role_check(actor, member):
            return False, "You can't ban someone with a higher or equal role."
        try:
            await member.ban(
                reason=reason,
                delete_message_seconds=min(max(delete_days, 0), 7) * 86400,
            )
        except discord.Forbidden:
            return False, "I don't have permission to ban that member."
        self.bot.dispatch("mod_action", "ban", actor, member, reason, guild)
        return True, f"Banned **{member}**." + (f" Reason: {reason}" if reason else "")

    async def _unban(self, actor, guild, user_id_str, reason):
        try:
            user = await self.bot.fetch_user(int(user_id_str))
        except (ValueError, discord.NotFound):
            return False, "Couldn't find a user with that ID."
        try:
            await guild.unban(user, reason=reason)
        except discord.NotFound:
            return False, "That user isn't banned."
        except discord.Forbidden:
            return False, "I don't have permission to unban users."
        self.bot.dispatch("mod_action", "unban", actor, user, reason, guild)
        return True, f"Unbanned **{user}**."

    async def _mute(self, actor, member, duration_str, reason, guild):
        if not role_check(actor, member):
            return False, "You can't mute someone with a higher or equal role."
        mute_role = self._get_mute_role(guild)
        td = parse_duration(duration_str) if duration_str else None

        if mute_role:
            if mute_role >= guild.me.top_role:
                return False, "The mute role is above my highest role. Move it below my role in the hierarchy."
            try:
                await member.add_roles(mute_role, reason=reason)
            except discord.Forbidden:
                return False, "I don't have permission to assign the mute role."

            label = format_duration(td) if td else None

            if td:
                expires_at = int(time.time() + td.total_seconds())
                with db.get_db() as conn:
                    conn.execute(
                        "DELETE FROM timed_mutes WHERE guild_id = ? AND user_id = ?",
                        (guild.id, member.id)
                    )
                    mute_id = conn.execute(
                        "INSERT INTO timed_mutes (guild_id, user_id, role_id, expires_at) VALUES (?, ?, ?, ?)",
                        (guild.id, member.id, mute_role.id, expires_at)
                    ).lastrowid
                asyncio.create_task(_auto_unmute(mute_id, member, mute_role, td.total_seconds()))

            self.bot.dispatch("mod_action", "mute", actor, member, reason, guild, label)
            msg = f"Muted **{member}**" + (f" for {label}" if label else " permanently") + "."
            return True, msg + (f" Reason: {reason}" if reason else "")

        if not td:
            return False, "No mute role configured. Run `?muterole create`, or provide a duration to use a temporary Discord timeout."
        if td > timedelta(days=28):
            return False, "Discord timeouts can't exceed 28 days."
        try:
            await member.timeout(td, reason=reason)
        except discord.Forbidden:
            return False, "I don't have permission to timeout that member."
        label = format_duration(td)
        self.bot.dispatch("mod_action", "mute", actor, member, reason, guild, label)
        return True, f"Timed out **{member}** for {label} (no mute role set)." + (f" Reason: {reason}" if reason else "")

    async def _unmute(self, actor, member, guild):
        mute_role = self._get_mute_role(guild)
        actions = []
        if mute_role and mute_role in member.roles:
            try:
                await member.remove_roles(mute_role, reason="Unmuted")
                actions.append("role removed")
            except discord.Forbidden:
                return False, "I don't have permission to remove the mute role."
            with db.get_db() as conn:
                conn.execute("DELETE FROM timed_mutes WHERE guild_id = ? AND user_id = ?", (guild.id, member.id))
        if member.timed_out_until:
            try:
                await member.timeout(None)
                actions.append("timeout cleared")
            except discord.Forbidden:
                pass
        if not actions:
            return False, f"**{member}** doesn't appear to be muted."
        self.bot.dispatch("mod_action", "unmute", actor, member, None, guild)
        return True, f"Unmuted **{member}** ({', '.join(actions)})."

    async def _softban(self, actor, member, reason, guild):
        if not role_check(actor, member):
            return False, "You can't softban someone with a higher or equal role."
        try:
            await member.ban(reason=f"Softban: {reason}", delete_message_seconds=604800)
            await guild.unban(member, reason="Softban complete")
        except discord.Forbidden:
            return False, "I don't have permission to softban that member."
        self.bot.dispatch("mod_action", "softban", actor, member, reason, guild)
        return True, f"Softbanned **{member}** (7 days of messages deleted)." + (f" Reason: {reason}" if reason else "")

    def _warn(self, actor, member, reason, guild):
        if not role_check(actor, member):
            return False, "You can't warn someone with a higher or equal role."
        if reason and len(reason) > 1000:
            reason = reason[:1000]
        with db.get_db() as conn:
            conn.execute(
                "INSERT INTO warnings (guild_id, user_id, reason, moderator_id) VALUES (?, ?, ?, ?)",
                (guild.id, member.id, reason, actor.id)
            )
        self.bot.dispatch("mod_action", "warn", actor, member, reason, guild)
        return True, f"Warned **{member}**: {reason}"

    def _get_warnings_embed(self, member, guild_id):
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT id, reason, moderator_id, created_at FROM warnings "
                "WHERE guild_id = ? AND user_id = ? ORDER BY created_at DESC",
                (guild_id, member.id)
            ).fetchall()
        if not rows:
            return None, f"**{member}** has no warnings."
        lines = [
            f"`#{r['id']}` {r['reason']} — <@{r['moderator_id']}> on {r['created_at'][:10]}"
            for r in rows
        ]
        embed = discord.Embed(title=f"Warnings for {member}", description="\n".join(lines), color=discord.Color.orange())
        return embed, None

    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(member="Who to kick", reason="Reason")
    @app_commands.check(slash_mod_check)
    async def slash_kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        ok, msg = await self._kick(interaction.user, member, reason, interaction.guild)
        await interaction.response.send_message(msg, ephemeral=not ok)

    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(member="Who to ban", reason="Reason", delete_days="Days of messages to delete (0-7)")
    @app_commands.check(slash_mod_check)
    async def slash_ban(self, interaction: discord.Interaction, member: discord.Member, reason: str = None, delete_days: int = 0):
        ok, msg = await self._ban(interaction.user, member, reason, interaction.guild, delete_days)
        await interaction.response.send_message(msg, ephemeral=not ok)

    @app_commands.command(name="unban", description="Unban a user by their ID")
    @app_commands.describe(user_id="User ID to unban", reason="Reason")
    @app_commands.check(slash_mod_check)
    async def slash_unban(self, interaction: discord.Interaction, user_id: str, reason: str = None):
        ok, msg = await self._unban(interaction.user, interaction.guild, user_id, reason)
        await interaction.response.send_message(msg, ephemeral=not ok)

    @app_commands.command(name="mute", description="Mute a member (mute role if configured, otherwise Discord timeout)")
    @app_commands.describe(member="Who to mute", duration="Duration (e.g. 10m, 2h, 1d). Leave empty for permanent.", reason="Reason")
    @app_commands.check(slash_mod_check)
    async def slash_mute(self, interaction: discord.Interaction, member: discord.Member, duration: str = None, reason: str = None):
        ok, msg = await self._mute(interaction.user, member, duration, reason, interaction.guild)
        await interaction.response.send_message(msg, ephemeral=not ok)

    @app_commands.command(name="unmute", description="Unmute a member")
    @app_commands.describe(member="Who to unmute")
    @app_commands.check(slash_mod_check)
    async def slash_unmute(self, interaction: discord.Interaction, member: discord.Member):
        ok, msg = await self._unmute(interaction.user, member, interaction.guild)
        await interaction.response.send_message(msg, ephemeral=not ok)

    @app_commands.command(name="softban", description="Ban + immediately unban (deletes 7 days of messages)")
    @app_commands.describe(member="Who to softban", reason="Reason")
    @app_commands.check(slash_mod_check)
    async def slash_softban(self, interaction: discord.Interaction, member: discord.Member, reason: str = None):
        ok, msg = await self._softban(interaction.user, member, reason, interaction.guild)
        await interaction.response.send_message(msg, ephemeral=not ok)

    @app_commands.command(name="warn", description="Issue a warning to a member")
    @app_commands.describe(member="Who to warn", reason="Reason")
    @app_commands.check(slash_mod_check)
    async def slash_warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        ok, msg = self._warn(interaction.user, member, reason, interaction.guild)
        await interaction.response.send_message(msg, ephemeral=not ok)

    @app_commands.command(name="warndel", description="Delete a warning by ID")
    @app_commands.describe(warning_id="Warning ID (shown in /warnings)")
    @app_commands.check(slash_mod_check)
    async def slash_warndel(self, interaction: discord.Interaction, warning_id: int):
        with db.get_db() as conn:
            row = conn.execute("SELECT id FROM warnings WHERE id = ? AND guild_id = ?", (warning_id, interaction.guild.id)).fetchone()
            if not row:
                await interaction.response.send_message("Warning not found.", ephemeral=True)
                return
            conn.execute("DELETE FROM warnings WHERE id = ?", (warning_id,))
        await interaction.response.send_message(f"Deleted warning `#{warning_id}`.")

    @app_commands.command(name="warnings", description="View warnings for a member")
    @app_commands.describe(member="Who to check")
    @app_commands.check(slash_mod_check)
    async def slash_warnings(self, interaction: discord.Interaction, member: discord.Member):
        embed, plain = self._get_warnings_embed(member, interaction.guild.id)
        if embed:
            await interaction.response.send_message(embed=embed, ephemeral=True)
        else:
            await interaction.response.send_message(plain, ephemeral=True)

    @app_commands.command(name="clearwarnings", description="Clear all warnings for a member")
    @app_commands.describe(member="Who to clear warnings for")
    @app_commands.check(slash_admin_check)
    async def slash_clearwarnings(self, interaction: discord.Interaction, member: discord.Member):
        with db.get_db() as conn:
            conn.execute("DELETE FROM warnings WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, member.id))
        await interaction.response.send_message(f"Cleared all warnings for **{member}**.")

    @commands.command(name="kick")
    @moderator_check()
    async def prefix_kick(self, ctx, member: discord.Member, *, reason=None):
        _, msg = await self._kick(ctx.author, member, reason, ctx.guild)
        await ctx.send(msg)

    @commands.command(name="ban")
    @moderator_check()
    async def prefix_ban(self, ctx, member: discord.Member, *, reason=None):
        _, msg = await self._ban(ctx.author, member, reason, ctx.guild)
        await ctx.send(msg)

    @commands.command(name="unban")
    @moderator_check()
    async def prefix_unban(self, ctx, user_id: str, *, reason=None):
        _, msg = await self._unban(ctx.author, ctx.guild, user_id, reason)
        await ctx.send(msg)

    @commands.command(name="mute")
    @moderator_check()
    async def prefix_mute(self, ctx, member: discord.Member, *, args: str = ""):
        parts = args.split(None, 1)
        if parts and parse_duration(parts[0]) is not None:
            duration, reason = parts[0], parts[1] if len(parts) > 1 else None
        else:
            duration, reason = None, args or None
        _, msg = await self._mute(ctx.author, member, duration, reason, ctx.guild)
        await ctx.send(msg)

    @commands.command(name="unmute")
    @moderator_check()
    async def prefix_unmute(self, ctx, member: discord.Member):
        _, msg = await self._unmute(ctx.author, member, ctx.guild)
        await ctx.send(msg)

    @commands.command(name="softban")
    @moderator_check()
    async def prefix_softban(self, ctx, member: discord.Member, *, reason=None):
        _, msg = await self._softban(ctx.author, member, reason, ctx.guild)
        await ctx.send(msg)

    @commands.command(name="warn")
    @moderator_check()
    async def prefix_warn(self, ctx, member: discord.Member, *, reason: str):
        _, msg = self._warn(ctx.author, member, reason, ctx.guild)
        await ctx.send(msg)

    @commands.command(name="warndel")
    @moderator_check()
    async def prefix_warndel(self, ctx, warning_id: str):
        try:
            parsed = int(warning_id.replace("#", ""))
        except ValueError:
            await ctx.send("❌ Invalid warning ID.")
            return
        with db.get_db() as conn:
            row = conn.execute("SELECT id FROM warnings WHERE id = ? AND guild_id = ?", (parsed, ctx.guild.id)).fetchone()
            if not row:
                await ctx.send("Warning not found.")
                return
            conn.execute("DELETE FROM warnings WHERE id = ?", (parsed,))
        await ctx.send(f"Deleted warning `#{parsed}`.")

    @commands.command(name="warnings")
    @moderator_check()
    async def prefix_warnings(self, ctx, member: discord.Member):
        embed, plain = self._get_warnings_embed(member, ctx.guild.id)
        await ctx.send(embed=embed) if embed else await ctx.send(plain)

    @commands.command(name="clearwarnings")
    @administrator_check()
    async def prefix_clearwarnings(self, ctx, member: discord.Member):
        with db.get_db() as conn:
            conn.execute("DELETE FROM warnings WHERE guild_id = ? AND user_id = ?", (ctx.guild.id, member.id))
        await ctx.send(f"Cleared all warnings for **{member}**.")

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.MemberNotFound):
            await ctx.send("Member not found.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing argument: `{error.param.name}`.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"Bad argument: {error}")


async def setup(bot):
    await bot.add_cog(Moderation(bot))