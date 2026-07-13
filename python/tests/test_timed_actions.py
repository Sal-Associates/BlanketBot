"""Timed channel actions (ported from verify-timed-channel.mjs)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from bot.utils.channel_permissions import (
    apply_permission_state,
    channel_permission_matches,
    get_permission_state,
    restore_channel_from_timed_action,
)
from bot.utils.timed_action_retry import MAX_CHANNEL_UNLOCK_ATTEMPTS, get_retry_delay_ms
from tests.conftest import MockOverwriteChannel, Repositories


def test_permission_state_serialization() -> None:
    for state in ("allow", "deny", "unset"):
        channel = MockOverwriteChannel("ch", "role")
        channel.set_initial_state(state)
        overwrite = channel.overwrites_for(None)
        assert get_permission_state(overwrite, "send_messages") == state


@pytest.mark.asyncio
async def test_permission_state_apply_and_restore(mock_channel_factory) -> None:
    for state in ("allow", "deny", "unset"):
        channel = mock_channel_factory("channel-1", "role-everyone", state)
        role = type("Role", (), {"id": "role-everyone"})()
        await apply_permission_state(channel, role, "send_messages", "deny", reason="test")
        assert channel.get_state() == "deny"
        await apply_permission_state(channel, role, "send_messages", state, reason="restore")
        assert channel.get_state() == state


@pytest.mark.asyncio
async def test_overlapping_channel_unlock_upsert(repos: Repositories, guild_id: str) -> None:
    now = datetime.now(UTC)
    ends_a = (now + timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%fZ")
    ends_b = (now + timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%fZ")

    first_id = await repos.timed_actions.upsert_channel(
        guild_id=guild_id,
        channel_id="channel-1",
        role_id="role-everyone",
        action="channel_unlock",
        permission="SendMessages",
        previous_state="unset",
        applied_state="deny",
        ends_at=ends_a,
        moderator_id="mod-1",
    )
    second_id = await repos.timed_actions.upsert_channel(
        guild_id=guild_id,
        channel_id="channel-1",
        role_id="role-everyone",
        action="channel_unlock",
        permission="SendMessages",
        previous_state="allow",
        applied_state="deny",
        ends_at=ends_b,
        moderator_id="mod-2",
    )
    assert first_id == second_id
    pending = await repos.timed_actions.list_pending_channel(
        guild_id,
        "channel-1",
        "channel_unlock",
        "SendMessages",
    )
    assert len(pending) == 1
    assert pending[0].previous_state == "unset"
    assert pending[0].ends_at == ends_b


@pytest.mark.asyncio
async def test_cancel_channel_timed_actions(repos: Repositories, guild_id: str) -> None:
    ends_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%fZ")
    await repos.timed_actions.upsert_channel(
        guild_id=guild_id,
        channel_id="channel-1",
        role_id="role-everyone",
        action="channel_unlock",
        permission="SendMessages",
        previous_state="allow",
        applied_state="deny",
        ends_at=ends_at,
        moderator_id="mod-1",
    )
    removed = await repos.timed_actions.cancel_channel(
        guild_id,
        "channel-1",
        "channel_unlock",
        "SendMessages",
    )
    assert removed == 1


@pytest.mark.asyncio
async def test_restore_channel_conflict_helper(mock_channel_factory) -> None:
    channel = mock_channel_factory("channel-1", "role-everyone", "allow")
    role_id = 111
    channel.guild = type("Guild", (), {"get_role": lambda _self, _id: type("Role", (), {"id": role_id})()})()
    result = await restore_channel_from_timed_action(
        channel,
        role_id,
        permission="send_messages",
        applied_state="deny",
        previous_state="unset",
    )
    assert result.kind == "conflict"
    assert channel.get_state() == "allow"


def test_retry_delay_and_permission_match() -> None:
    assert get_retry_delay_ms(1) == 30_000
    assert get_retry_delay_ms(3) == 120_000
    assert get_retry_delay_ms(10) == 300_000
    assert MAX_CHANNEL_UNLOCK_ATTEMPTS == 10

    channel = MockOverwriteChannel("ch", "role")
    channel.set_initial_state("deny")
    overwrite = channel.overwrites_for(None)
    assert channel_permission_matches(overwrite, "send_messages", "deny") is True
