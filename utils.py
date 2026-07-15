import re
import discord
from datetime import timedelta

MENTION_RE = re.compile(r"^<@!?(\d+)>$")
SNOWFLAKE_RE = re.compile(r"^\d{17,20}$")
LINK_RE = re.compile(r"https?://\S+", re.IGNORECASE)
INVITE_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li)|discordapp\.com/invite)/\S+",
    re.IGNORECASE,
)

_DURATION_RE = re.compile(
    r"^(\d+)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours|d|day|days)$",
    re.IGNORECASE,
)


def parse_duration(s: str | None) -> timedelta | None:
    if not s:
        return None
    match = _DURATION_RE.match(s.strip())
    if not match:
        return None
    value, unit = int(match.group(1)), match.group(2).lower()
    if unit.startswith("s"):
        return timedelta(seconds=value)
    if unit.startswith("m"):
        return timedelta(minutes=value)
    if unit.startswith("h"):
        return timedelta(hours=value)
    return timedelta(days=value)


def format_duration(td: timedelta) -> str:
    total = int(td.total_seconds())
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if seconds and not days:
        parts.append(f"{seconds}s")
    return " ".join(parts) or "0s"


def success(msg: str) -> str:
    return f"✅ {msg}"


def error(msg: str) -> str:
    return f"❌ {msg}"


def resolve_member(guild: discord.Guild, value: str | None) -> discord.Member | None:
    if not value:
        return None
    mention = MENTION_RE.match(value.strip())
    if mention:
        return guild.get_member(int(mention.group(1)))
    if SNOWFLAKE_RE.match(value.strip()):
        return guild.get_member(int(value.strip()))
    lowered = value.lower()
    for member in guild.members:
        if member.display_name.lower() == lowered or member.name.lower() == lowered:
            return member
    return None


def role_check(actor: discord.Member, member: discord.Member) -> bool:
    if actor.guild_permissions.administrator:
        return True
    return actor.top_role > member.top_role


async def auto_unmute(mute_id: int, member, role, delay: float):
    """Shared timed-mute expiry logic used by moderation.py and bot.py."""
    import asyncio
    import db
    await asyncio.sleep(delay)
    with db.get_db() as conn:
        row = conn.execute("SELECT id FROM timed_mutes WHERE id = ?", (mute_id,)).fetchone()
        if not row:
            return
        conn.execute("DELETE FROM timed_mutes WHERE id = ?", (mute_id,))
    try:
        await member.remove_roles(role, reason="Mute expired")
    except Exception:
        pass