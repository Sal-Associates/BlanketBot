"""Shared repository accessors for cogs."""

from __future__ import annotations

from discord.ext import commands

from bot.database.repositories.automod import AutomodRepository
from bot.database.repositories.banned_words import BannedWordsRepository
from bot.database.repositories.cases import CasesRepository
from bot.database.repositories.guild_settings import GuildSettingsRepository
from bot.database.repositories.lockdown import LockdownRepository
from bot.database.repositories.mod_queue import ModQueueRepository
from bot.database.repositories.notes import NotesRepository
from bot.database.repositories.staff_roles import StaffRolesRepository
from bot.database.repositories.strike_state import StrikeStateRepository
from bot.database.repositories.timed_actions import TimedActionsRepository
from bot.database.repositories.warnings import WarningsRepository
from bot.services.moderation import ModerationService


class CogRepos:
    """Lazy repository and service factory bound to a bot instance."""

    def __init__(self, bot: commands.Bot) -> None:
        self._bot = bot

    @property
    def db(self):
        return self._bot.database  # type: ignore[attr-defined]

    @property
    def guild_settings(self) -> GuildSettingsRepository:
        return GuildSettingsRepository(self.db)

    @property
    def staff_roles(self) -> StaffRolesRepository:
        return StaffRolesRepository(self.db)

    @property
    def cases(self) -> CasesRepository:
        return CasesRepository(self.db)

    @property
    def warnings(self) -> WarningsRepository:
        return WarningsRepository(self.db)

    @property
    def notes(self) -> NotesRepository:
        return NotesRepository(self.db)

    @property
    def timed_actions(self) -> TimedActionsRepository:
        return TimedActionsRepository(self.db)

    @property
    def lockdown(self) -> LockdownRepository:
        return LockdownRepository(self.db)

    @property
    def automod(self) -> AutomodRepository:
        return AutomodRepository(self.db)

    @property
    def banned_words(self) -> BannedWordsRepository:
        return BannedWordsRepository(self.db)

    @property
    def mod_queue(self) -> ModQueueRepository:
        return ModQueueRepository(self.db)

    @property
    def strike_state(self) -> StrikeStateRepository:
        return StrikeStateRepository(self.db)

    @property
    def moderation(self) -> ModerationService:
        return ModerationService(
            cases=self.cases,
            timed_actions=self.timed_actions,
            guild_settings=self.guild_settings,
        )
