"""Database row models and enums (expanded in later stages)."""

from __future__ import annotations

from enum import StrEnum


class WarningStatus(StrEnum):
    ACTIVE = "active"
    VOIDED = "voided"


class StaffRoleType(StrEnum):
    MODERATOR = "moderator"
    ADMINISTRATOR = "administrator"


class TimedActionStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"


class ModQueueStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class BannedWordMatchMode(StrEnum):
    CONTAINS = "contains"
    EXACT = "exact"
