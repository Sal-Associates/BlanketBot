"""?staff mod|admin add|remove|list — manage staff roles."""

from __future__ import annotations

from discord.ext import commands

from bot.checks.decorators import administrator_required
from bot.cogs.deps import CogRepos
from bot.database.models import StaffRoleType
from bot.utils.helpers import basic_embed, error, success
from bot.utils.resolvers import resolve_role


class StaffCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repos = CogRepos(bot)

    @commands.group(name="staff", invoke_without_command=True)
    @administrator_required()
    async def staff(self, ctx: commands.Context[commands.Bot]) -> None:
        await ctx.reply(error("Usage: `?staff mod|admin add|remove|list [@role]`"))

    @staff.group(name="mod", invoke_without_command=True)
    @administrator_required()
    async def staff_mod(self, ctx: commands.Context[commands.Bot]) -> None:
        await ctx.reply(error("Usage: `?staff mod add|remove|list [@role]`"))

    @staff.group(name="admin", invoke_without_command=True)
    @administrator_required()
    async def staff_admin(self, ctx: commands.Context[commands.Bot]) -> None:
        await ctx.reply(error("Usage: `?staff admin add|remove|list [@role]`"))

    async def _handle_role_action(
        self,
        ctx: commands.Context[commands.Bot],
        *,
        role_type: StaffRoleType,
        action: str,
        role_arg: str | None,
    ) -> None:
        guild_id = str(ctx.guild.id)  # type: ignore[union-attr]
        label = "Moderator" if role_type == StaffRoleType.MODERATOR else "Admin"

        if action in {"list", ""}:
            role_ids = await self.repos.staff_roles.list_roles(guild_id, role_type)
            if not role_ids:
                await ctx.reply(error(f"No {label.lower()} roles configured."))
                return
            roles = [ctx.guild.get_role(int(rid)) for rid in role_ids]  # type: ignore[union-attr]
            lines = [f"• {role}" for role in roles if role is not None]
            await ctx.reply(embed=basic_embed(f"{label} Roles", "\n".join(lines)))
            return

        if action not in {"add", "remove", "del"}:
            await ctx.reply(error(f"Usage: `?staff {role_type.value} add|remove|list [@role]`"))
            return

        role = resolve_role(ctx.guild, role_arg)  # type: ignore[arg-type]
        if role is None:
            await ctx.reply(error(f"Usage: `?staff {role_type.value} add|remove|list [@role]`"))
            return

        if action == "add":
            await self.repos.staff_roles.add_role(guild_id, str(role.id), role_type)
            await ctx.reply(success(f"**{role.name}** is now a {label.lower()} role."))
            return

        await self.repos.staff_roles.remove_role(guild_id, str(role.id), role_type)
        await ctx.reply(success(f"**{role.name}** removed from {label.lower()} roles."))

    @staff_mod.command(name="add")
    @administrator_required()
    async def staff_mod_add(self, ctx: commands.Context[commands.Bot], *, role: str) -> None:
        await self._handle_role_action(ctx, role_type=StaffRoleType.MODERATOR, action="add", role_arg=role)

    @staff_mod.command(name="remove", aliases=["del"])
    @administrator_required()
    async def staff_mod_remove(self, ctx: commands.Context[commands.Bot], *, role: str) -> None:
        await self._handle_role_action(ctx, role_type=StaffRoleType.MODERATOR, action="remove", role_arg=role)

    @staff_mod.command(name="list")
    @administrator_required()
    async def staff_mod_list(self, ctx: commands.Context[commands.Bot]) -> None:
        await self._handle_role_action(ctx, role_type=StaffRoleType.MODERATOR, action="list", role_arg=None)

    @staff_admin.command(name="add")
    @administrator_required()
    async def staff_admin_add(self, ctx: commands.Context[commands.Bot], *, role: str) -> None:
        await self._handle_role_action(ctx, role_type=StaffRoleType.ADMINISTRATOR, action="add", role_arg=role)

    @staff_admin.command(name="remove", aliases=["del"])
    @administrator_required()
    async def staff_admin_remove(self, ctx: commands.Context[commands.Bot], *, role: str) -> None:
        await self._handle_role_action(ctx, role_type=StaffRoleType.ADMINISTRATOR, action="remove", role_arg=role)

    @staff_admin.command(name="list")
    @administrator_required()
    async def staff_admin_list(self, ctx: commands.Context[commands.Bot]) -> None:
        await self._handle_role_action(ctx, role_type=StaffRoleType.ADMINISTRATOR, action="list", role_arg=None)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(StaffCog(bot))
