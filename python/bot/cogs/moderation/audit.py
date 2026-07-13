"""?audit — Discord native audit log lookup."""

from __future__ import annotations

import discord
from discord.ext import commands

from bot.checks.decorators import moderator_required
from bot.utils.helpers import error
from bot.utils.resolvers import resolve_member

ACTION_NAMES = {
    discord.AuditLogAction.ban: "Ban",
    discord.AuditLogAction.kick: "Kick",
    discord.AuditLogAction.member_update: "Member Update",
    discord.AuditLogAction.member_role_update: "Role Update",
    discord.AuditLogAction.message_delete: "Message Delete",
    discord.AuditLogAction.message_bulk_delete: "Bulk Delete",
    discord.AuditLogAction.channel_create: "Channel Create",
    discord.AuditLogAction.channel_delete: "Channel Delete",
    discord.AuditLogAction.role_create: "Role Create",
    discord.AuditLogAction.role_delete: "Role Delete",
}


class AuditCog(commands.Cog):
    @commands.command(name="audit")
    @moderator_required()
    async def audit(self, ctx: commands.Context[commands.Bot], *, args: str) -> None:
        parts = args.split()
        target = resolve_member(ctx.guild, ctx.message, parts[0])  # type: ignore[arg-type]
        if target is None:
            await ctx.reply(error("Usage: `?audit <user> [limit]`"))
            return
        limit = min(int(parts[1]), 25) if len(parts) > 1 and parts[1].isdigit() else 10
        try:
            logs = await ctx.guild.fetch_audit_logs(limit=100)  # type: ignore[union-attr]
            entries = [
                entry
                for entry in logs.entries
                if (entry.target and getattr(entry.target, "id", None) == target.id)
                or (entry.user and entry.user.id == target.id)
            ][:limit]
        except discord.HTTPException:
            await ctx.reply(error("Could not fetch audit logs. Bot needs **View Audit Log** permission."))
            return

        if not entries:
            await ctx.reply(f"No audit log entries found for **{target.display_name}**.")
            return

        lines = []
        for entry in entries:
            action = ACTION_NAMES.get(entry.action, f"Action {entry.action}")
            executor = entry.user.display_name if entry.user else "Unknown"
            when = f"<t:{int(entry.created_at.timestamp())}:R>"
            reason = f" — {entry.reason}" if entry.reason else ""
            lines.append(f"**{action}** by {executor} {when}{reason}")

        embed = discord.Embed(
            title=f"Audit Log: {target.display_name}",
            description="\n".join(lines),
            color=0x5865F2,
        )
        embed.set_footer(text="Source: Discord native audit log")
        await ctx.reply(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AuditCog())
