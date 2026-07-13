import discord
from discord import app_commands
from discord.ext import commands
import db
from checks import administrator_check


class Settings(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.group(name="settings", invoke_without_command=True)
    @administrator_check()
    async def settings(self, ctx):
        row = db.get_guild_settings(ctx.guild.id)
        if not row:
            await ctx.send("No settings configured yet. Use `?settings logchannel #channel` to get started.")
            return

        log_ch = f"<#{row['log_channel']}>" if row["log_channel"] else "Not set"
        automod = "Enabled" if row["automod_enabled"] else "Disabled"

        embed = discord.Embed(title=f"Settings — {ctx.guild.name}", color=discord.Color.blurple())
        embed.add_field(name="Log channel", value=log_ch, inline=True)
        embed.add_field(name="Automod", value=automod, inline=True)
        await ctx.send(embed=embed)

    @settings.command(name="logchannel")
    @administrator_check()
    async def settings_logchannel(self, ctx, channel: discord.TextChannel | str = None):
        if channel == "off" or channel is None:
            db.ensure_guild_settings(ctx.guild.id)
            with db.get_db() as conn:
                conn.execute(
                    "UPDATE guild_settings SET log_channel = NULL WHERE guild_id = ?",
                    (ctx.guild.id,)
                )
            await ctx.send("✅ Log channel cleared.")
            return

        if not isinstance(channel, discord.TextChannel):
            await ctx.send("❌ Usage: `?settings logchannel #channel` or `?settings logchannel off`")
            return

        db.ensure_guild_settings(ctx.guild.id)
        with db.get_db() as conn:
            conn.execute(
                "UPDATE guild_settings SET log_channel = ? WHERE guild_id = ?",
                (channel.id, ctx.guild.id)
            )
        await ctx.send(f"✅ Log channel set to {channel.mention}.")

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("You don't have permission to change settings.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"❌ {error}")


async def setup(bot):
    await bot.add_cog(Settings(bot))
