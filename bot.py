import asyncio
import os
import discord
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
    print(f"logged in as {bot.user} ({bot.user.id})")

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
        await bot.start(os.getenv("DISCORD_TOKEN"))

asyncio.run(main())