"""?help — command reference."""

from __future__ import annotations

import discord
from discord.ext import commands

COMMAND_HELP: dict[str, dict[str, str]] = {
    "help": {
        "category": "Info",
        "description": "Show all commands or details for one command.",
        "usage": "?help [command]",
    },
    "info": {
        "category": "Info",
        "description": "Server, user, channel, and avatar info.",
        "usage": "?info server|user|channel|avatar [args]",
    },
    "whois": {
        "category": "Info",
        "description": "User profile with warnings, notes, and recent cases.",
        "usage": "?whois [@user]",
    },
    "prefix": {
        "category": "Admin",
        "description": "View or change the command prefix.",
        "usage": "?prefix [new prefix]",
    },
    "staff": {
        "category": "Admin",
        "description": "Manage moderator and administrator staff roles.",
        "usage": "?staff mod|admin add|remove|list [@role]",
    },
    "module": {
        "category": "Admin",
        "description": "Toggle a server module on or off.",
        "usage": "?module Automod",
    },
    "modules": {
        "category": "Admin",
        "description": "List all modules and their status.",
        "usage": "?modules",
    },
    "modlog": {
        "category": "Admin",
        "description": "Set the live moderation log channel.",
        "usage": "?modlog [#channel]",
    },
    "modqueue": {
        "category": "Admin",
        "description": "Configure the automod review queue.",
        "usage": "?modqueue [#channel] · ?modqueue off · ?modqueue status",
    },
    "strike": {
        "category": "Admin",
        "description": "Configure strike escalation thresholds.",
        "usage": "?strike status|set|on|off",
    },
    "muterole": {
        "category": "Admin",
        "description": "View, set, or clear the server mute role.",
        "usage": "?muterole [@role|off]",
    },
    "mod": {
        "category": "Moderation",
        "description": "Ban, kick, mute, and other moderation actions.",
        "usage": "?mod ban|unban|kick|mute|unmute|softban|deafen|undeafen",
    },
    "warn": {
        "category": "Moderation",
        "description": "Warning system: add, list, remove, and clear.",
        "usage": "?warn add|list|del|clear|view|remove",
    },
    "note": {
        "category": "Moderation",
        "description": "Staff-only notes on users.",
        "usage": "?note add|list|edit|del",
    },
    "case": {
        "category": "Moderation",
        "description": "View moderation cases by number or user.",
        "usage": "?case <number> · ?case list [@user]",
    },
    "channel": {
        "category": "Moderation",
        "description": "Channel lock, unlock, slowmode, and server lockdown.",
        "usage": "?channel lock|unlock|slowmode|lockdown",
    },
    "audit": {
        "category": "Moderation",
        "description": "Discord native audit log entries for a user.",
        "usage": "?audit <user> [limit]",
    },
    "purge": {
        "category": "Moderation",
        "description": "Bulk-delete messages with optional filters.",
        "usage": "?purge [count] or ?purge <filter> [args]",
    },
    "automod": {
        "category": "Automod",
        "description": "Configure auto-moderation rules and thresholds.",
        "usage": "?automod [subcommand]",
    },
}


class HelpCog(commands.Cog):
    @commands.command(name="help")
    async def help_command(self, ctx: commands.Context[commands.Bot], *, query: str | None = None) -> None:
        if query:
            cmd = COMMAND_HELP.get(query.lower())
            if not cmd:
                await ctx.reply(f"Unknown command: `{query}`")
                return
            embed = discord.Embed(
                title=f"?{query.lower()}",
                description=cmd["description"],
                color=0x5865F2,
            )
            embed.add_field(name="Category", value=cmd["category"], inline=True)
            embed.add_field(name="Usage", value=f"`{cmd['usage']}`", inline=False)
            await ctx.reply(embed=embed)
            return

        embed = discord.Embed(
            title="Mod Bot Commands",
            description="Moderation-focused bot. Use `?help [command]` for details.",
            color=0x5865F2,
        )
        categories: dict[str, list[str]] = {}
        for name, meta in COMMAND_HELP.items():
            categories.setdefault(meta["category"], []).append(name)

        for category in sorted(categories):
            embed.add_field(
                name=category,
                value=", ".join(f"`{name}`" for name in sorted(categories[category])),
                inline=False,
            )
        await ctx.reply(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(HelpCog())
