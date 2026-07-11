"""Moderation compensation and workflow tests (ported from verify-moderation-workflows.mjs)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from bot.errors import DatabaseError
from bot.services.moderation_compensation import (
    persistence_logging_failure_message,
    persistence_rollback_message,
    rollback_temporary_ban,
    rollback_temporary_mute,
)
from tests.conftest import Repositories


@pytest.mark.asyncio
async def test_warning_transaction_success(repos: Repositories, guild_id: str) -> None:
    warning_id, case_number = await repos.warnings.create_with_case(
        guild_id=guild_id,
        user_id="user-1",
        moderator_id="mod-1",
        reason="warn1",
        source="test",
        cases=repos.cases,
    )
    assert warning_id > 0
    assert case_number > 0


@pytest.mark.asyncio
async def test_concurrent_mod_queue_decision(repos: Repositories, guild_id: str) -> None:
    entry = await repos.mod_queue.add(
        guild_id=guild_id,
        channel_id="ch-1",
        author_id="user-1",
        content="content",
        reason="spam",
    )

    deny_result, approve_result = await asyncio.gather(
        repos.mod_queue.process_decision(
            entry_id=entry.id,
            moderator_id="mod-a",
            decision="deny",
            cases=repos.cases,
            warn_reason="Automod: spam",
            case_action="queue_deny",
            case_reason="Automod violation: spam",
        ),
        repos.mod_queue.process_decision(
            entry_id=entry.id,
            moderator_id="mod-b",
            decision="approve",
            cases=repos.cases,
            case_action="queue_approve",
            case_reason="False positive",
        ),
    )

    statuses = {deny_result.status, approve_result.status}
    assert statuses == {"success", "already_processed"}

    updated = await repos.mod_queue.get(entry.id)
    assert updated is not None
    assert updated.status.value != "pending"


@pytest.mark.asyncio
async def test_temporary_punishment_records(repos: Repositories, guild_id: str) -> None:
    case_number, timed_action_id = await repos.timed_actions.create_temporary_punishment_records(
        guild_id=guild_id,
        user_id="user-ban",
        moderator_id="mod-1",
        case_action="ban",
        case_reason="temp",
        timed_action="unban",
        ends_at_ms=1_783_747_690_834,
        cases=repos.cases,
    )
    assert case_number > 0
    assert timed_action_id > 0


@pytest.mark.asyncio
async def test_rollback_temporary_mute_success() -> None:
    target = MagicMock(spec=discord.Member)
    target.remove_roles = AsyncMock()
    mute_role = MagicMock(spec=discord.Role)
    result = await rollback_temporary_mute(target, mute_role)
    assert result.success is True
    target.remove_roles.assert_awaited_once()


@pytest.mark.asyncio
async def test_rollback_temporary_mute_failure_message() -> None:
    target = MagicMock(spec=discord.Member)
    target.remove_roles = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "fail"))
    mute_role = MagicMock(spec=discord.Role)
    result = await rollback_temporary_mute(target, mute_role)
    assert result.success is False
    assert "manual intervention" in persistence_rollback_message("mute", result).lower()


@pytest.mark.asyncio
async def test_rollback_temporary_ban_success() -> None:
    guild = MagicMock(spec=discord.Guild)
    guild.unban = AsyncMock()
    result = await rollback_temporary_ban(guild, "123456789012345678")
    assert result.success is True
    guild.unban.assert_awaited_once()


def test_persistence_logging_failure_message() -> None:
    assert "could not be saved" in persistence_logging_failure_message("kicked").lower()


@pytest.mark.asyncio
async def test_duplicate_banned_word_raises(repos: Repositories, guild_id: str) -> None:
    await repos.banned_words.add(guild_id, "spam", "contains", created_by="mod-1")
    with pytest.raises(DatabaseError, match="duplicate_banned_word"):
        await repos.banned_words.add(guild_id, "spam", "contains", created_by="mod-1")
