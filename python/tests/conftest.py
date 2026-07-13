"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import discord
import pytest
import pytest_asyncio
from bot.config import Settings
from bot.database.connection import Database
from bot.database.migrations import run_migrations
from bot.database.repositories.automod import AutomodRepository
from bot.database.repositories.banned_words import BannedWordsRepository
from bot.database.repositories.cases import CasesRepository
from bot.database.repositories.guild_settings import GuildSettingsRepository
from bot.database.repositories.lockdown import LockdownRepository
from bot.database.repositories.mod_queue import ModQueueRepository
from bot.database.repositories.notes import NotesRepository
from bot.database.repositories.staff_roles import StaffRolesRepository
from bot.database.repositories.timed_actions import TimedActionsRepository
from bot.database.repositories.warnings import WarningsRepository

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
GUILD_ID = "123456789012345678"
ROLE_EVERYONE = "role-everyone"

INITIAL_TABLES = frozenset(
    {
        "schema_migrations",
        "guild_settings",
        "staff_roles",
        "warnings",
        "notes",
        "case_counters",
        "cases",
        "timed_actions",
        "mod_queue",
        "banned_words",
        "automod_ignored_channels",
        "automod_ignored_roles",
        "automod_links",
        "lockdown_channels",
        "lockdown_operations",
        "lockdown_channel_snapshots",
        "strike_escalation_state",
        "note_revisions",
    },
)


@dataclass
class Repositories:
    guild_settings: GuildSettingsRepository
    staff_roles: StaffRolesRepository
    warnings: WarningsRepository
    notes: NotesRepository
    cases: CasesRepository
    timed_actions: TimedActionsRepository
    mod_queue: ModQueueRepository
    banned_words: BannedWordsRepository
    automod: AutomodRepository
    lockdown: LockdownRepository


@pytest.fixture
def guild_id() -> str:
    return GUILD_ID


@pytest.fixture
def settings() -> Settings:
    return Settings(
        discord_token="test-token",
        guild_id=GUILD_ID,
        superuser_ids=frozenset({"super"}),
        database_path=Path("data/test.sqlite3"),
    )


@pytest.fixture
def tmp_db_path(tmp_path: Path) -> Path:
    return tmp_path / "test.sqlite3"


@pytest_asyncio.fixture
async def database(tmp_db_path: Path) -> AsyncIterator[Database]:
    db = Database(tmp_db_path)
    await db.connect()
    try:
        yield db
    finally:
        await db.close()


@pytest_asyncio.fixture
async def migrated_database(database: Database) -> AsyncIterator[Database]:
    await run_migrations(database, MIGRATIONS_DIR)
    yield database


@pytest_asyncio.fixture
async def repos(migrated_database: Database) -> Repositories:
    return Repositories(
        guild_settings=GuildSettingsRepository(migrated_database),
        staff_roles=StaffRolesRepository(migrated_database),
        warnings=WarningsRepository(migrated_database),
        notes=NotesRepository(migrated_database),
        cases=CasesRepository(migrated_database),
        timed_actions=TimedActionsRepository(migrated_database),
        mod_queue=ModQueueRepository(migrated_database),
        banned_words=BannedWordsRepository(migrated_database),
        automod=AutomodRepository(migrated_database),
        lockdown=LockdownRepository(migrated_database),
    )


@pytest.fixture
def legacy_store_path(tmp_path: Path) -> Path:
    source = Path(__file__).resolve().parent / "fixtures" / "legacy_store.sample.json"
    target = tmp_path / "store.json"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    return target


@pytest.fixture
def empty_legacy_store() -> dict[str, Any]:
    return {
        "guild_settings": {},
        "mod_roles": [],
        "admin_roles": [],
        "warnings": [],
        "notes": [],
        "mod_logs": [],
        "automod_words": [],
        "banned_words": [],
        "automod_links": [],
        "automod_ignored_channels": [],
        "automod_ignored_roles": [],
        "timed_actions": [],
        "cases": [],
        "mod_queue": [],
        "case_counters": {},
        "_counters": {
            "warnings": 0,
            "notes": 0,
            "mod_logs": 0,
            "timed_actions": 0,
            "mod_queue": 0,
            "banned_words": 0,
        },
    }


def make_role(position: int, role_id: str = "role") -> MagicMock:
    role = MagicMock(spec=discord.Role)
    role.id = int(role_id) if role_id.isdigit() else hash(role_id) % 10**18
    role.position = position
    role.name = role_id
    return role


def make_member(
    member_id: str,
    position: int,
    *,
    guild: MagicMock | None = None,
    tag: str | None = None,
) -> MagicMock:
    member = MagicMock(spec=discord.Member)
    member.id = int(member_id) if member_id.isdigit() else hash(member_id) % 10**18
    if member_id == "owner" and guild is not None:
        member.id = guild.owner_id
    role = make_role(position, f"role-{member_id}")
    member.roles = MagicMock()
    member.roles.highest = role
    member.top_role = role
    member.guild = guild
    member.user = MagicMock()
    member.user.id = member.id
    member.user.tag = tag or f"User{member_id}"
    member.display_name = tag or f"User{member_id}"
    return member


def make_guild(*, owner_id: str = "owner", bot_position: int = 20) -> MagicMock:
    guild = MagicMock(spec=discord.Guild)
    guild.id = int(GUILD_ID)
    guild.owner_id = int(owner_id) if owner_id.isdigit() else hash(owner_id) % 10**18
    bot_role = make_role(bot_position, "bot-role")
    guild.me = MagicMock(spec=discord.Member)
    guild.me.id = int("bot") if False else 999_999_999_999_999_999
    guild.me.roles = MagicMock()
    guild.me.roles.highest = bot_role
    guild.me.top_role = bot_role
    guild.default_role = make_role(0, ROLE_EVERYONE)
    guild.default_role.id = int(ROLE_EVERYONE) if ROLE_EVERYONE.isdigit() else 111
    return guild


@dataclass
class MockOverwriteChannel:
    """Minimal channel mock for permission overwrite tests."""

    channel_id: str
    role_id: str
    permission: str = "send_messages"
    fail_edits: int = 0
    _allow: bool | None = field(default=None, init=False)
    _deny: bool | None = field(default=None, init=False)
    _remaining_failures: int = field(init=False)

    def __post_init__(self) -> None:
        self._remaining_failures = self.fail_edits

    def set_initial_state(self, state: str) -> None:
        if state == "allow":
            self._allow, self._deny = True, False
        elif state == "deny":
            self._allow, self._deny = False, True
        else:
            self._allow, self._deny = None, None

    def overwrites_for(self, role: Any) -> discord.PermissionOverwrite:
        overwrite = discord.PermissionOverwrite()
        setattr(overwrite, self.permission, self._allow if self._deny is not True else False)
        if self._deny is True:
            setattr(overwrite, self.permission, False)
        elif self._allow is True:
            setattr(overwrite, self.permission, True)
        else:
            setattr(overwrite, self.permission, None)
        return overwrite

    async def set_permissions(self, role: Any, *, overwrite: discord.PermissionOverwrite, reason: str = "") -> None:
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise discord.HTTPException(MagicMock(), "500: Discord API unavailable")
        value = getattr(overwrite, self.permission, None)
        if value is True:
            self._allow, self._deny = True, False
        elif value is False:
            self._allow, self._deny = False, True
        else:
            self._allow, self._deny = None, None

    def get_state(self) -> str:
        if self._deny is True:
            return "deny"
        if self._allow is True:
            return "allow"
        return "unset"


@pytest.fixture
def mock_channel_factory() -> Callable[..., MockOverwriteChannel]:
    def factory(
        channel_id: str, role_id: str, initial_state: str = "unset", *, fail_edits: int = 0
    ) -> MockOverwriteChannel:
        channel = MockOverwriteChannel(channel_id=channel_id, role_id=role_id, fail_edits=fail_edits)
        channel.set_initial_state(initial_state)
        return channel

    return factory
