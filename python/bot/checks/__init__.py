"""Permission and hierarchy checks for discord.py cogs."""

from bot.checks.decorators import administrator_required, moderator_required

__all__ = ["administrator_required", "moderator_required"]
