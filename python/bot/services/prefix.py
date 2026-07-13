"""Dynamic command prefix management."""

from __future__ import annotations

from bot.constants import DEFAULT_PREFIX
from bot.database.repositories.guild_settings import GuildSettingsRepository
from bot.result_types import ServiceResult

MAX_PREFIX_LENGTH = 5


def validate_prefix(raw: str | None) -> ServiceResult[str]:
    if raw is None:
        return ServiceResult.failure("Please provide a prefix (max 5 characters).")
    prefix = raw.strip()
    if not prefix:
        return ServiceResult.failure("Please provide a prefix (max 5 characters).")
    if len(prefix) > MAX_PREFIX_LENGTH:
        return ServiceResult.failure("Please provide a prefix (max 5 characters).")
    if prefix.isspace():
        return ServiceResult.failure("Please provide a prefix (max 5 characters).")
    return ServiceResult.success(prefix)


async def get_prefix(guild_id: str, guild_settings: GuildSettingsRepository) -> str:
    prefix = await guild_settings.get_prefix(guild_id)
    return prefix or DEFAULT_PREFIX


async def update_prefix(
    guild_id: str,
    new_prefix: str,
    guild_settings: GuildSettingsRepository,
) -> ServiceResult[str]:
    validated = validate_prefix(new_prefix)
    if not validated.ok or validated.value is None:
        return validated
    await guild_settings.update(guild_id, prefix=validated.value)
    return ServiceResult.success(validated.value)
