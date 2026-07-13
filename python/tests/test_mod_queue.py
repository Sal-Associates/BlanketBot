"""Mod queue persistence tests (ported from verify-moderation-workflows.mjs queue sections)."""

from __future__ import annotations

import pytest
from tests.conftest import Repositories


@pytest.mark.asyncio
async def test_add_mod_queue_entry(repos: Repositories, guild_id: str) -> None:
    entry = await repos.mod_queue.add(
        guild_id=guild_id,
        channel_id="ch-1",
        author_id="user-1",
        content="content",
        reason="spam",
    )
    assert entry.id > 0
    assert entry.status.value == "pending"


@pytest.mark.asyncio
async def test_deny_creates_warning_and_case(repos: Repositories, guild_id: str) -> None:
    entry = await repos.mod_queue.add(
        guild_id=guild_id,
        channel_id="ch-1",
        author_id="user-1",
        content="content",
        reason="spam",
    )
    result = await repos.mod_queue.process_decision(
        entry_id=entry.id,
        moderator_id="mod-a",
        decision="deny",
        cases=repos.cases,
        warn_reason="Automod: spam",
        case_action="queue_deny",
        case_reason="Automod violation: spam",
    )
    assert result.status == "success"
    assert result.warning_id is not None
    assert result.case_number is not None

    case = await repos.cases.get_case(guild_id, result.case_number)
    assert case is not None
    assert case.action == "queue_deny"


@pytest.mark.asyncio
async def test_approve_without_warning(repos: Repositories, guild_id: str) -> None:
    entry = await repos.mod_queue.add(
        guild_id=guild_id,
        channel_id="ch-1",
        author_id="user-1",
        content="content",
        reason="spam",
    )
    result = await repos.mod_queue.process_decision(
        entry_id=entry.id,
        moderator_id="mod-a",
        decision="approve",
        cases=repos.cases,
        case_action="queue_approve",
        case_reason="False positive",
    )
    assert result.status == "success"
    assert result.warning_id is None
    assert result.case_number is not None


@pytest.mark.asyncio
async def test_already_processed_decision(repos: Repositories, guild_id: str) -> None:
    entry = await repos.mod_queue.add(
        guild_id=guild_id,
        channel_id="ch-1",
        author_id="user-1",
        content="content",
        reason="spam",
    )
    first = await repos.mod_queue.process_decision(
        entry_id=entry.id,
        moderator_id="mod-a",
        decision="deny",
        cases=repos.cases,
        warn_reason="Automod: spam",
        case_action="queue_deny",
        case_reason="Automod violation: spam",
    )
    assert first.status == "success"

    second = await repos.mod_queue.process_decision(
        entry_id=entry.id,
        moderator_id="mod-b",
        decision="approve",
        cases=repos.cases,
        case_action="queue_approve",
        case_reason="Too late",
    )
    assert second.status == "already_processed"
