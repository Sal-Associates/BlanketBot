import discord
from discord.ext import commands

MOD_ACTIONS = [
    ("kick",          "Kick a member"),
    ("ban",           "Ban a member"),
    ("unban",         "Unban a user by ID"),
    ("softban",       "Ban + unban, deletes 7 days of messages"),
    ("mute",          "Mute a member (role-based; duration optional)"),
    ("unmute",        "Unmute a member"),
    ("warn",          "Issue a warning"),
    ("warndel",       "Delete a warning by ID"),
    ("warnings",      "View warnings for a member"),
    ("clearwarnings", "Clear all warnings for a member"),
]

MOD_TOOLS = [
    ("note add",         "Add a staff note"),
    ("note list",        "List notes for a member"),
    ("note edit",        "Edit a note by ID"),
    ("note del",         "Delete a note by ID"),
    ("purge",            "Bulk delete (filters: user, match, links, bots, etc.)"),
    ("channel lock",     "Lock a channel"),
    ("channel unlock",   "Unlock a channel"),
    ("channel slowmode", "Set slowmode in seconds (0 to disable)"),
    ("modlogs",          "Mod history for a user"),
    ("modstats",         "Mod stats for a moderator or server"),
    ("case",             "Look up a specific case by number"),
    ("whois",            "User info + mod history"),
]

INFO_COMMANDS = [
    ("info server",  "Server info (members, roles, boost level, etc.)"),
    ("info channel", "Channel info"),
    ("help",         "Show this message"),
    ("about",        "About this bot"),
]

ADMIN_COMMANDS = [
    ("settings logchannel",              "Set log channel (or `off` to clear)"),
    ("muterole",                         "View current mute role"),
    ("muterole create",                  "Create a Muted role and apply channel permissions"),
    ("muterole set @role",               "Use an existing role as the mute role"),
    ("muterole off",                     "Clear mute role (falls back to Discord timeout)"),
    ("staff mod add/del/list",           "Manage moderator roles"),
    ("staff admin add/del/list",         "Manage admin roles"),
    ("automod on/off",                   "Enable or disable automod"),
    ("automod antispam/anticaps/antiinvite/antimention on/off", "Toggle checks"),
    ("automod word add/del/list",        "Manage banned words"),
    ("automod blacklist/whitelist add/remove/list", "Manage link rules"),
    ("automod ignore channel/role",      "Manage ignore list"),
    ("automod threshold show|reset|caps|spam-count|spam-window|mentions", "Thresholds"),
    ("lockdown enable/disable",          "Lock or unlock configured channels"),
    ("lockdown status",                  "Show channel lock states"),
    ("lockdown channel add/remove/list", "Manage lockdown channels"),
]


def _fmt(rows, show_slash=True):
    lines = []
    for cmd, desc in rows:
        if show_slash:
            lines.append(f"`?{cmd}` / `/{cmd}` — {desc}")
        else:
            lines.append(f"`?{cmd}` — {desc}")
    return "\n".join(lines)


class General(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="help")
    async def help(self, ctx):
        embed = discord.Embed(title="Commands", color=discord.Color.blurple())
        embed.add_field(name="Mod Actions",  value=_fmt(MOD_ACTIONS),                   inline=False)
        embed.add_field(name="Mod Tools",    value=_fmt(MOD_TOOLS),                     inline=False)
        embed.add_field(name="Info",         value=_fmt(INFO_COMMANDS, show_slash=False), inline=False)
        embed.add_field(name="Admin",        value=_fmt(ADMIN_COMMANDS, show_slash=False), inline=False)
        await ctx.send(embed=embed)

    @commands.command(name="about")
    async def about(self, ctx):
        embed = discord.Embed(
            title=f"{self.bot.user.name}",
            description="A moderation and logging bot.",
            color=discord.Color.blurple()
        )
        embed.add_field(name="Prefix",  value="`?`",                  inline=True)
        embed.add_field(name="Slash",   value="`/` for moderation",   inline=True)
        embed.add_field(name="Servers", value=str(len(self.bot.guilds)), inline=True)
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text=f"discord.py {discord.__version__}")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(General(bot))