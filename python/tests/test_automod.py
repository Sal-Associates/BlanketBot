"""Automod module and threshold tests (ported from verify-automod-module.mjs and verify-automod-thresholds.mjs)."""

from __future__ import annotations

import pytest
from bot.automod.handler import prune_spam_tracker, reset_spam_tracker, track_spam
from bot.automod.thresholds import (
    AUTOMOD_THRESHOLD_DEFAULTS,
    caps_percentage,
    coerce_threshold_value,
    get_threshold_reset_updates,
    is_mass_mention,
    validate_caps_threshold_input,
    validate_mention_threshold_input,
    validate_spam_count_input,
    validate_spam_window_input,
)
from bot.constants import CAPS_MIN_LETTERS
from bot.errors import DatabaseError
from tests.conftest import Repositories


def test_canonical_threshold_defaults() -> None:
    assert AUTOMOD_THRESHOLD_DEFAULTS["caps_threshold"] == 70
    assert AUTOMOD_THRESHOLD_DEFAULTS["mention_threshold"] == 5


def test_caps_validation_and_runtime_minimum() -> None:
    assert validate_caps_threshold_input("75")["ok"] is True
    assert validate_caps_threshold_input("49")["ok"] is False
    assert validate_caps_threshold_input("101")["ok"] is False
    assert caps_percentage("A" * CAPS_MIN_LETTERS) == 100
    assert caps_percentage("A" * (CAPS_MIN_LETTERS - 1)) == 0


def test_spam_and_mention_validation() -> None:
    assert validate_spam_count_input("3")["ok"] is True
    assert validate_spam_count_input("2")["ok"] is False
    assert validate_spam_window_input("5s")["value"] == 5000
    assert validate_spam_window_input("500")["ok"] is False
    assert validate_mention_threshold_input("2")["ok"] is True
    assert validate_mention_threshold_input("1")["ok"] is False


def test_mention_runtime_semantics() -> None:
    message = type(
        "Message",
        (),
        {
            "mention_everyone": True,
            "mentions": [],
            "role_mentions": [],
        },
    )()
    assert is_mass_mention(message, 5) is True


def test_spam_tracker_threshold_and_cleanup() -> None:
    reset_spam_tracker()
    assert track_spam("g1", "u1", 3, 5000) is False
    assert track_spam("g1", "u1", 3, 5000) is False
    assert track_spam("g1", "u1", 3, 5000) is True

    reset_spam_tracker()
    for index in range(100):
        track_spam("g2", f"user-{index}", 5, 5000)
    prune_spam_tracker(int(__import__("time").time() * 1000) + 121_000)
    assert track_spam("g2", "user-new", 5, 5000) is False


@pytest.mark.asyncio
async def test_module_toggle_and_threshold_persistence(repos: Repositories, guild_id: str) -> None:
    settings = await repos.guild_settings.get(guild_id)
    assert settings.caps_threshold == AUTOMOD_THRESHOLD_DEFAULTS["caps_threshold"]

    await repos.guild_settings.update(guild_id, caps_threshold=85, anti_caps=False)
    await repos.guild_settings.update(guild_id, anti_caps=True)
    updated = await repos.guild_settings.get(guild_id)
    assert updated.caps_threshold == 85

    reset_updates = get_threshold_reset_updates("spam")
    assert reset_updates is not None
    await repos.guild_settings.update(guild_id, **reset_updates)
    reset_spam = await repos.guild_settings.get(guild_id)
    assert reset_spam.spam_threshold == 5
    assert reset_spam.spam_interval_ms == 5000
    assert reset_spam.caps_threshold == 85


@pytest.mark.asyncio
async def test_automod_ignore_lists(repos: Repositories, guild_id: str) -> None:
    await repos.automod.add_ignored_channel(guild_id, "ch-text")
    assert await repos.automod.list_ignored_channels(guild_id) == ["ch-text"]
    with pytest.raises(DatabaseError, match="duplicate_ignored_channel"):
        await repos.automod.add_ignored_channel(guild_id, "ch-text")
    assert await repos.automod.remove_ignored_channel(guild_id, "ch-text") is True

    await repos.automod.add_ignored_role(guild_id, "role-vip")
    assert await repos.automod.list_ignored_roles(guild_id) == ["role-vip"]
    with pytest.raises(DatabaseError, match="duplicate_ignored_role"):
        await repos.automod.add_ignored_role(guild_id, "role-vip")


@pytest.mark.asyncio
async def test_automod_module_master_switch(repos: Repositories, guild_id: str) -> None:
    enabled, _ = await repos.guild_settings.toggle_module(guild_id, "Automod")
    assert enabled is False
    assert await repos.guild_settings.is_module_disabled(guild_id, "Automod") is True

    enabled, _ = await repos.guild_settings.toggle_module(guild_id, "Automod")
    assert enabled is True
    assert await repos.guild_settings.is_module_disabled(guild_id, "Automod") is False


def test_legacy_threshold_normalization() -> None:
    for key, raw in {
        "caps_threshold": 200,
        "spam_threshold": "bad",
        "spam_interval_ms": 999_999,
        "mention_threshold": 1,
    }.items():
        value, _ = coerce_threshold_value(key, raw)
        if key == "caps_threshold":
            assert value == 70
        elif key == "spam_threshold":
            assert value == 5
        elif key == "spam_interval_ms":
            assert value == 5000
        elif key == "mention_threshold":
            assert value == 5
