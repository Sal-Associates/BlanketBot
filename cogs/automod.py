import time
import discord
from discord.ext import commands
import db
from checks import _is_mod, administrator_check
from utils import INVITE_RE, LINK_RE

THRESHOLD_RANGES = {
    "caps_threshold":    (50, 100),
    "spam_count":        (3, 20),
    "spam_window":       (1, 60),
    "mention_threshold": (2, 50),
}
THRESHOLD_DEFAULTS = {
    "caps_threshold": 70,
    "spam_count": 5,
    "spam_window": 5,
    "mention_threshold": 5,
}


class Automod(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # (guild_id, user_id) -> (count, first_timestamp)
        self._spam_tracker: dict[tuple[int, int], tuple[int, float]] = {}

    def _prune_spam_tracker(self, now: float, window: int):
        stale = [k for k, (_, first) in self._spam_tracker.items() if now - first > window * 2]
        for k in stale:
            del self._spam_tracker[k]

    def _get_settings(self, guild_id: int):
        return db.get_guild_settings(guild_id)

    def _is_ignored(self, guild_id: int, channel_id: int, role_ids: set[int]) -> bool:
        with db.get_db() as conn:
            if conn.execute(
                "SELECT 1 FROM automod_ignored WHERE guild_id = ? AND type = 'channel' AND target_id = ?",
                (guild_id, channel_id)
            ).fetchone():
                return True
            if role_ids:
                placeholders = ",".join("?" * len(role_ids))
                row = conn.execute(
                    f"SELECT 1 FROM automod_ignored WHERE guild_id = ? AND type = 'role' AND target_id IN ({placeholders})",
                    (guild_id, *role_ids)
                ).fetchone()
                if row:
                    return True
        return False

    def _check_banned_words(self, guild_id: int, content: str) -> str | None:
        lower = content.lower()
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT word, match_mode FROM banned_words WHERE guild_id = ?", (guild_id,)
            ).fetchall()
        for row in rows:
            word = row["word"].lower()
            if row["match_mode"] == "exact":
                if word in lower.split():
                    return f"banned word: `{row['word']}`"
            else:
                if word in lower:
                    return f"banned word: `{row['word']}`"
        return None

    def _check_links(self, guild_id: int, content: str) -> str | None:
        links = LINK_RE.findall(content)
        if not links:
            return None
        with db.get_db() as conn:
            blacklist = [r["link"] for r in conn.execute(
                "SELECT link FROM automod_links WHERE guild_id = ? AND list_type = 'blacklist'", (guild_id,)
            ).fetchall()]
            whitelist = [r["link"] for r in conn.execute(
                "SELECT link FROM automod_links WHERE guild_id = ? AND list_type = 'whitelist'", (guild_id,)
            ).fetchall()]
        if not blacklist:
            return None
        for link in links:
            lower = link.lower()
            if any(w in lower for w in whitelist):
                continue
            if any(b in lower for b in blacklist):
                return "blocked link"
        return None

    def _check_spam(self, guild_id: int, user_id: int, count: int, window: int) -> bool:
        key = (guild_id, user_id)
        now = time.time()
        existing = self._spam_tracker.get(key)
        if existing is None or now - existing[1] > window:
            self._spam_tracker[key] = (1, now)
            if len(self._spam_tracker) % 50 == 0:
                self._prune_spam_tracker(now, window)
            return False
        hits, first = existing[0] + 1, existing[1]
        self._spam_tracker[key] = (hits, first)
        return hits >= count

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        settings = self._get_settings(message.guild.id)
        if not settings or not settings["automod_enabled"]:
            return

        member = message.author
        if not isinstance(member, discord.Member):
            return
        if _is_mod(member, message.guild.id):
            return

        role_ids = {r.id for r in member.roles}
        if self._is_ignored(message.guild.id, message.channel.id, role_ids):
            return

        content = message.content
        reason = None

        reason = self._check_banned_words(message.guild.id, content)

        if not reason and settings["anti_invite"] and INVITE_RE.search(content):
            reason = "Discord invite link"

        if not reason:
            reason = self._check_links(message.guild.id, content)

        if not reason and settings["anti_mention"]:
            mention_count = len(message.mentions) + len(message.role_mentions)
            if message.mention_everyone or mention_count >= settings["mention_threshold"]:
                reason = f"mass mention ({mention_count})"

        if not reason and settings["anti_caps"] and len(content) >= 8:
            letters = [c for c in content if c.isalpha()]
            if letters:
                caps_pct = sum(1 for c in letters if c.isupper()) / len(letters) * 100
                if caps_pct >= settings["caps_threshold"]:
                    reason = f"excessive caps ({int(caps_pct)}%)"

        if not reason and settings["anti_spam"]:
            if self._check_spam(message.guild.id, member.id, settings["spam_count"], settings["spam_window"]):
                reason = "spam"

        if reason:
            try:
                await message.delete()
            except discord.HTTPException:
                pass
            try:
                await message.channel.send(
                    f"{member.mention} Your message was removed for violating server rules.",
                    delete_after=5
                )
            except discord.HTTPException:
                pass

    _ALLOWED_COLUMNS = frozenset({
        'automod_enabled', 'anti_spam', 'anti_caps',
        'anti_invite', 'anti_mention', 'caps_threshold',
        'spam_count', 'spam_window', 'mention_threshold',
    })

    def _toggle(self, guild_id: int, column: str, value: int):
        if column not in self._ALLOWED_COLUMNS:
            raise ValueError(f"Disallowed column: {column}")
        db.ensure_guild_settings(guild_id)
        with db.get_db() as conn:
            conn.execute(f"UPDATE guild_settings SET {column} = ? WHERE guild_id = ?", (value, guild_id))

    @commands.group(name="automod", invoke_without_command=True)
    @administrator_check()
    async def automod(self, ctx):
        settings = db.get_guild_settings(ctx.guild.id)
        if not settings:
            await ctx.send("No settings yet. Run `?automod on` to get started.")
            return

        with db.get_db() as conn:
            words = conn.execute("SELECT COUNT(*) FROM banned_words WHERE guild_id = ?", (ctx.guild.id,)).fetchone()[0]
            blacklist = conn.execute("SELECT COUNT(*) FROM automod_links WHERE guild_id = ? AND list_type = 'blacklist'", (ctx.guild.id,)).fetchone()[0]
            whitelist = conn.execute("SELECT COUNT(*) FROM automod_links WHERE guild_id = ? AND list_type = 'whitelist'", (ctx.guild.id,)).fetchone()[0]
            ignored_ch = conn.execute("SELECT COUNT(*) FROM automod_ignored WHERE guild_id = ? AND type = 'channel'", (ctx.guild.id,)).fetchone()[0]
            ignored_roles = conn.execute("SELECT COUNT(*) FROM automod_ignored WHERE guild_id = ? AND type = 'role'", (ctx.guild.id,)).fetchone()[0]

        def t(val): return "✅ On" if val else "❌ Off"

        embed = discord.Embed(title="Automod Status", color=discord.Color.blurple())
        embed.add_field(name="Automod", value=t(settings["automod_enabled"]), inline=True)
        embed.add_field(name="Anti-spam", value=t(settings["anti_spam"]), inline=True)
        embed.add_field(name="Anti-caps", value=t(settings["anti_caps"]), inline=True)
        embed.add_field(name="Anti-invite", value=t(settings["anti_invite"]), inline=True)
        embed.add_field(name="Anti-mention", value=t(settings["anti_mention"]), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.add_field(name="Banned words", value=str(words), inline=True)
        embed.add_field(name="Link blacklist", value=str(blacklist), inline=True)
        embed.add_field(name="Link whitelist", value=str(whitelist), inline=True)
        embed.add_field(name="Ignored channels", value=str(ignored_ch), inline=True)
        embed.add_field(name="Ignored roles", value=str(ignored_roles), inline=True)
        embed.add_field(name="\u200b", value="\u200b", inline=True)
        embed.set_footer(text="Use ?automod threshold show for threshold details")
        await ctx.send(embed=embed)

    @automod.command(name="on")
    @administrator_check()
    async def automod_on(self, ctx):
        self._toggle(ctx.guild.id, "automod_enabled", 1)
        await ctx.send("✅ Automod enabled.")

    @automod.command(name="off")
    @administrator_check()
    async def automod_off(self, ctx):
        self._toggle(ctx.guild.id, "automod_enabled", 0)
        await ctx.send("✅ Automod disabled.")

    @automod.command(name="antispam")
    @administrator_check()
    async def automod_antispam(self, ctx, state: str):
        val = 1 if state.lower() in ("on", "enable", "true") else 0
        self._toggle(ctx.guild.id, "anti_spam", val)
        await ctx.send(f"✅ Anti-spam {'enabled' if val else 'disabled'}.")

    @automod.command(name="anticaps")
    @administrator_check()
    async def automod_anticaps(self, ctx, state: str):
        val = 1 if state.lower() in ("on", "enable", "true") else 0
        self._toggle(ctx.guild.id, "anti_caps", val)
        await ctx.send(f"✅ Anti-caps {'enabled' if val else 'disabled'}.")

    @automod.command(name="antiinvite")
    @administrator_check()
    async def automod_antiinvite(self, ctx, state: str):
        val = 1 if state.lower() in ("on", "enable", "true") else 0
        self._toggle(ctx.guild.id, "anti_invite", val)
        await ctx.send(f"✅ Anti-invite {'enabled' if val else 'disabled'}.")

    @automod.command(name="antimention")
    @administrator_check()
    async def automod_antimention(self, ctx, state: str):
        val = 1 if state.lower() in ("on", "enable", "true") else 0
        self._toggle(ctx.guild.id, "anti_mention", val)
        await ctx.send(f"✅ Anti-mention {'enabled' if val else 'disabled'}.")

    @automod.group(name="word", invoke_without_command=True)
    @administrator_check()
    async def automod_word(self, ctx):
        await ctx.send("❌ Usage: `?automod word add contains|exact <word,[word,...]>` · `?automod word del <id or text>` · `?automod word list`")

    @automod_word.command(name="add")
    @administrator_check()
    async def word_add(self, ctx, match_mode: str, *, words: str):
        if match_mode not in ("contains", "exact"):
            await ctx.send("❌ Match mode must be `contains` or `exact`.")
            return
        values = [w.strip().lower() for w in words.split(",") if w.strip()]
        if not values:
            await ctx.send("❌ Provide at least one word.")
            return
        added = []
        with db.get_db() as conn:
            for word in values:
                word_id = conn.execute(
                    "INSERT INTO banned_words (guild_id, word, match_mode) VALUES (?, ?, ?)",
                    (ctx.guild.id, word, match_mode)
                ).lastrowid
                added.append(f"`#{word_id}` [{match_mode}] {word}")
        await ctx.send(f"✅ Added {len(added)} banned word(s):\n" + "\n".join(added))

    @automod_word.command(name="del", aliases=["remove"])
    @administrator_check()
    async def word_del(self, ctx, *, value: str):
        cleaned = value.replace("#", "").strip()
        with db.get_db() as conn:
            # try by ID first
            if cleaned.isdigit():
                row = conn.execute(
                    "SELECT id FROM banned_words WHERE id = ? AND guild_id = ?",
                    (int(cleaned), ctx.guild.id)
                ).fetchone()
                if not row:
                    await ctx.send(f"❌ No banned word with ID #{cleaned}.")
                    return
                conn.execute("DELETE FROM banned_words WHERE id = ?", (int(cleaned),))
                await ctx.send(f"✅ Removed banned word #{cleaned}.")
                return

            # try by value
            rows = conn.execute(
                "SELECT id, match_mode FROM banned_words WHERE guild_id = ? AND word = ?",
                (ctx.guild.id, cleaned.lower())
            ).fetchall()
            if not rows:
                await ctx.send(f"❌ No banned word matching `{cleaned}`. Use `?automod word list` to see IDs.")
                return
            if len(rows) > 1:
                matches = ", ".join(f"#{r['id']} ({r['match_mode']})" for r in rows)
                await ctx.send(f"❌ Multiple matches for `{cleaned}`: {matches}. Delete by ID to be specific.")
                return
            conn.execute("DELETE FROM banned_words WHERE id = ?", (rows[0]["id"],))
            await ctx.send(f"✅ Removed [{rows[0]['match_mode']}] `{cleaned}`.")

    @automod_word.command(name="list")
    @administrator_check()
    async def word_list(self, ctx):
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT id, word, match_mode FROM banned_words WHERE guild_id = ? ORDER BY id",
                (ctx.guild.id,)
            ).fetchall()
        if not rows:
            await ctx.send("No banned words configured.")
            return
        lines = [f"`#{r['id']}` [{r['match_mode']}] {r['word']}" for r in rows]
        embed = discord.Embed(title="Banned Words", description="\n".join(lines), color=discord.Color.red())
        await ctx.send(embed=embed)

    @automod.group(name="blacklist", invoke_without_command=True)
    @administrator_check()
    async def automod_blacklist(self, ctx):
        await ctx.send("❌ Usage: `?automod blacklist add|remove|list <link>`")

    @automod_blacklist.command(name="add")
    @administrator_check()
    async def blacklist_add(self, ctx, *, links: str):
        items = [l.strip().lower() for l in links.split(",") if l.strip()]
        with db.get_db() as conn:
            for link in items:
                conn.execute(
                    "INSERT INTO automod_links (guild_id, link, list_type) VALUES (?, ?, 'blacklist')",
                    (ctx.guild.id, link)
                )
        await ctx.send(f"✅ Blacklisted: {', '.join(f'`{i}`' for i in items)}")

    @automod_blacklist.command(name="remove", aliases=["del"])
    @administrator_check()
    async def blacklist_remove(self, ctx, *, link: str):
        with db.get_db() as conn:
            conn.execute(
                "DELETE FROM automod_links WHERE guild_id = ? AND list_type = 'blacklist' AND link = ?",
                (ctx.guild.id, link.strip().lower())
            )
        await ctx.send(f"✅ Removed `{link}` from blacklist.")

    @automod_blacklist.command(name="list")
    @administrator_check()
    async def blacklist_list(self, ctx):
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT link FROM automod_links WHERE guild_id = ? AND list_type = 'blacklist' ORDER BY id",
                (ctx.guild.id,)
            ).fetchall()
        if not rows:
            await ctx.send("No blacklisted links. Links are allowed by default — add entries here to block specific domains.")
            return
        await ctx.send("Blacklisted links:\n" + "\n".join(f"`{r['link']}`" for r in rows))

    @automod.group(name="whitelist", invoke_without_command=True)
    @administrator_check()
    async def automod_whitelist(self, ctx):
        await ctx.send("❌ Usage: `?automod whitelist add|remove|list <link>`")

    @automod_whitelist.command(name="add")
    @administrator_check()
    async def whitelist_add(self, ctx, *, links: str):
        items = [l.strip().lower() for l in links.split(",") if l.strip()]
        with db.get_db() as conn:
            for link in items:
                conn.execute(
                    "INSERT INTO automod_links (guild_id, link, list_type) VALUES (?, ?, 'whitelist')",
                    (ctx.guild.id, link)
                )
        await ctx.send(f"✅ Whitelisted: {', '.join(f'`{i}`' for i in items)}")

    @automod_whitelist.command(name="remove", aliases=["del"])
    @administrator_check()
    async def whitelist_remove(self, ctx, *, link: str):
        with db.get_db() as conn:
            conn.execute(
                "DELETE FROM automod_links WHERE guild_id = ? AND list_type = 'whitelist' AND link = ?",
                (ctx.guild.id, link.strip().lower())
            )
        await ctx.send(f"✅ Removed `{link}` from whitelist.")

    @automod_whitelist.command(name="list")
    @administrator_check()
    async def whitelist_list(self, ctx):
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT link FROM automod_links WHERE guild_id = ? AND list_type = 'whitelist' ORDER BY id",
                (ctx.guild.id,)
            ).fetchall()
        if not rows:
            await ctx.send("No whitelisted links.")
            return
        await ctx.send("Whitelisted links:\n" + "\n".join(f"`{r['link']}`" for r in rows))

    @automod.group(name="ignore", invoke_without_command=True)
    @administrator_check()
    async def automod_ignore(self, ctx):
        await ctx.send("❌ Usage: `?automod ignore channel|role add|remove|list`")

    @automod_ignore.group(name="channel", invoke_without_command=True)
    @administrator_check()
    async def ignore_channel(self, ctx):
        await ctx.send("❌ Usage: `?automod ignore channel add|remove|list [#channel]`")

    @ignore_channel.command(name="add")
    @administrator_check()
    async def ignore_channel_add(self, ctx, channel: discord.TextChannel):
        with db.get_db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO automod_ignored (guild_id, type, target_id) VALUES (?, 'channel', ?)",
                (ctx.guild.id, channel.id)
            )
        await ctx.send(f"✅ {channel.mention} added to automod ignore list.")

    @ignore_channel.command(name="remove", aliases=["del"])
    @administrator_check()
    async def ignore_channel_remove(self, ctx, channel: discord.TextChannel):
        with db.get_db() as conn:
            conn.execute(
                "DELETE FROM automod_ignored WHERE guild_id = ? AND type = 'channel' AND target_id = ?",
                (ctx.guild.id, channel.id)
            )
        await ctx.send(f"✅ {channel.mention} removed from automod ignore list.")

    @ignore_channel.command(name="list")
    @administrator_check()
    async def ignore_channel_list(self, ctx):
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT target_id FROM automod_ignored WHERE guild_id = ? AND type = 'channel'",
                (ctx.guild.id,)
            ).fetchall()
        if not rows:
            await ctx.send("No ignored channels.")
            return
        await ctx.send("Ignored channels: " + ", ".join(f"<#{r['target_id']}>" for r in rows))

    @automod_ignore.group(name="role", invoke_without_command=True)
    @administrator_check()
    async def ignore_role(self, ctx):
        await ctx.send("❌ Usage: `?automod ignore role add|remove|list [@role]`")

    @ignore_role.command(name="add")
    @administrator_check()
    async def ignore_role_add(self, ctx, role: discord.Role):
        if role == ctx.guild.default_role:
            await ctx.send("❌ `@everyone` cannot be ignored — it would disable automod for the whole server.")
            return
        with db.get_db() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO automod_ignored (guild_id, type, target_id) VALUES (?, 'role', ?)",
                (ctx.guild.id, role.id)
            )
        await ctx.send(f"✅ **{role.name}** added to automod ignore list.")

    @ignore_role.command(name="remove", aliases=["del"])
    @administrator_check()
    async def ignore_role_remove(self, ctx, role: discord.Role):
        with db.get_db() as conn:
            conn.execute(
                "DELETE FROM automod_ignored WHERE guild_id = ? AND type = 'role' AND target_id = ?",
                (ctx.guild.id, role.id)
            )
        await ctx.send(f"✅ **{role.name}** removed from automod ignore list.")

    @ignore_role.command(name="list")
    @administrator_check()
    async def ignore_role_list(self, ctx):
        with db.get_db() as conn:
            rows = conn.execute(
                "SELECT target_id FROM automod_ignored WHERE guild_id = ? AND type = 'role'",
                (ctx.guild.id,)
            ).fetchall()
        if not rows:
            await ctx.send("No ignored roles.")
            return
        await ctx.send("Ignored roles: " + ", ".join(f"<@&{r['target_id']}>" for r in rows))

    @automod.command(name="ignored")
    @administrator_check()
    async def automod_ignored(self, ctx):
        with db.get_db() as conn:
            channels = conn.execute(
                "SELECT target_id FROM automod_ignored WHERE guild_id = ? AND type = 'channel'", (ctx.guild.id,)
            ).fetchall()
            roles = conn.execute(
                "SELECT target_id FROM automod_ignored WHERE guild_id = ? AND type = 'role'", (ctx.guild.id,)
            ).fetchall()
        ch_lines = [f"<#{r['target_id']}>" for r in channels] or ["None"]
        role_lines = [f"<@&{r['target_id']}>" for r in roles] or ["None"]
        embed = discord.Embed(title="Automod Ignored", color=discord.Color.blurple())
        embed.add_field(name=f"Channels ({len(channels)})", value="\n".join(ch_lines), inline=True)
        embed.add_field(name=f"Roles ({len(roles)})", value="\n".join(role_lines), inline=True)
        await ctx.send(embed=embed)

    @automod.group(name="threshold", invoke_without_command=True)
    @administrator_check()
    async def threshold(self, ctx):
        await ctx.send("❌ Usage: `?automod threshold show|reset|spam-count|spam-window|caps|mentions`")

    @threshold.command(name="show")
    @administrator_check()
    async def threshold_show(self, ctx):
        s = db.get_guild_settings(ctx.guild.id)
        if not s:
            await ctx.send("No settings configured yet.")
            return
        embed = discord.Embed(title="Automod Thresholds", color=discord.Color.blurple())
        embed.add_field(
            name="Spam",
            value=f"{s['spam_count']} messages within {s['spam_window']}s — anti-spam {'✅' if s['anti_spam'] else '❌'}",
            inline=False
        )
        embed.add_field(
            name="Caps",
            value=f"{s['caps_threshold']}% at 8+ letters — anti-caps {'✅' if s['anti_caps'] else '❌'}",
            inline=False
        )
        embed.add_field(
            name="Mentions",
            value=f"{s['mention_threshold']} user/role mentions (@everyone/@here always flagged) — anti-mention {'✅' if s['anti_mention'] else '❌'}",
            inline=False
        )
        await ctx.send(embed=embed)

    @threshold.command(name="reset")
    @administrator_check()
    async def threshold_reset(self, ctx, target: str):
        updates = {}
        if target == "caps":
            updates = {"caps_threshold": THRESHOLD_DEFAULTS["caps_threshold"]}
        elif target == "spam":
            updates = {"spam_count": THRESHOLD_DEFAULTS["spam_count"], "spam_window": THRESHOLD_DEFAULTS["spam_window"]}
        elif target == "mentions":
            updates = {"mention_threshold": THRESHOLD_DEFAULTS["mention_threshold"]}
        elif target == "all":
            updates = dict(THRESHOLD_DEFAULTS)
        else:
            await ctx.send("❌ Usage: `?automod threshold reset caps|spam|mentions|all`")
            return
        db.ensure_guild_settings(ctx.guild.id)
        with db.get_db() as conn:
            for col, val in updates.items():
                conn.execute(f"UPDATE guild_settings SET {col} = ? WHERE guild_id = ?", (val, ctx.guild.id))
        await ctx.send(f"✅ Reset **{target}** threshold(s) to defaults.")

    def _set_threshold(self, guild_id, column, value, min_val, max_val):
        if column not in self._ALLOWED_COLUMNS:
            raise ValueError(f"Disallowed column: {column}")
        if not (min_val <= value <= max_val):
            return False, f"Must be between {min_val} and {max_val}."
        db.ensure_guild_settings(guild_id)
        with db.get_db() as conn:
            conn.execute(f"UPDATE guild_settings SET {column} = ? WHERE guild_id = ?", (value, guild_id))
        return True, None

    @threshold.command(name="spam-count")
    @administrator_check()
    async def threshold_spam_count(self, ctx, count: int):
        ok, err = self._set_threshold(ctx.guild.id, "spam_count", count, *THRESHOLD_RANGES["spam_count"])
        await ctx.send(f"✅ Spam count set to {count} messages." if ok else f"❌ {err}")

    @threshold.command(name="spam-window")
    @administrator_check()
    async def threshold_spam_window(self, ctx, seconds: int):
        ok, err = self._set_threshold(ctx.guild.id, "spam_window", seconds, *THRESHOLD_RANGES["spam_window"])
        await ctx.send(f"✅ Spam window set to {seconds}s." if ok else f"❌ {err}")

    @threshold.command(name="caps")
    @administrator_check()
    async def threshold_caps(self, ctx, percent: int):
        ok, err = self._set_threshold(ctx.guild.id, "caps_threshold", percent, *THRESHOLD_RANGES["caps_threshold"])
        await ctx.send(f"✅ Caps threshold set to {percent}%." if ok else f"❌ {err}")

    @threshold.command(name="mentions")
    @administrator_check()
    async def threshold_mentions(self, ctx, count: int):
        ok, err = self._set_threshold(ctx.guild.id, "mention_threshold", count, *THRESHOLD_RANGES["mention_threshold"])
        await ctx.send(f"✅ Mention threshold set to {count}." if ok else f"❌ {err}")

    async def cog_command_error(self, ctx, error):
        if isinstance(error, commands.CheckFailure):
            await ctx.send("You don't have permission to configure automod.")
        elif isinstance(error, (commands.MissingRequiredArgument, commands.BadArgument)):
            await ctx.send(f"❌ {error}")


async def setup(bot):
    await bot.add_cog(Automod(bot))