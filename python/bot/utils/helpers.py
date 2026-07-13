"""User-facing message helpers and regex constants."""

from __future__ import annotations

import re

import discord

LINK_REGEX = re.compile(r"https?://[^\s]+", re.IGNORECASE)
INVITE_REGEX = re.compile(
    r"(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li)|discordapp\.com/invite)/[^\s]+",
    re.IGNORECASE,
)
MENTION_ONLY_RE = re.compile(r"^<@!?(\d+)>$")
ROLE_MENTION_RE = re.compile(r"^<@&(\d+)>$")
CHANNEL_MENTION_RE = re.compile(r"^<#(\d+)>$")
SNOWFLAKE_RE = re.compile(r"^\d{17,20}$")


def success(message: str) -> str:
    return f"✅ {message}"


def error(message: str) -> str:
    return f"❌ {message}"


def info(message: str) -> str:
    return f"ℹ️ {message}"


def basic_embed(
    title: str,
    description: str,
    *,
    color: int = 0x5865F2,
) -> discord.Embed:
    return discord.Embed(title=title, description=description, color=color)


def parse_args(content: str, prefix: str) -> tuple[str, str, str, str]:
    without_prefix = content[len(prefix) :].strip()
    if not without_prefix:
        return "", "", "", ""
    parts = without_prefix.split()
    command = parts[0].lower()
    rest = " ".join(parts[1:])
    sub_parts = rest.split() if rest else []
    subcommand = sub_parts[0].lower() if sub_parts else ""
    subargs = " ".join(sub_parts[1:]) if len(sub_parts) > 1 else ""
    return command, rest, subcommand, subargs


def chunk_lines(lines: list[str], *, max_len: int = 1900) -> list[str]:
    if not lines:
        return ["*(empty)*"]
    chunks: list[str] = []
    current = ""
    for line in lines:
        candidate = f"{current}\n{line}".strip() if current else line
        if len(candidate) > max_len:
            if current:
                chunks.append(current)
            current = line[:max_len]
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
