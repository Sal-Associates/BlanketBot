"""Structured service results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ServiceResult(Generic[T]):
    ok: bool
    value: T | None = None
    error: str | None = None
    partial: bool = False

    @classmethod
    def success(cls, value: T | None = None) -> ServiceResult[T]:
        return cls(ok=True, value=value)

    @classmethod
    def failure(cls, error: str, *, partial: bool = False) -> ServiceResult[T]:
        return cls(ok=False, error=error, partial=partial)


@dataclass(frozen=True, slots=True)
class HierarchyResult:
    allowed: bool
    reason: str | None = None
