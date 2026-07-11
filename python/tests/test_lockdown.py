"""Lockdown repository tests (ported from verify-lockdown.mjs)."""

from __future__ import annotations

import pytest
from bot.errors import DatabaseError
from bot.utils.channel_permissions import apply_permission_state
from tests.conftest import Repositories


@pytest.mark.asyncio
async def test_add_and_remove_lockdown_channels(repos: Repositories, guild_id: str) -> None:
    channels = await repos.lockdown.add_channel(guild_id, "ch-1")
    assert channels == ["ch-1"]
    channels = await repos.lockdown.add_channel(guild_id, "ch-2")
    assert channels == ["ch-1", "ch-2"]

    with pytest.raises(DatabaseError, match="duplicate_lockdown_channel"):
        await repos.lockdown.add_channel(guild_id, "ch-1")

    removed = await repos.lockdown.remove_channel(guild_id, "ch-2")
    assert removed == 1
    assert await repos.lockdown.list_channels(guild_id) == ["ch-1"]


@pytest.mark.asyncio
async def test_enable_disable_state_roundtrip(
    repos: Repositories,
    guild_id: str,
    mock_channel_factory,
) -> None:
    await repos.lockdown.add_channel(guild_id, "ch-state")
    role_id = "role-everyone"

    for initial_state in ("allow", "deny", "unset"):
        await repos.lockdown.clear_active(guild_id)
        channel = mock_channel_factory("ch-state", role_id, initial_state)
        role = type("Role", (), {"id": role_id})()

        acquire = await repos.lockdown.acquire_enable(
            guild_id,
            moderator_id="mod-1",
            reason="test enable",
            role_id=role_id,
        )
        assert acquire.ok is True
        assert acquire.operation is not None

        await apply_permission_state(channel, role, "send_messages", "deny", reason="lockdown")
        await repos.lockdown.finalize_enable(
            guild_id,
            [
                {
                    "channel_id": "ch-state",
                    "previous_state": initial_state,
                    "applied_state": "deny",
                    "result": "applied",
                },
            ],
        )

        state = await repos.lockdown.get_state(guild_id)
        assert state.active is True
        snapshot = state.channels[0]
        assert snapshot.previous_state == initial_state
        assert snapshot.applied_state == "deny"

        disable_acquire = await repos.lockdown.acquire_disable(guild_id)
        assert disable_acquire.ok is True
        await apply_permission_state(channel, role, "send_messages", initial_state, reason="unlock")
        await repos.lockdown.finalize_disable(
            guild_id,
            moderator_id="mod-1",
            reason="test disable",
        )
        assert channel.get_state() == initial_state
        await repos.lockdown.clear_active(guild_id)


@pytest.mark.asyncio
async def test_concurrent_enable_only_one_wins(repos: Repositories, guild_id: str) -> None:
    await repos.lockdown.add_channel(guild_id, "ch-race")
    first = await repos.lockdown.acquire_enable(
        guild_id,
        moderator_id="mod-1",
        reason="race 1",
        role_id="role-everyone",
    )
    second = await repos.lockdown.acquire_enable(
        guild_id,
        moderator_id="mod-2",
        reason="race 2",
        role_id="role-everyone",
    )
    assert first.ok is True
    assert second.ok is False
    assert second.reason == "already_active"
    await repos.lockdown.clear_active(guild_id)
