import discord
from discord import app_commands
from discord.ext import commands
import db


def _is_mod(member: discord.Member, guild_id: int) -> bool:
    perms = member.guild_permissions
    if perms.administrator or perms.kick_members or perms.ban_members or perms.moderate_members or perms.manage_messages:
        return True
    member_role_ids = {r.id for r in member.roles}
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT role_id FROM staff_roles WHERE guild_id = ? AND role_type IN ('mod', 'admin')",
            (guild_id,)
        ).fetchall()
    return any(row["role_id"] in member_role_ids for row in rows)


def _is_admin(member: discord.Member, guild_id: int) -> bool:
    if member.guild_permissions.administrator:
        return True
    member_role_ids = {r.id for r in member.roles}
    with db.get_db() as conn:
        rows = conn.execute(
            "SELECT role_id FROM staff_roles WHERE guild_id = ? AND role_type = 'admin'",
            (guild_id,)
        ).fetchall()
    return any(row["role_id"] in member_role_ids for row in rows)


# prefix command checks
def moderator_check():
    async def predicate(ctx: commands.Context) -> bool:
        if not isinstance(ctx.author, discord.Member):
            raise commands.CheckFailure("This command can only be used in a server.")
        if not _is_mod(ctx.author, ctx.guild.id):
            raise commands.CheckFailure("You don't have permission to use this command.")
        return True
    return commands.check(predicate)


def administrator_check():
    async def predicate(ctx: commands.Context) -> bool:
        if not isinstance(ctx.author, discord.Member):
            raise commands.CheckFailure("This command can only be used in a server.")
        if not _is_admin(ctx.author, ctx.guild.id):
            raise commands.CheckFailure("You don't have permission to use this command.")
        return True
    return commands.check(predicate)


# slash command checks — replaces @app_commands.default_permissions so staff roles work
async def slash_mod_check(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        raise app_commands.CheckFailure("This command can only be used in a server.")
    if _is_mod(interaction.user, interaction.guild_id):
        return True
    raise app_commands.CheckFailure("You don't have permission to use this command.")


async def slash_admin_check(interaction: discord.Interaction) -> bool:
    if not isinstance(interaction.user, discord.Member):
        raise app_commands.CheckFailure("This command can only be used in a server.")
    if _is_admin(interaction.user, interaction.guild_id):
        return True
    raise app_commands.CheckFailure("You don't have permission to use this command.")