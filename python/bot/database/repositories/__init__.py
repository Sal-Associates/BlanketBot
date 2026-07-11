"""Repository layer."""

from bot.database.repositories.automod import AutomodLinkListType, AutomodRepository
from bot.database.repositories.banned_words import BannedWordRecord, BannedWordsRepository
from bot.database.repositories.base import Repository
from bot.database.repositories.cases import CaseRecord, CasesRepository
from bot.database.repositories.guild_settings import GuildSettings, GuildSettingsRepository
from bot.database.repositories.lockdown import (
    LockdownAcquireResult,
    LockdownOperationRecord,
    LockdownRepository,
    LockdownSnapshotRecord,
    LockdownState,
)
from bot.database.repositories.mod_queue import (
    ModQueueDecisionResult,
    ModQueueRecord,
    ModQueueRepository,
)
from bot.database.repositories.notes import NoteRecord, NoteRevisionRecord, NotesRepository
from bot.database.repositories.staff_roles import StaffRolesRepository
from bot.database.repositories.strike_state import StrikeStateRecord, StrikeStateRepository
from bot.database.repositories.timed_actions import TimedActionRecord, TimedActionsRepository
from bot.database.repositories.warnings import WarningRecord, WarningsRepository

__all__ = [
    "AutomodLinkListType",
    "AutomodRepository",
    "BannedWordRecord",
    "BannedWordsRepository",
    "CaseRecord",
    "CasesRepository",
    "GuildSettings",
    "GuildSettingsRepository",
    "LockdownAcquireResult",
    "LockdownOperationRecord",
    "LockdownRepository",
    "LockdownSnapshotRecord",
    "LockdownState",
    "ModQueueDecisionResult",
    "ModQueueRecord",
    "ModQueueRepository",
    "NoteRecord",
    "NoteRevisionRecord",
    "NotesRepository",
    "Repository",
    "StaffRolesRepository",
    "StrikeStateRecord",
    "StrikeStateRepository",
    "TimedActionRecord",
    "TimedActionsRepository",
    "WarningRecord",
    "WarningsRepository",
]
