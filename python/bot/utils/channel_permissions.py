"""Channel permission state helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import discord

PermissionState = Literal["allow", "deny", "unset"]


@dataclass(frozen=True, slots=True)
class ChannelRestoreResult:
    kind: Literal["restored", "conflict"]
    previous_state: PermissionState | None = None
    current_state: PermissionState | None = None


def get_permission_state(
    overwrite: discord.PermissionOverwrite | None,
    permission: str,
) -> PermissionState:
    if overwrite is None:
        return "unset"
    value = getattr(overwrite, permission, None)
    if value is True:
        return "allow"
    if value is False:
        return "deny"
    return "unset"


def channel_permission_matches(
    overwrite: discord.PermissionOverwrite | None,
    permission: str,
    expected: PermissionState,
) -> bool:
    return get_permission_state(overwrite, permission) == expected


async def apply_permission_state(
    channel: discord.abc.GuildChannel,
    role: discord.Role,
    permission: str,
    state: PermissionState,
    *,
    reason: str,
) -> None:
    overwrite = channel.overwrites_for(role)
    if state == "allow":
        setattr(overwrite, permission, True)
    elif state == "deny":
        setattr(overwrite, permission, False)
    else:
        setattr(overwrite, permission, None)
    await channel.set_permissions(role, overwrite=overwrite, reason=reason)


async def restore_channel_from_timed_action(
    channel: discord.abc.GuildChannel,
    role_id: int,
    *,
    permission: str = "SendMessages",
    applied_state: PermissionState = "deny",
    previous_state: PermissionState = "unset",
    reason: str = "Restore channel permission",
) -> ChannelRestoreResult:
    role = channel.guild.get_role(role_id) or discord.Object(id=role_id)
    overwrite = channel.overwrites_for(role)  # type: ignore[arg-type]
    if not channel_permission_matches(overwrite, permission, applied_state):
        return ChannelRestoreResult(
            kind="conflict",
            current_state=get_permission_state(overwrite, permission),
        )
    await apply_permission_state(channel, role, permission, previous_state, reason=reason)  # type: ignore[arg-type]
    return ChannelRestoreResult(kind="restored", previous_state=previous_state)
