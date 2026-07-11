"""Moderation hierarchy validation (ported from verify-moderation.mjs)."""

from __future__ import annotations

from bot.services.hierarchy import MODERATION_DENIAL, check_bot_can_act_on, check_moderation_target
from tests.conftest import make_guild, make_member


def test_moderator_can_target_lower_role() -> None:
    guild = make_guild(owner_id="owner", bot_position=20)
    mod = make_member("mod", 10, guild=guild)
    target = make_member("target-low", 5, guild=guild)
    assert check_moderation_target(guild, mod, target).allowed is True


def test_equal_role_denied() -> None:
    guild = make_guild(owner_id="owner", bot_position=20)
    mod = make_member("mod", 10, guild=guild)
    target = make_member("target-equal", 10, guild=guild)
    result = check_moderation_target(guild, mod, target)
    assert result.allowed is False
    assert result.reason == MODERATION_DENIAL["TARGET_ABOVE_ISSUER"]


def test_higher_target_denied() -> None:
    guild = make_guild(owner_id="owner", bot_position=20)
    mod = make_member("mod", 10, guild=guild)
    target = make_member("target-high", 15, guild=guild)
    assert check_moderation_target(guild, mod, target).allowed is False


def test_owner_can_target_high_role_when_bot_allows() -> None:
    guild = make_guild(owner_id="owner", bot_position=20)
    owner = make_member("owner", 0, guild=guild)
    target = make_member("target-high", 15, guild=guild)
    assert check_moderation_target(guild, owner, target).allowed is True


def test_superuser_still_blocked_by_hierarchy() -> None:
    guild = make_guild(owner_id="owner", bot_position=20)
    superuser = make_member("super", 3, guild=guild)
    target = make_member("target-high", 15, guild=guild)
    assert check_moderation_target(guild, superuser, target).allowed is False


def test_bot_must_be_above_target() -> None:
    low_bot_guild = make_guild(owner_id="owner", bot_position=8)
    mod = make_member("mod", 10, guild=low_bot_guild)
    target = make_member("target-nine", 9, guild=low_bot_guild)
    result = check_moderation_target(low_bot_guild, mod, target)
    assert result.allowed is False
    assert result.reason == MODERATION_DENIAL["BOT_CANNOT_ACT"]


def test_self_target_denied() -> None:
    guild = make_guild(owner_id="owner", bot_position=20)
    mod = make_member("mod", 10, guild=guild)
    result = check_moderation_target(guild, mod, mod)
    assert result.allowed is False
    assert result.reason == MODERATION_DENIAL["SELF"]


def test_owner_target_denied() -> None:
    guild = make_guild(owner_id="owner", bot_position=20)
    mod = make_member("mod", 10, guild=guild)
    owner = make_member("owner", 0, guild=guild)
    result = check_moderation_target(guild, mod, owner)
    assert result.allowed is False
    assert result.reason == MODERATION_DENIAL["TARGET_IS_OWNER"]


def test_plain_user_object_denied_for_member_actions() -> None:
    guild = make_guild(owner_id="owner", bot_position=20)
    mod = make_member("mod", 10, guild=guild)
    result = check_moderation_target(guild, mod, type("User", (), {"id": "gone"})())
    assert result.allowed is False
    assert result.reason == MODERATION_DENIAL["NOT_A_MEMBER"]


def test_raw_user_id_allowed_when_member_not_required() -> None:
    guild = make_guild(owner_id="owner", bot_position=20)
    mod = make_member("mod", 10, guild=guild)
    result = check_moderation_target(
        guild,
        mod,
        type("User", (), {"id": 999_999_999_999_999_999})(),
        require_member=False,
    )
    assert result.allowed is True


def test_check_bot_can_act_on_helper() -> None:
    guild = make_guild(owner_id="owner", bot_position=20)
    target = make_member("target-low", 5, guild=guild)
    assert check_bot_can_act_on(guild, target).allowed is True

    low_bot_guild = make_guild(owner_id="owner", bot_position=8)
    high_target = make_member("target-nine", 9, guild=low_bot_guild)
    assert check_bot_can_act_on(low_bot_guild, high_target).allowed is False
