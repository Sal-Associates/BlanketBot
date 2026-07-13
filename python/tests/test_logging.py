"""Logging setup tests."""

from __future__ import annotations

import logging

from bot.utils.logging_setup import setup_logging


def test_setup_logging_is_idempotent() -> None:
    setup_logging(level=logging.DEBUG)
    handler_count = len(logging.getLogger().handlers)
    setup_logging(level=logging.DEBUG)
    assert len(logging.getLogger().handlers) == handler_count
