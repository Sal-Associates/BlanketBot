import discord
from discord import app_commands
from discord.ext import commands
import db
from checks import moderator_check, administrator_check, slash_mod_check


class MemberRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_role(self, guild: discord.Guild) -> discord.Role | None:
        settings = db.get_guild_settings(guild.id)
        if not settings or not settings["member_role_id"]:
            return None
        return guild.get_role(settings["member_role_id"])

    def _save(self, guild_id: int, role_id: int | None):
        db.ensure_guild_settings(guild_id)
        with db.get_db() as conn:
            conn.execute("UPDATE guild_settings SET member_role_id = ? WHERE guild_id = ?", (role_id, guild_id))

    async def _give(self, actor: discord.Member, member: discord.Member, guild: discord.Guild):
        role = self._get_role(guild)
        if not role:
            return False, "No member role configured. An admin can set one with `?memberrole set @role`."
        if role in member.roles:
            return False, f"**{member}** already has **{role.name}**."
        if role >= guild.me.top_role:
            return False, "The member role is above my highest role. Move it below my role in the hierarchy."
        is_owner = guild.owner_id == actor.id
        if not is_owner and not actor.guild_permissions.administrator and role >= actor.top_role:
            return False, "You can't assign a role at or above your own highest role."
        try:
            await member.add_roles(role, reason=f"Member role assigned by {actor}")
        except discord.Forbidden:
            return False, "I don't have permission to assign that role."
        return True, f"Gave **{role.name}** to **{member}**."

    @app_commands.command(name="memberrole", description="Give a member the configured member role")
    @app_commands.describe(member="Who to give the member role to")
    @app_commands.check(slash_mod_check)
    async def slash_memberrole(self, interaction: discord.Interaction, member: discord.Member):
        ok, msg = await self._give(interaction.user, member, interaction.guild)
        await interaction.response.send_message(msg, ephemeral=not ok)

    @commands.group(name="memberrole", invoke_without_command=True)
    @moderator_check()
    async def memberrole(self, ctx):
        role = self._get_role(ctx.guild)
        if role:
            await ctx.send(f"Member role: **{role.name}** (`{role.id}`)\nUse `?memberrole give @user` to assign it, `?memberrole set @role` to change it, or `?memberrole off` to clear it.")
        else:
            await ctx.send("No member role configured. Use `?memberrole set @role` to choose an existing role.")

    @memberrole.command(name="set")
    @administrator_check()
    async def memberrole_set(self, ctx, role: discord.Role):
        if role == ctx.guild.default_role:
            await ctx.send("❌ `@everyone` can't be used as the member role.")
            return
        if role.managed:
            await ctx.send("❌ That role is managed by an integration and can't be assigned manually.")
            return
        if role >= ctx.guild.me.top_role:
            await ctx.send("❌ That role is at or above my highest role. Move it below my role in the hierarchy.")
            return
        self._save(ctx.guild.id, role.id)
        await ctx.send(f"✅ Member role set to **{role.name}**.")

    @memberrole.command(name="off")
    @administrator_check()
    async def memberrole_off(self, ctx):
        self._save(ctx.guild.id, None)
        await ctx.send("✅ Member role cleared.")

    @memberrole.command(name="give", aliases=["add"])
    @moderator_check()
    async def memberrole_give(self, ctx, member: discord.Member):
        _, msg = await self._give(ctx.author, member, ctx.guild)
        await ctx.send(msg)

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("You don't have permission to use this command.")
        elif isinstance(error, commands.RoleNotFound):
            await ctx.send("Role not found.")
        elif isinstance(error, commands.MemberNotFound):
            await ctx.send("Member not found.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing argument: `{error.param.name}`.")


async def setup(bot):
    await bot.add_cog(MemberRole(bot))