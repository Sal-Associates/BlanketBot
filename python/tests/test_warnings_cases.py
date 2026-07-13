"""Warnings and case linkage (ported from verify-cases-consolidation.mjs)."""

from __future__ import annotations

import pytest
from tests.conftest import Repositories


@pytest.mark.asyncio
async def test_warning_creates_single_case_record(repos: Repositories, guild_id: str) -> None:
    warning_id, case_number = await repos.warnings.create_with_case(
        guild_id=guild_id,
        user_id="user-1",
        moderator_id="mod-1",
        reason="warn reason",
        source="warn_command",
        cases=repos.cases,
    )
    assert warning_id > 0
    assert case_number > 0

    case = await repos.cases.get_case(guild_id, case_number)
    assert case is not None
    assert case.action == "warn"
    assert case.metadata.get("warning_id") == warning_id
    assert case.source == "warn_command"


@pytest.mark.asyncio
async def test_temporary_punishment_case_metadata(repos: Repositories, guild_id: str) -> None:
    ends_at = 1_783_747_630_834
    case_number, timed_action_id = await repos.timed_actions.create_temporary_punishment_records(
        guild_id=guild_id,
        user_id="user-ban",
        moderator_id="mod-1",
        case_action="ban",
        case_reason="temp",
        timed_action="unban",
        ends_at_ms=ends_at,
        cases=repos.cases,
    )
    case = await repos.cases.get_case(guild_id, case_number)
    assert case is not None
    assert case.metadata.get("timed_action") == "unban"
    assert case.metadata.get("timed_action_id") == timed_action_id
    assert case.metadata.get("ends_at") == ends_at


@pytest.mark.asyncio
async def test_failed_case_status_preserved(repos: Repositories, guild_id: str) -> None:
    case_number = await repos.cases.create_case(
        guild_id=guild_id,
        user_id="user-1",
        moderator_id="mod-1",
        action="strike_ban_failed",
        reason="bot cannot act",
        source="strike",
        status="failed",
        metadata={"status": "failed"},
    )
    case = await repos.cases.get_case(guild_id, case_number)
    assert case is not None
    assert case.status == "failed"
    assert case.source == "strike"
