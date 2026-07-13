"""Entry point: ``python -m bot``."""

from __future__ import annotations

import asyncio
import logging
import sys

from bot.client import build_bot
from bot.config import load_settings
from bot.errors import ConfigurationError
from bot.utils.logging_setup import setup_logging

logger = logging.getLogger(__name__)


async def _run() -> None:
    settings = load_settings()
    bot = build_bot(settings)
    async with bot:
        await bot.start(settings.discord_token)


def main() -> None:
    setup_logging()
    try:
        asyncio.run(_run())
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Shutdown requested")


if __name__ == "__main__":
    main()
