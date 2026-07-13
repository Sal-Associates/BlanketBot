"""?muterole — configure the server mute role."""

from __future__ import annotations

from discord.ext import commands

from bot.checks.decorators import administrator_required
from bot.cogs.deps import CogRepos
from bot.services.mod_log import get_or_create_mute_role
from bot.utils.helpers import error, info, success
from bot.utils.resolvers import resolve_role


class MuteRoleCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repos = CogRepos(bot)

    @commands.command(name="muterole")
    @administrator_required()
    async def muterole(self, ctx: commands.Context[commands.Bot], *, arg: str | None = None) -> None:
        guild = ctx.guild
        assert guild is not None
        guild_id = str(guild.id)
        settings = await self.repos.guild_settings.get(guild_id)

        if arg is None:
            if settings.mute_role_id:
                role = guild.get_role(int(settings.mute_role_id))
                if role:
                    await ctx.reply(info(f"Mute role: {role} (`{role.id}`)"))
                    return
            role = await get_or_create_mute_role(guild, guild_settings=self.repos.guild_settings)
            await ctx.reply(info(f"Mute role: {role} (`{role.id}`) — auto-created if missing."))
            return

        if arg.lower() == "off":
            await self.repos.guild_settings.update(guild_id, mute_role_id=None)
            await ctx.reply(success("Custom mute role cleared. A new role will be auto-created on next mute."))
            return

        role = resolve_role(guild, arg)
        if role is None:
            await ctx.reply(error("Provide a valid role mention, ID, or `off`."))
            return

        me = guild.me
        if me is None or role.position >= me.top_role.position:
            await ctx.reply(error("That role is above or equal to my highest role — I cannot assign it."))
            return
        if not role.is_assignable():
            await ctx.reply(error("That role cannot be assigned by the bot."))
            return

        await self.repos.guild_settings.update(guild_id, mute_role_id=str(role.id))
        await ctx.reply(success(f"Mute role set to {role}."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MuteRoleCog(bot))
