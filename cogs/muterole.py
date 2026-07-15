import discord
from discord.ext import commands
import db
from checks import administrator_check


class MuteRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_role(self, guild: discord.Guild) -> discord.Role | None:
        settings = db.get_guild_settings(guild.id)
        if not settings or not settings["mute_role_id"]:
            return None
        return guild.get_role(settings["mute_role_id"])

    def _save(self, guild_id: int, role_id: int | None):
        db.ensure_guild_settings(guild_id)
        with db.get_db() as conn:
            conn.execute("UPDATE guild_settings SET mute_role_id = ? WHERE guild_id = ?", (role_id, guild_id))

    @commands.group(name="muterole", invoke_without_command=True)
    @administrator_check()
    async def muterole(self, ctx):
        role = self._get_role(ctx.guild)
        if role:
            await ctx.send(f"Mute role: **{role.name}** (`{role.id}`)\nUse `?muterole set @role`, `?muterole create`, or `?muterole off`.")
        else:
            await ctx.send("No mute role configured. Use `?muterole create` to create one, or `?muterole set @role` to assign an existing role.")

    @muterole.command(name="set")
    @administrator_check()
    async def muterole_set(self, ctx, role: discord.Role):
        if role >= ctx.guild.me.top_role:
            await ctx.send("❌ That role is at or above my highest role. Move it below my role in the hierarchy.")
            return
        self._save(ctx.guild.id, role.id)
        await ctx.send(f"✅ Mute role set to **{role.name}**.")

    @muterole.command(name="create")
    @administrator_check()
    async def muterole_create(self, ctx):
        existing = discord.utils.get(ctx.guild.roles, name="Muted")
        if existing:
            self._save(ctx.guild.id, existing.id)
            await ctx.send(f"✅ Found existing **Muted** role and set it as the mute role.")
            return

        msg = await ctx.send("⏳ Creating **Muted** role and applying channel permissions...")

        try:
            role = await ctx.guild.create_role(name="Muted", reason=f"Mute role created by {ctx.author}")
        except discord.Forbidden:
            await msg.edit(content="❌ I don't have permission to create roles.")
            return

        failed = []
        for channel in ctx.guild.text_channels:
            try:
                await channel.set_permissions(role, send_messages=False, add_reactions=False)
            except discord.Forbidden:
                failed.append(channel.name)

        self._save(ctx.guild.id, role.id)

        applied = len(ctx.guild.text_channels) - len(failed)
        reply = f"✅ Created **Muted** role and applied permissions to {applied} channel(s)."
        if failed:
            reply += f"\n⚠️ Couldn't set permissions in: {', '.join(failed)}"
        await msg.edit(content=reply)

    @muterole.command(name="off")
    @administrator_check()
    async def muterole_off(self, ctx):
        self._save(ctx.guild.id, None)
        await ctx.send("✅ Mute role cleared. Mutes will fall back to Discord timeout.")

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("You don't have permission to configure the mute role.")
        elif isinstance(error, commands.RoleNotFound):
            await ctx.send("Role not found.")


async def setup(bot):
    await bot.add_cog(MuteRole(bot))
