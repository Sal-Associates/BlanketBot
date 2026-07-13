"""?info — server, user, channel, and avatar info."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.utils.helpers import basic_embed, error
from bot.utils.resolvers import resolve_channel, resolve_member


class InfoCog(commands.Cog):
    @commands.group(name="info", invoke_without_command=True)
    async def info(self, ctx: commands.Context[commands.Bot]) -> None:
        await self.info_server(ctx)

    @info.command(name="server")
    async def info_server(self, ctx: commands.Context[commands.Bot]) -> None:
        guild = ctx.guild
        assert guild is not None
        humans = sum(1 for member in guild.members if not member.bot)
        bots = guild.member_count - humans if guild.member_count else 0
        embed = discord.Embed(title=guild.name, color=0x5865F2)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="Owner", value=f"<@{guild.owner_id}>", inline=True)
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Humans / Bots", value=f"{humans} / {bots}", inline=True)
        embed.add_field(name="Channels", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Boost Level", value=str(guild.premium_tier), inline=True)
        embed.add_field(
            name="Created",
            value=f"<t:{int(guild.created_at.timestamp())}:R>",
            inline=True,
        )
        if guild.description:
            embed.description = guild.description
        await ctx.reply(embed=embed)

    @info.command(name="user")
    async def info_user(self, ctx: commands.Context[commands.Bot], *, user_arg: str | None = None) -> None:
        target = resolve_member(ctx.guild, ctx.message, user_arg)  # type: ignore[arg-type]
        if target is None and isinstance(ctx.author, discord.Member):
            target = ctx.author
        if target is None:
            await ctx.reply(error("Could not resolve that user."))
            return
        user = target
        embed = discord.Embed(title=str(user), color=user.colour.value or 0x5865F2)
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="ID", value=str(user.id), inline=True)
        joined = f"<t:{int(user.joined_at.timestamp())}:R>" if user.joined_at else "Unknown"
        embed.add_field(name="Joined", value=joined, inline=True)
        embed.add_field(name="Created", value=f"<t:{int(user.created_at.timestamp())}:R>", inline=True)
        roles = [role.mention for role in user.roles if role != ctx.guild.default_role]  # type: ignore[union-attr]
        embed.add_field(name="Roles", value=" ".join(roles) or "None", inline=False)
        await ctx.reply(embed=embed)

    @info.command(name="channel")
    async def info_channel(self, ctx: commands.Context[commands.Bot], *, channel_arg: str | None = None) -> None:
        channel = resolve_channel(ctx.guild, channel_arg) or ctx.channel  # type: ignore[arg-type]
        lines = [
            f"**ID:** {channel.id}",
            f"**Type:** {channel.type}",
            f"**Created:** <t:{int(channel.created_at.timestamp())}:R>",
        ]
        if isinstance(channel, discord.TextChannel):
            if channel.topic:
                lines.append(f"**Topic:** {channel.topic}")
            if channel.slowmode_delay:
                lines.append(f"**Slowmode:** {channel.slowmode_delay}s")
        name = getattr(channel, "name", str(channel))
        await ctx.reply(embed=basic_embed(f"#{name}", "\n".join(lines)))

    @info.command(name="avatar")
    async def info_avatar(self, ctx: commands.Context[commands.Bot], *, user_arg: str | None = None) -> None:
        target = resolve_member(ctx.guild, ctx.message, user_arg)  # type: ignore[arg-type]
        if target is None and isinstance(ctx.author, discord.Member):
            target = ctx.author
        if target is None:
            await ctx.reply(error("Could not resolve that user."))
            return
        url = target.display_avatar.replace(size=512).url
        embed = discord.Embed(title=f"{target.display_name}'s avatar")
        embed.set_image(url=url)
        await ctx.reply(content=f"**{target}**'s avatar:", embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(InfoCog())
