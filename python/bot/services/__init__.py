"""Business logic services."""

from bot.services.authorization import is_admin, is_moderator, is_superuser
from bot.services.hierarchy import (
    MODERATION_DENIAL,
    HierarchyResult,
    check_bot_can_act_on,
    check_moderation_target,
    get_moderation_denied,
)
from bot.services.lockdown import build_lockdown_status, disable_lockdown, enable_lockdown
from bot.services.mod_log import get_or_create_mute_role, send_mod_log
from bot.services.moderation import ModerationService
from bot.services.moderation_compensation import (
    persistence_logging_failure_message,
    persistence_rollback_message,
    rollback_temporary_ban,
    rollback_temporary_mute,
)
from bot.services.prefix import get_prefix, update_prefix, validate_prefix
from bot.services.strikes import check_strike_escalation

__all__ = [
    "HierarchyResult",
    "MODERATION_DENIAL",
    "ModerationService",
    "build_lockdown_status",
    "check_bot_can_act_on",
    "check_moderation_target",
    "check_strike_escalation",
    "disable_lockdown",
    "enable_lockdown",
    "get_moderation_denied",
    "get_or_create_mute_role",
    "get_prefix",
    "is_admin",
    "is_moderator",
    "is_superuser",
    "persistence_logging_failure_message",
    "persistence_rollback_message",
    "rollback_temporary_ban",
    "rollback_temporary_mute",
    "send_mod_log",
    "update_prefix",
    "validate_prefix",
]
