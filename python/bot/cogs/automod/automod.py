"""?automod — auto-moderation configuration."""

from __future__ import annotations

from discord.ext import commands

from bot.checks.decorators import administrator_required
from bot.cogs.deps import CogRepos
from bot.database.models import BannedWordMatchMode
from bot.database.repositories.automod import AutomodLinkListType
from bot.errors import DatabaseError
from bot.utils.automod_ignore import (
    format_ignored_channel_line,
    format_ignored_role_line,
    is_automod_eligible_channel,
    resolve_channel_target,
    resolve_role_target,
)
from bot.utils.automod_thresholds import (
    format_threshold_show,
    get_threshold_reset_updates,
    validate_caps_threshold_input,
    validate_mention_threshold_input,
    validate_spam_count_input,
    validate_spam_window_input,
)
from bot.utils.helpers import basic_embed, chunk_lines, error, success

LIST_CHUNK_SIZE = 20
CANONICAL_IGNORE_HINT = "Canonical syntax: `?automod ignore channel|role add|remove|list`"


class AutomodCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repos = CogRepos(bot)

    async def _send_chunked(self, ctx: commands.Context, title: str, lines: list[str]) -> None:
        if not lines:
            await ctx.reply(error(f"No {title.lower()} configured."))
            return
        chunks = chunk_lines(lines, max_len=1900)
        for index, chunk in enumerate(chunks):
            chunk_title = f"{title} ({index + 1}/{len(chunks)})" if len(chunks) > 1 else title
            if index == 0:
                await ctx.reply(embed=basic_embed(chunk_title, chunk))
            else:
                await ctx.channel.send(embed=basic_embed(chunk_title, chunk))  # type: ignore[union-attr]

    async def _add_banned_words(self, ctx: commands.Context, mode: str, raw_values: str) -> None:
        values = [part.strip() for part in raw_values.split(",") if part.strip()]
        if not values:
            await ctx.reply(error("Provide at least one word or phrase."))
            return
        try:
            match_mode = BannedWordMatchMode(mode.lower())
        except ValueError:
            await ctx.reply(error("Match mode must be `contains` or `exact`."))
            return

        added: list[str] = []
        guild_id = str(ctx.guild.id)  # type: ignore[union-attr]
        for value in values:
            try:
                entry_id = await self.repos.banned_words.add(
                    guild_id,
                    value,
                    match_mode,
                    created_by=str(ctx.author.id),
                )
                added.append(f"#{entry_id} [{match_mode.value}] {value.strip().lower()}")
            except DatabaseError as exc:
                if str(exc) == "duplicate_banned_word":
                    await ctx.reply(
                        error(
                            f"Duplicate entry: `{value.strip().lower()}` already exists in "
                            f"**{match_mode.value}** mode.",
                        ),
                    )
                    return
                if str(exc) == "Banned word value cannot be empty":
                    await ctx.reply(error("Word value cannot be empty."))
                    return
                raise

        hint = "Use `?automod word list` to view entries. Legacy `?automod banword` / `banexact` still work."
        await ctx.reply(
            success(f"Added banned word{'s' if len(added) > 1 else ''}:\n" + "\n".join(added) + f"\n_{hint}_"),
        )

    async def _remove_banned_word(self, ctx: commands.Context, rest: str) -> None:
        trimmed = rest.strip()
        if not trimmed:
            await ctx.reply(error("Usage: `?automod word remove <entry-id>`"))
            return

        guild_id = str(ctx.guild.id)  # type: ignore[union-attr]
        if trimmed.isdigit():
            entry_id = int(trimmed)
            if not await self.repos.banned_words.remove(guild_id, entry_id):
                await ctx.reply(error(f"Banned word #{entry_id} was not found."))
                return
            await ctx.reply(success(f"Removed banned word #{entry_id}."))
            return

        parts = trimmed.split()
        maybe_mode = parts[-1].lower() if parts else ""
        mode = BannedWordMatchMode.CONTAINS
        value = trimmed
        try:
            parsed_mode = BannedWordMatchMode(maybe_mode)
            if len(parts) > 1:
                mode = parsed_mode
                value = " ".join(parts[:-1])
        except ValueError:
            pass

        matches = [
            entry
            for entry in await self.repos.banned_words.list_for_guild(guild_id)
            if entry.value == value.strip().lower()
        ]
        if len(matches) > 1 and maybe_mode not in {m.value for m in BannedWordMatchMode}:
            await ctx.reply(
                error(
                    "That word exists in multiple modes. Remove by ID, or specify mode: "
                    "`?automod word remove <text> contains|exact`.",
                ),
            )
            return

        if not await self.repos.banned_words.remove_by_value(guild_id, value, mode):
            await ctx.reply(
                error(f"No **{mode.value}** banned word matching `{value.strip().lower()}` was found."),
            )
            return
        await ctx.reply(
            success(
                f"Removed **{mode.value}** banned word `{value.strip().lower()}`. "
                "Prefer `?automod word remove <id>` for unambiguous removal.",
            ),
        )

    @commands.group(name="automod", invoke_without_command=True)
    @administrator_required()
    async def automod(self, ctx: commands.Context[commands.Bot]) -> None:
        await self.automod_status(ctx)

    @automod.command(name="status")
    @administrator_required()
    async def automod_status(self, ctx: commands.Context[commands.Bot]) -> None:
        guild_id = str(ctx.guild.id)  # type: ignore[union-attr]
        settings = await self.repos.guild_settings.get(guild_id)
        module_disabled = await self.repos.guild_settings.is_module_disabled(guild_id, "Automod")
        words = await self.repos.banned_words.list_for_guild(guild_id)
        blacklist = await self.repos.automod.list_links(guild_id, AutomodLinkListType.BLACKLIST)
        ignored_channels = await self.repos.automod.list_ignored_channels(guild_id)
        ignored_roles = await self.repos.automod.list_ignored_roles(guild_id)
        inactive = " (inactive)" if module_disabled else ""
        body = "\n".join(
            [
                f"**Master status:** {'Disabled' if module_disabled else 'Enabled'}",
                "_Individual protections are inactive while the Automod module is disabled._"
                if module_disabled
                else "",
                f"**Anti-spam:** {'On' if settings.anti_spam else 'Off'}{inactive}",
                f"**Anti-caps:** {'On' if settings.anti_caps else 'Off'}{inactive}",
                f"**Anti-invite:** {'On' if settings.anti_invite else 'Off'}{inactive}",
                f"**Anti-mention:** {'On' if settings.anti_mention else 'Off'}{inactive}",
                f"**Banned words:** {len(words)}{inactive}",
                f"**Blacklisted links:** {len(blacklist)}{inactive}",
                f"**Ignored channels:** {len(ignored_channels)} — `?automod ignore channel list`",
                f"**Ignored roles:** {len(ignored_roles)} — `?automod ignore role list`",
                "**Thresholds:** `?automod threshold show`",
            ],
        )
        await ctx.reply(embed=basic_embed("Automod Status", body))

    @automod.group(name="word", invoke_without_command=True)
    @administrator_required()
    async def automod_word(self, ctx: commands.Context[commands.Bot]) -> None:
        await ctx.reply(error("Usage: `?automod word add|remove|list`"))

    @automod_word.command(name="add")
    @administrator_required()
    async def automod_word_add(self, ctx: commands.Context[commands.Bot], mode: str, *, text: str) -> None:
        if not text.strip():
            await ctx.reply(error("Usage: `?automod word add contains|exact <text>`"))
            return
        await self._add_banned_words(ctx, mode, text)

    @automod_word.command(name="remove")
    @administrator_required()
    async def automod_word_remove(self, ctx: commands.Context[commands.Bot], *, rest: str) -> None:
        await self._remove_banned_word(ctx, rest)

    @automod_word.command(name="list")
    @administrator_required()
    async def automod_word_list(self, ctx: commands.Context[commands.Bot]) -> None:
        words = await self.repos.banned_words.list_for_guild(str(ctx.guild.id))  # type: ignore[union-attr]
        lines = [
            f"**#{entry.id}** [`{entry.match_mode.value}`] {entry.value}"
            for entry in sorted(words, key=lambda item: item.id)
        ]
        await self._send_chunked(ctx, "Banned Words", lines)

    @automod.command(name="banword")
    @administrator_required()
    async def automod_banword(self, ctx: commands.Context[commands.Bot], *, values: str) -> None:
        await self._add_banned_words(ctx, "contains", values)

    @automod.command(name="banexact")
    @administrator_required()
    async def automod_banexact(self, ctx: commands.Context[commands.Bot], *, value: str) -> None:
        await self._add_banned_words(ctx, "exact", value)

    @automod.command(name="unbanword")
    @administrator_required()
    async def automod_unbanword(self, ctx: commands.Context[commands.Bot], *, rest: str) -> None:
        await self._remove_banned_word(ctx, rest)

    @automod.command(name="blacklist")
    @administrator_required()
    async def automod_blacklist(self, ctx: commands.Context[commands.Bot], *, links: str) -> None:
        guild_id = str(ctx.guild.id)  # type: ignore[union-attr]
        items = [part.strip() for part in links.split(",") if part.strip()]
        for link in items:
            await self.repos.automod.add_link(guild_id, link, AutomodLinkListType.BLACKLIST)
        await ctx.reply(success(f"Blacklisted links: {', '.join(items)}"))

    @automod.command(name="whitelist")
    @administrator_required()
    async def automod_whitelist(self, ctx: commands.Context[commands.Bot], *, links: str) -> None:
        guild_id = str(ctx.guild.id)  # type: ignore[union-attr]
        items = [part.strip() for part in links.split(",") if part.strip()]
        for link in items:
            await self.repos.automod.add_link(guild_id, link, AutomodLinkListType.WHITELIST)
        await ctx.reply(success(f"Whitelisted links: {', '.join(items)}"))

    async def _add_ignored_channel(self, ctx: commands.Context, arg: str, *, legacy: bool = False) -> None:
        target = resolve_channel_target(ctx.guild, arg)  # type: ignore[arg-type]
        if target is None:
            await ctx.reply(error("Provide a valid channel mention or ID from this server."))
            return
        channel_id, channel = target
        if channel and not is_automod_eligible_channel(channel):
            await ctx.reply(error("That channel type is not eligible for Automod message checks."))
            return
        try:
            await self.repos.automod.add_ignored_channel(str(ctx.guild.id), channel_id)  # type: ignore[union-attr]
        except DatabaseError:
            label = channel or f"channel `{channel_id}`"
            await ctx.reply(error(f"{label} is already in the ignored channel list."))
            return
        suffix = f"\n_{CANONICAL_IGNORE_HINT}_" if legacy else ""
        label = channel or f"channel `{channel_id}`"
        await ctx.reply(success(f"Automod will ignore {label} (`{channel_id}`).{suffix}"))

    async def _add_ignored_role(self, ctx: commands.Context, arg: str, *, legacy: bool = False) -> None:
        target = resolve_role_target(ctx.guild, arg)  # type: ignore[arg-type]
        if target is None:
            await ctx.reply(error("Provide a valid role mention or ID from this server."))
            return
        role_id, role = target
        if role_id == str(ctx.guild.default_role.id):  # type: ignore[union-attr]
            await ctx.reply(error("`@everyone` cannot be added — it would disable Automod for the entire server."))
            return
        try:
            await self.repos.automod.add_ignored_role(str(ctx.guild.id), role_id)  # type: ignore[union-attr]
        except DatabaseError:
            await ctx.reply(error(f"Role **{role.name}** is already in the ignored role list."))  # type: ignore[union-attr]
            return
        suffix = f"\n_{CANONICAL_IGNORE_HINT}_" if legacy else ""
        label = f"**{role.name}**" if role else f"role `{role_id}`"
        await ctx.reply(success(f"Automod will ignore role {label} (`{role_id}`).{suffix}"))

    @automod.group(name="ignore", invoke_without_command=True)
    @administrator_required()
    async def automod_ignore(self, ctx: commands.Context[commands.Bot]) -> None:
        await ctx.reply(error("Usage: `?automod ignore channel|role add|remove|list`"))

    @automod_ignore.group(name="channel", invoke_without_command=True)
    @administrator_required()
    async def automod_ignore_channel(self, ctx: commands.Context[commands.Bot]) -> None:
        await ctx.reply(error("Usage: `?automod ignore channel add|remove|list`"))

    @automod_ignore_channel.command(name="add")
    @administrator_required()
    async def automod_ignore_channel_add(self, ctx: commands.Context[commands.Bot], *, arg: str) -> None:
        await self._add_ignored_channel(ctx, arg)

    @automod_ignore_channel.command(name="remove")
    @administrator_required()
    async def automod_ignore_channel_remove(self, ctx: commands.Context[commands.Bot], *, arg: str) -> None:
        target = resolve_channel_target(ctx.guild, arg)  # type: ignore[arg-type]
        if target is None:
            await ctx.reply(error("Usage: `?automod ignore channel remove #channel` or provide a channel ID."))
            return
        channel_id, channel = target
        if not await self.repos.automod.remove_ignored_channel(str(ctx.guild.id), channel_id):  # type: ignore[union-attr]
            await ctx.reply(error(f"Channel `{channel_id}` is not in the ignored channel list."))
            return
        label = channel or f"channel `{channel_id}`"
        await ctx.reply(success(f"Removed {label} from ignored channels."))

    @automod_ignore_channel.command(name="list")
    @administrator_required()
    async def automod_ignore_channel_list(self, ctx: commands.Context[commands.Bot]) -> None:
        channel_ids = await self.repos.automod.list_ignored_channels(str(ctx.guild.id))  # type: ignore[union-attr]
        lines = [format_ignored_channel_line(ctx.guild, channel_id) for channel_id in channel_ids]  # type: ignore[arg-type]
        await self._send_chunked(ctx, "Ignored Channels", lines)

    @automod_ignore.group(name="role", invoke_without_command=True)
    @administrator_required()
    async def automod_ignore_role(self, ctx: commands.Context[commands.Bot]) -> None:
        await ctx.reply(error("Usage: `?automod ignore role add|remove|list`"))

    @automod_ignore_role.command(name="add")
    @administrator_required()
    async def automod_ignore_role_add(self, ctx: commands.Context[commands.Bot], *, arg: str) -> None:
        await self._add_ignored_role(ctx, arg)

    @automod_ignore_role.command(name="remove")
    @administrator_required()
    async def automod_ignore_role_remove(self, ctx: commands.Context[commands.Bot], *, arg: str) -> None:
        target = resolve_role_target(ctx.guild, arg)  # type: ignore[arg-type]
        if target is None:
            await ctx.reply(error("Usage: `?automod ignore role remove @role` or provide a role ID."))
            return
        role_id, role = target
        if not await self.repos.automod.remove_ignored_role(str(ctx.guild.id), role_id):  # type: ignore[union-attr]
            await ctx.reply(error(f"Role `{role_id}` is not in the ignored role list."))
            return
        label = f"**{role.name}**" if role else f"role `{role_id}`"
        await ctx.reply(success(f"Removed {label} from ignored roles."))

    @automod_ignore_role.command(name="list")
    @administrator_required()
    async def automod_ignore_role_list(self, ctx: commands.Context[commands.Bot]) -> None:
        role_ids = await self.repos.automod.list_ignored_roles(str(ctx.guild.id))  # type: ignore[union-attr]
        lines = [format_ignored_role_line(ctx.guild, role_id) for role_id in role_ids]  # type: ignore[arg-type]
        await self._send_chunked(ctx, "Ignored Roles", lines)

    @automod.command(name="ignorechannel")
    @administrator_required()
    async def automod_ignorechannel(self, ctx: commands.Context[commands.Bot], *, arg: str) -> None:
        await self._add_ignored_channel(ctx, arg, legacy=True)

    @automod.command(name="ignorerole")
    @administrator_required()
    async def automod_ignorerole(self, ctx: commands.Context[commands.Bot], *, arg: str) -> None:
        await self._add_ignored_role(ctx, arg, legacy=True)

    @automod.command(name="ignored")
    @administrator_required()
    async def automod_ignored(self, ctx: commands.Context[commands.Bot]) -> None:
        guild_id = str(ctx.guild.id)  # type: ignore[union-attr]
        channel_ids = await self.repos.automod.list_ignored_channels(guild_id)
        role_ids = await self.repos.automod.list_ignored_roles(guild_id)
        channel_lines = [format_ignored_channel_line(ctx.guild, cid) for cid in channel_ids]  # type: ignore[arg-type]
        role_lines = [format_ignored_role_line(ctx.guild, rid) for rid in role_ids]  # type: ignore[arg-type]
        body = "\n".join(
            [
                f"**Channels ({len(channel_ids)}):**",
                "\n".join(channel_lines) if channel_lines else "None",
                "",
                f"**Roles ({len(role_ids)}):**",
                "\n".join(role_lines) if role_lines else "None",
                "",
                "_Use `?automod ignore channel list` or `?automod ignore role list` for paginated output._",
            ],
        )
        await ctx.reply(embed=basic_embed("Automod Ignored", body))

    @automod.group(name="threshold", invoke_without_command=True)
    @administrator_required()
    async def automod_threshold(self, ctx: commands.Context[commands.Bot]) -> None:
        await ctx.reply(error("Usage: `?automod threshold caps|spam-count|spam-window|mentions|show|reset`"))

    @automod_threshold.command(name="show")
    @administrator_required()
    async def automod_threshold_show(self, ctx: commands.Context[commands.Bot]) -> None:
        guild_id = str(ctx.guild.id)  # type: ignore[union-attr]
        settings = await self.repos.guild_settings.get(guild_id)
        module_disabled = await self.repos.guild_settings.is_module_disabled(guild_id, "Automod")
        await ctx.reply(
            embed=basic_embed(
                "Automod Thresholds",
                format_threshold_show(settings, module_disabled=module_disabled),
            ),
        )

    @automod_threshold.command(name="reset")
    @administrator_required()
    async def automod_threshold_reset(self, ctx: commands.Context[commands.Bot], target: str) -> None:
        updates = get_threshold_reset_updates(target)
        if not updates:
            await ctx.reply(error("Usage: `?automod threshold reset caps|spam|mentions|all`"))
            return
        await self.repos.guild_settings.update(str(ctx.guild.id), **updates)  # type: ignore[union-attr]
        await ctx.reply(
            success(f"Reset **{target.lower()}** threshold{'s' if target.lower() == 'all' else ''} to defaults.")
        )

    @automod_threshold.command(name="caps")
    @administrator_required()
    async def automod_threshold_caps(self, ctx: commands.Context[commands.Bot], value: str) -> None:
        result = validate_caps_threshold_input(value)
        if not result["ok"]:
            await ctx.reply(error(result["error"]))
            return
        from bot.constants import CAPS_MIN_LETTERS

        await self.repos.guild_settings.update(str(ctx.guild.id), caps_threshold=result["value"])  # type: ignore[union-attr]
        await ctx.reply(
            success(
                f"Caps threshold set to **{result['value']}%** for messages with at least {CAPS_MIN_LETTERS} letters.",
            ),
        )

    @automod_threshold.command(name="spam-count")
    @administrator_required()
    async def automod_threshold_spam_count(self, ctx: commands.Context[commands.Bot], value: str) -> None:
        result = validate_spam_count_input(value)
        if not result["ok"]:
            await ctx.reply(error(result["error"]))
            return
        guild_id = str(ctx.guild.id)  # type: ignore[union-attr]
        await self.repos.guild_settings.update(guild_id, spam_threshold=result["value"])
        settings = await self.repos.guild_settings.get(guild_id)
        from bot.utils.automod_thresholds import format_spam_window

        await ctx.reply(
            success(
                f"Spam count set to **{result['value']}** messages within "
                f"{format_spam_window(settings.spam_interval_ms)}.",
            ),
        )

    @automod_threshold.command(name="spam-window")
    @administrator_required()
    async def automod_threshold_spam_window(self, ctx: commands.Context[commands.Bot], value: str) -> None:
        result = validate_spam_window_input(value)
        if not result["ok"]:
            await ctx.reply(error(result["error"]))
            return
        guild_id = str(ctx.guild.id)  # type: ignore[union-attr]
        await self.repos.guild_settings.update(guild_id, spam_interval_ms=result["value"])
        settings = await self.repos.guild_settings.get(guild_id)
        from bot.utils.automod_thresholds import format_spam_window

        await ctx.reply(
            success(
                f"Spam window set to **{format_spam_window(result['value'])}** "
                f"({settings.spam_threshold} messages within window).",
            ),
        )

    @automod_threshold.command(name="mentions")
    @administrator_required()
    async def automod_threshold_mentions(self, ctx: commands.Context[commands.Bot], value: str) -> None:
        result = validate_mention_threshold_input(value)
        if not result["ok"]:
            await ctx.reply(error(result["error"]))
            return
        await self.repos.guild_settings.update(str(ctx.guild.id), mention_threshold=result["value"])  # type: ignore[union-attr]
        await ctx.reply(
            success(
                f"Mention threshold set to **{result['value']}** user/role mentions per message "
                "(@everyone/@here always flagged).",
            ),
        )

    @automod.command(name="antispam")
    @administrator_required()
    async def automod_antispam(self, ctx: commands.Context[commands.Bot], state: str = "on") -> None:
        await self.repos.guild_settings.update(str(ctx.guild.id), anti_spam=state.lower() != "off")  # type: ignore[union-attr]
        await ctx.reply(success(f"Anti-spam {'disabled' if state.lower() == 'off' else 'enabled'}."))

    @automod.command(name="anticaps")
    @administrator_required()
    async def automod_anticaps(self, ctx: commands.Context[commands.Bot], state: str = "on") -> None:
        await self.repos.guild_settings.update(str(ctx.guild.id), anti_caps=state.lower() != "off")  # type: ignore[union-attr]
        await ctx.reply(success(f"Anti-caps {'disabled' if state.lower() == 'off' else 'enabled'}."))

    @automod.command(name="antiinvite")
    @administrator_required()
    async def automod_antiinvite(self, ctx: commands.Context[commands.Bot], state: str = "on") -> None:
        await self.repos.guild_settings.update(str(ctx.guild.id), anti_invite=state.lower() != "off")  # type: ignore[union-attr]
        await ctx.reply(success(f"Anti-invite {'disabled' if state.lower() == 'off' else 'enabled'}."))

    @automod.command(name="antimention")
    @administrator_required()
    async def automod_antimention(self, ctx: commands.Context[commands.Bot], state: str = "on") -> None:
        await self.repos.guild_settings.update(str(ctx.guild.id), anti_mention=state.lower() != "off")  # type: ignore[union-attr]
        await ctx.reply(success(f"Anti-mention {'disabled' if state.lower() == 'off' else 'enabled'}."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutomodCog(bot))
