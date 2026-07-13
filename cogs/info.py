import discord
from discord.ext import commands


class Info(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="info", invoke_without_command=True)
    async def info(self, ctx):
        await self.info_server(ctx)

    @info.command(name="server")
    async def info_server(self, ctx):
        guild = ctx.guild
        humans = sum(1 for m in guild.members if not m.bot)
        bots = (guild.member_count or 0) - humans

        embed = discord.Embed(title=guild.name, color=0x5865F2)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        if guild.description:
            embed.description = guild.description

        embed.add_field(name="Owner",        value=f"<@{guild.owner_id}>",       inline=True)
        embed.add_field(name="Members",      value=str(guild.member_count),       inline=True)
        embed.add_field(name="Humans / Bots",value=f"{humans} / {bots}",         inline=True)
        embed.add_field(name="Channels",     value=str(len(guild.channels)),      inline=True)
        embed.add_field(name="Roles",        value=str(len(guild.roles)),         inline=True)
        embed.add_field(name="Boost level",  value=str(guild.premium_tier),       inline=True)
        embed.add_field(name="Created",      value=f"<t:{int(guild.created_at.timestamp())}:R>", inline=True)
        embed.set_footer(text=f"ID: {guild.id}")
        await ctx.send(embed=embed)

    @info.command(name="channel")
    async def info_channel(self, ctx, channel: discord.TextChannel = None):
        target = channel or ctx.channel
        embed = discord.Embed(title=f"#{target.name}", color=0x5865F2)
        embed.add_field(name="ID",       value=str(target.id),                                        inline=True)
        embed.add_field(name="Category", value=target.category.name if target.category else "None",   inline=True)
        embed.add_field(name="Created",  value=f"<t:{int(target.created_at.timestamp())}:R>",         inline=True)
        if target.topic:
            embed.add_field(name="Topic", value=target.topic, inline=False)
        if target.slowmode_delay:
            embed.add_field(name="Slowmode", value=f"{target.slowmode_delay}s", inline=True)
        embed.set_footer(text=f"ID: {target.id}")
        await ctx.send(embed=embed)

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.ChannelNotFound):
            await ctx.send("Channel not found.")


async def setup(bot):
    await bot.add_cog(Info(bot))
