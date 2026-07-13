"""Guild settings persistence."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from bot.constants import AUTOMOD_THRESHOLD_DEFAULTS, DEFAULT_PREFIX
from bot.database.repositories.base import Repository


@dataclass(frozen=True, slots=True)
class GuildSettings:
    guild_id: str
    prefix: str = DEFAULT_PREFIX
    mod_log_channel_id: str | None = None
    mod_queue_channel_id: str | None = None
    mod_queue_enabled: bool = False
    mute_role_id: str | None = None
    strike_enabled: bool = True
    strike_mute_at: int = 3
    strike_ban_at: int = 5
    anti_spam: bool = True
    anti_caps: bool = False
    anti_invite: bool = False
    anti_mention: bool = False
    caps_threshold: int = 70
    spam_threshold: int = 5
    spam_interval_ms: int = 5000
    mention_threshold: int = 5
    disabled_modules: tuple[str, ...] = ()

    @classmethod
    def from_row(cls, row: Any) -> GuildSettings:
        disabled = json.loads(row["disabled_modules"] or "[]")
        return cls(
            guild_id=row["guild_id"],
            prefix=row["prefix"] or DEFAULT_PREFIX,
            mod_log_channel_id=row["mod_log_channel_id"],
            mod_queue_channel_id=row["mod_queue_channel_id"],
            mod_queue_enabled=bool(row["mod_queue_enabled"]),
            mute_role_id=row["mute_role_id"],
            strike_enabled=bool(row["strike_enabled"]),
            strike_mute_at=int(row["strike_mute_at"]),
            strike_ban_at=int(row["strike_ban_at"]),
            anti_spam=bool(row["anti_spam"]),
            anti_caps=bool(row["anti_caps"]),
            anti_invite=bool(row["anti_invite"]),
            anti_mention=bool(row["anti_mention"]),
            caps_threshold=int(row["caps_threshold"]),
            spam_threshold=int(row["spam_threshold"]),
            spam_interval_ms=int(row["spam_interval_ms"]),
            mention_threshold=int(row["mention_threshold"]),
            disabled_modules=tuple(disabled),
        )


class GuildSettingsRepository(Repository):
    async def ensure_guild(self, guild_id: str) -> GuildSettings:
        row = await self._db.fetchone(
            "SELECT * FROM guild_settings WHERE guild_id = ?",
            (guild_id,),
        )
        if row:
            return GuildSettings.from_row(row)
        await self._db.execute(
            """
            INSERT INTO guild_settings (guild_id) VALUES (?)
            ON CONFLICT(guild_id) DO NOTHING
            """,
            (guild_id,),
        )
        await self._db.commit()
        row = await self._db.fetchone(
            "SELECT * FROM guild_settings WHERE guild_id = ?",
            (guild_id,),
        )
        assert row is not None
        return GuildSettings.from_row(row)

    async def get(self, guild_id: str) -> GuildSettings:
        return await self.ensure_guild(guild_id)

    async def update(self, guild_id: str, **fields: Any) -> GuildSettings:
        await self.ensure_guild(guild_id)
        if not fields:
            return await self.get(guild_id)
        columns = []
        values: list[Any] = []
        for key, value in fields.items():
            if key == "disabled_modules":
                value = json.dumps(list(value))
            elif key in {
                "mod_queue_enabled",
                "strike_enabled",
                "anti_spam",
                "anti_caps",
                "anti_invite",
                "anti_mention",
            }:
                value = int(bool(value))
            columns.append(f"{key} = ?")
            values.append(value)
        columns.append("updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')")
        values.append(guild_id)
        await self._db.execute(
            f"UPDATE guild_settings SET {', '.join(columns)} WHERE guild_id = ?",
            tuple(values),
        )
        await self._db.commit()
        return await self.get(guild_id)

    async def is_module_disabled(self, guild_id: str, module_name: str) -> bool:
        settings = await self.get(guild_id)
        return module_name in settings.disabled_modules

    async def toggle_module(self, guild_id: str, module_name: str) -> tuple[bool, GuildSettings]:
        settings = await self.get(guild_id)
        disabled = set(settings.disabled_modules)
        if module_name in disabled:
            disabled.remove(module_name)
            enabled = True
        else:
            disabled.add(module_name)
            enabled = False
        updated = await self.update(guild_id, disabled_modules=tuple(sorted(disabled)))
        return enabled, updated

    async def get_prefix(self, guild_id: str) -> str:
        return (await self.get(guild_id)).prefix

    def normalize_thresholds(self, settings: GuildSettings) -> GuildSettings:
        data = {
            "caps_threshold": settings.caps_threshold,
            "spam_threshold": settings.spam_threshold,
            "spam_interval_ms": settings.spam_interval_ms,
            "mention_threshold": settings.mention_threshold,
        }
        normalized = {**AUTOMOD_THRESHOLD_DEFAULTS}
        for key, default in AUTOMOD_THRESHOLD_DEFAULTS.items():
            value = data.get(key, default)
            if key == "caps_threshold":
                normalized[key] = max(50, min(100, int(value)))
            elif key == "spam_threshold":
                normalized[key] = max(3, min(20, int(value)))
            elif key == "spam_interval_ms":
                normalized[key] = max(1000, min(60_000, int(value)))
            elif key == "mention_threshold":
                normalized[key] = max(2, min(50, int(value)))
        return GuildSettings(
            **{
                **settings.__dict__,
                **normalized,
            },
        )
