"""Timed action retry policy."""

from __future__ import annotations

MAX_CHANNEL_UNLOCK_ATTEMPTS = 10
SCHEDULER_POLL_INTERVAL_SECONDS = 15
RETRY_DELAYS_MS = [30_000, 60_000, 120_000, 300_000]


def get_retry_delay_ms(attempt_count: int) -> int:
    index = min(max(attempt_count - 1, 0), len(RETRY_DELAYS_MS) - 1)
    return max(RETRY_DELAYS_MS[index], SCHEDULER_POLL_INTERVAL_SECONDS * 1000)


def sanitize_timed_action_error(err: BaseException | str | None) -> str:
    if not err:
        return "unknown_error"
    if isinstance(err, str):
        return err[:200]
    code = getattr(err, "code", None) or getattr(err, "status", None)
    message = str(err)[:200]
    return f"{code}: {message}" if code else message
