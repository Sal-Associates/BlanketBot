import discord
from discord.ext import commands
import db
from checks import administrator_check


class Staff(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="staff", invoke_without_command=True)
    @administrator_check()
    async def staff(self, ctx):
        await ctx.send("❌ Usage: `?staff mod|admin add|del|list [@role]`")

    @staff.group(name="mod", invoke_without_command=True)
    @administrator_check()
    async def staff_mod(self, ctx):
        await ctx.send("❌ Usage: `?staff mod add|del|list [@role]`")

    @staff.group(name="admin", invoke_without_command=True)
    @administrator_check()
    async def staff_admin(self, ctx):
        await ctx.send("❌ Usage: `?staff admin add|del|list [@role]`")

    async def _list(self, ctx, role_type: str, label: str):
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT role_id FROM staff_roles WHERE guild_id = ? AND role_type = ?",
                (ctx.guild.id, role_type)
            ).fetchall()
        if not rows:
            await ctx.send(f"No {label} roles configured.")
            return
        roles = [ctx.guild.get_role(row["role_id"]) for row in rows]
        lines = [f"• {r.mention}" if r else f"• ~~deleted role~~" for r in roles]
        embed = discord.Embed(
            title=f"{label.capitalize()} Roles",
            description="\n".join(lines),
            color=discord.Color.blurple()
        )
        await ctx.send(embed=embed)

    async def _add(self, ctx, role: discord.Role, role_type: str, label: str):
        with db.get_db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO staff_roles (guild_id, role_id, role_type) VALUES (?, ?, ?)",
                (ctx.guild.id, role.id, role_type)
            )
        await ctx.send(f"✅ **{role.name}** is now a {label} role.")

    async def _del(self, ctx, role: discord.Role, role_type: str, label: str):
        with db.get_db() as conn:
            conn.execute(
                "DELETE FROM staff_roles WHERE guild_id = ? AND role_id = ? AND role_type = ?",
                (ctx.guild.id, role.id, role_type)
            )
        await ctx.send(f"✅ **{role.name}** removed from {label} roles.")

    @staff_mod.command(name="add")
    @administrator_check()
    async def mod_add(self, ctx, role: discord.Role):
        await self._add(ctx, role, "mod", "moderator")

    @staff_mod.command(name="del", aliases=["remove"])
    @administrator_check()
    async def mod_del(self, ctx, role: discord.Role):
        await self._del(ctx, role, "mod", "moderator")

    @staff_mod.command(name="list")
    @administrator_check()
    async def mod_list(self, ctx):
        await self._list(ctx, "mod", "moderator")

    @staff_admin.command(name="add")
    @administrator_check()
    async def admin_add(self, ctx, role: discord.Role):
        await self._add(ctx, role, "admin", "admin")

    @staff_admin.command(name="del", aliases=["remove"])
    @administrator_check()
    async def admin_del(self, ctx, role: discord.Role):
        await self._del(ctx, role, "admin", "admin")

    @staff_admin.command(name="list")
    @administrator_check()
    async def admin_list(self, ctx):
        await self._list(ctx, "admin", "admin")

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("You don't have permission to manage staff roles.")
        elif isinstance(error, commands.RoleNotFound):
            await ctx.send("Role not found.")
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing argument: `{error.param.name}`.")


async def setup(bot):
    await bot.add_cog(Staff(bot))
