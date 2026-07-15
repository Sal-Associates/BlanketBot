import asyncio
import os
import time
import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv
import db

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.moderation = True

bot = commands.Bot(command_prefix="?", intents=intents, help_command=None)


@bot.event
async def on_ready():
    await bot.tree.sync()
    await _restore_timed_mutes()
    print(f"logged in as {bot.user} ({bot.user.id})")


async def _restore_timed_mutes():
    now = time.time()
    with db.get_db() as conn:
        rows = conn.execute("SELECT * FROM timed_mutes").fetchall()

    for row in rows:
        guild = bot.get_guild(row["guild_id"])
        if not guild:
            continue
        role = guild.get_role(row["role_id"])
        if not role:
            with db.get_db() as conn:
                conn.execute("DELETE FROM timed_mutes WHERE id = ?", (row["id"],))
            continue
        member = guild.get_member(row["user_id"])
        if member is None:
            try:
                member = await guild.fetch_member(row["user_id"])
            except discord.NotFound:
                with db.get_db() as conn:
                    conn.execute("DELETE FROM timed_mutes WHERE id = ?", (row["id"],))
                continue
            except discord.HTTPException:
                continue
        delay = row["expires_at"] - now
        if delay <= 0:
            if role in member.roles:
                try:
                    await member.remove_roles(role, reason="Mute expired (bot restart)")
                except discord.HTTPException:
                    pass
            with db.get_db() as conn:
                conn.execute("DELETE FROM timed_mutes WHERE id = ?", (row["id"],))
        else:
            asyncio.create_task(_auto_unmute(row["id"], member, role, delay))


from utils import auto_unmute as _auto_unmute


@bot.tree.error
async def on_tree_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.CheckFailure):
        msg = str(error) or "You don't have permission to use this command."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    else:
        print(f"Unhandled tree error in {interaction.command}: {error}")
        try:
            await interaction.response.send_message("Something went wrong. Please try again.", ephemeral=True)
        except discord.HTTPException:
            pass


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CheckFailure):
        await ctx.send("You don't have permission to use this command.")
    elif isinstance(error, commands.CommandNotFound):
        pass
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Missing argument: `{error.param.name}`.")
    elif isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Bad argument: {error}")
    else:
        raise error


async def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set. Copy .env.example to .env and fill in your token.")
    db.init_db()
    async with bot:
        for cog in [
            "cogs.general",
            "cogs.settings",
            "cogs.staff",
            "cogs.moderation",
            "cogs.muterole",
            "cogs.mod_log",
            "cogs.modlogs",
            "cogs.notes",
            "cogs.purge",
            "cogs.whois",
            "cogs.info",
            "cogs.channel",
            "cogs.automod",
            "cogs.lockdown",
        ]:
            await bot.load_extension(cog)
        await bot.start(token)


asyncio.run(main())