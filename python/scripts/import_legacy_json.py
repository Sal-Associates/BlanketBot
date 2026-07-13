#!/usr/bin/env python3
"""Import legacy JavaScript store.json into SQLite (read-only on source JSON)."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# Allow running as `python scripts/import_legacy_json.py` from python/
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from bot.automod.thresholds import coerce_threshold_value
from bot.constants import DEFAULT_DATABASE_PATH
from bot.database.connection import Database
from bot.database.migrations import run_migrations

logger = logging.getLogger(__name__)

REQUIRED_TOP_LEVEL_KEYS = (
    "guild_settings",
    "mod_roles",
    "admin_roles",
    "warnings",
    "notes",
    "mod_logs",
    "automod_words",
    "banned_words",
    "automod_links",
    "automod_ignored_channels",
    "automod_ignored_roles",
    "timed_actions",
    "cases",
    "mod_queue",
    "case_counters",
    "_counters",
)

DEFAULT_JSON_PATH = _ROOT.parent / "node-bun" / "data" / "store.json"
MIGRATIONS_DIR = _ROOT / "migrations"


@dataclass
class ImportSummary:
    imported: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def bump(self, key: str, *, skipped: bool = False) -> None:
        bucket = self.skipped if skipped else self.imported
        bucket[key] = bucket.get(key, 0) + 1

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        logger.warning(message)

    def error(self, message: str) -> None:
        self.errors.append(message)
        logger.error(message)


def _ms_to_iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed:
            return None
        if trimmed.endswith("Z") or "T" in trimmed:
            return trimmed
        if trimmed.isdigit():
            value = int(trimmed)
        else:
            return trimmed
    try:
        ts = int(value)
    except (TypeError, ValueError):
        return None
    if ts > 1_000_000_000_000:
        ts //= 1000
    return datetime.fromtimestamp(ts, tz=UTC).strftime("%Y-%m-%dT%H:%M:%fZ")


def _parse_json_array(raw: Any) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _parse_disabled_modules(raw: Any) -> list[str]:
    modules = _parse_json_array(raw)
    return [str(item) for item in modules]


def migrate_automod_module_state(raw: dict[str, Any], merged: dict[str, Any]) -> bool:
    disabled = _parse_disabled_modules(raw.get("disabled_modules", merged.get("disabled_modules", "[]")))
    if "Automod" in disabled:
        merged["automod_module_migrated"] = 1
        return False

    if raw.get("_automod_module_migrated"):
        merged["automod_module_migrated"] = 1
        return False

    changed = False
    if "automod_enabled" in raw and not raw.get("automod_enabled"):
        if "Automod" not in disabled:
            disabled.append("Automod")
            merged["disabled_modules"] = json.dumps(disabled)
            changed = True

    merged["automod_module_migrated"] = 1
    if not raw.get("_automod_module_migrated"):
        changed = True
    return changed


def collect_banned_words(data: dict[str, Any], summary: ImportSummary) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for entry in data.get("banned_words") or []:
        if not isinstance(entry, dict):
            summary.warn("Skipping malformed banned_words entry")
            continue
        guild_id = str(entry.get("guild_id", ""))
        value = str(entry.get("value", "")).strip().lower()
        mode = str(entry.get("match_mode", "contains")).lower()
        if not guild_id or not value or mode not in {"contains", "exact"}:
            summary.warn(f"Skipping invalid banned_words entry: {entry!r}")
            continue
        key = (guild_id, value, mode)
        if key in seen:
            summary.bump("banned_words", skipped=True)
            continue
        seen.add(key)
        records.append(
            {
                "id": entry.get("id"),
                "guild_id": guild_id,
                "value": value,
                "match_mode": mode,
                "created_by": entry.get("created_by"),
                "created_at": _ms_to_iso(entry.get("created_at")),
            },
        )

    for legacy in data.get("automod_words") or []:
        if not isinstance(legacy, dict):
            summary.warn("Skipping malformed automod_words entry")
            continue
        guild_id = str(legacy.get("guild_id", ""))
        value = str(legacy.get("word", legacy.get("value", ""))).strip().lower()
        if not guild_id or not value:
            continue
        exact = legacy.get("exact")
        mode = "exact" if exact in (1, True) or legacy.get("match_mode") == "exact" else "contains"
        key = (guild_id, value, mode)
        if key in seen:
            summary.bump("banned_words", skipped=True)
            continue
        seen.add(key)
        records.append(
            {
                "id": None,
                "guild_id": guild_id,
                "value": value,
                "match_mode": mode,
                "created_by": legacy.get("created_by"),
                "created_at": _ms_to_iso(legacy.get("created_at")),
            },
        )

    return records


def validate_store_json(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise ValueError("Root JSON value must be an object")
    defaults: dict[str, Any] = {
        "guild_settings": {},
        "mod_roles": [],
        "admin_roles": [],
        "warnings": [],
        "notes": [],
        "mod_logs": [],
        "automod_words": [],
        "banned_words": [],
        "automod_links": [],
        "automod_ignored_channels": [],
        "automod_ignored_roles": [],
        "timed_actions": [],
        "cases": [],
        "mod_queue": [],
        "case_counters": {},
        "_counters": {
            "warnings": 0,
            "notes": 0,
            "mod_logs": 0,
            "timed_actions": 0,
            "mod_queue": 0,
            "banned_words": 0,
        },
    }
    normalized = {**defaults, **data}
    for key, default in defaults.items():
        if normalized.get(key) is None:
            normalized[key] = default
    if not isinstance(normalized["guild_settings"], dict):
        raise ValueError("guild_settings must be an object")
    return normalized


async def database_has_data(db: Database) -> bool:
    row = await db.fetchone("SELECT COUNT(*) AS count FROM guild_settings")
    return bool(row and int(row["count"]) > 0)


async def backup_database(db_path: Path) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = db_path.with_suffix(db_path.suffix + f".bak-{timestamp}")
    shutil.copy2(db_path, backup_path)
    return backup_path


async def import_data(
    db: Database,
    data: dict[str, Any],
    *,
    dry_run: bool,
    summary: ImportSummary,
) -> None:
    banned_words = collect_banned_words(data, summary)

    if dry_run:
        summary.imported["guild_settings"] = len(data.get("guild_settings", {}))
        summary.imported["mod_roles"] = len(data.get("mod_roles", []))
        summary.imported["admin_roles"] = len(data.get("admin_roles", []))
        summary.imported["warnings"] = len(data.get("warnings", []))
        summary.imported["notes"] = len(data.get("notes", []))
        summary.imported["cases"] = len(data.get("cases", []))
        summary.imported["timed_actions"] = len(data.get("timed_actions", []))
        summary.imported["mod_queue"] = len(data.get("mod_queue", []))
        summary.imported["banned_words"] = len(banned_words)
        summary.imported["automod_links"] = len(data.get("automod_links", []))
        summary.imported["automod_ignored_channels"] = len(data.get("automod_ignored_channels", []))
        summary.imported["automod_ignored_roles"] = len(data.get("automod_ignored_roles", []))
        summary.skipped["mod_logs"] = len(data.get("mod_logs", []))
        return

    await db.execute("BEGIN IMMEDIATE")

    try:
        for guild_id, raw_settings in (data.get("guild_settings") or {}).items():
            if not isinstance(raw_settings, dict):
                summary.warn(f"Skipping malformed guild_settings for {guild_id}")
                continue

            merged = dict(raw_settings)
            merged["guild_id"] = str(guild_id)
            migrate_automod_module_state(raw_settings, merged)
            normalized = dict(merged)
            for key in (
                "caps_threshold",
                "spam_threshold",
                "spam_interval_ms",
                "mention_threshold",
            ):
                if key == "spam_interval_ms" and "spam_interval" in normalized and "spam_interval_ms" not in merged:
                    normalized["spam_interval_ms"] = normalized.get("spam_interval")
                value, _ = coerce_threshold_value(key, normalized.get(key))
                normalized[key] = value
            disabled_modules = json.dumps(_parse_disabled_modules(normalized.get("disabled_modules", "[]")))
            spam_interval = normalized.get("spam_interval_ms", normalized.get("spam_interval", 5000))

            await db.execute(
                """
                INSERT INTO guild_settings (
                    guild_id, prefix, mod_log_channel_id, mod_queue_channel_id, mod_queue_enabled,
                    mute_role_id, strike_enabled, strike_mute_at, strike_ban_at,
                    anti_spam, anti_caps, anti_invite, anti_mention,
                    caps_threshold, spam_threshold, spam_interval_ms, mention_threshold,
                    disabled_modules, automod_module_migrated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    prefix = excluded.prefix,
                    mod_log_channel_id = excluded.mod_log_channel_id,
                    mod_queue_channel_id = excluded.mod_queue_channel_id,
                    mod_queue_enabled = excluded.mod_queue_enabled,
                    mute_role_id = excluded.mute_role_id,
                    strike_enabled = excluded.strike_enabled,
                    strike_mute_at = excluded.strike_mute_at,
                    strike_ban_at = excluded.strike_ban_at,
                    anti_spam = excluded.anti_spam,
                    anti_caps = excluded.anti_caps,
                    anti_invite = excluded.anti_invite,
                    anti_mention = excluded.anti_mention,
                    caps_threshold = excluded.caps_threshold,
                    spam_threshold = excluded.spam_threshold,
                    spam_interval_ms = excluded.spam_interval_ms,
                    mention_threshold = excluded.mention_threshold,
                    disabled_modules = excluded.disabled_modules,
                    automod_module_migrated = excluded.automod_module_migrated,
                    updated_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
                """,
                (
                    str(guild_id),
                    str(normalized.get("prefix", "?")),
                    normalized.get("mod_log_channel") or normalized.get("mod_log_channel_id"),
                    normalized.get("mod_queue_channel") or normalized.get("mod_queue_channel_id"),
                    int(bool(normalized.get("mod_queue_enabled", 0))),
                    normalized.get("mute_role") or normalized.get("mute_role_id"),
                    int(bool(normalized.get("strike_enabled", 1))),
                    int(normalized.get("strike_mute_at", 3)),
                    int(normalized.get("strike_ban_at", 5)),
                    int(bool(normalized.get("anti_spam", 1))),
                    int(bool(normalized.get("anti_caps", 0))),
                    int(bool(normalized.get("anti_invite", 0))),
                    int(bool(normalized.get("anti_mention", 0))),
                    int(normalized.get("caps_threshold", 70)),
                    int(normalized.get("spam_threshold", 5)),
                    int(spam_interval),
                    int(normalized.get("mention_threshold", 5)),
                    disabled_modules,
                    int(bool(normalized.get("automod_module_migrated", 0))),
                ),
            )
            summary.bump("guild_settings")

            for channel_id in _parse_json_array(normalized.get("lockdown_channels", "[]")):
                await db.execute(
                    "INSERT OR IGNORE INTO lockdown_channels (guild_id, channel_id) VALUES (?, ?)",
                    (str(guild_id), str(channel_id)),
                )
                summary.bump("lockdown_channels")

            lockdown_state = normalized.get("lockdown_state")
            if lockdown_state:
                try:
                    state = json.loads(lockdown_state) if isinstance(lockdown_state, str) else lockdown_state
                except json.JSONDecodeError:
                    summary.warn(f"Skipping malformed lockdown_state for guild {guild_id}")
                    state = None
                if isinstance(state, dict) and state.get("active"):
                    cursor = await db.execute(
                        """
                        INSERT INTO lockdown_operations (
                            guild_id, active, disabling, started_at, started_by, reason,
                            role_id, permission, metadata_json
                        ) VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(guild_id),
                            int(bool(state.get("disabling", False))),
                            _ms_to_iso(state.get("started_at")),
                            state.get("started_by"),
                            state.get("reason"),
                            state.get("role_id"),
                            state.get("permission", "SendMessages"),
                            json.dumps(
                                {
                                    "last_disabled_at": state.get("last_disabled_at"),
                                    "last_disabled_by": state.get("last_disabled_by"),
                                    "disable_reason": state.get("disable_reason"),
                                },
                            ),
                        ),
                    )
                    operation_id = cursor.lastrowid
                    for channel in state.get("channels") or []:
                        if not isinstance(channel, dict):
                            continue
                        await db.execute(
                            """
                            INSERT INTO lockdown_channel_snapshots (
                                operation_id, channel_id, previous_state, applied_state,
                                result, disable_result, error
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                operation_id,
                                str(channel.get("channel_id", "")),
                                channel.get("previous_state"),
                                channel.get("applied_state"),
                                channel.get("result"),
                                channel.get("disable_result"),
                                channel.get("error"),
                            ),
                        )
                    summary.bump("lockdown_operations")

        for role in data.get("mod_roles") or []:
            if not isinstance(role, dict):
                continue
            await db.execute(
                "INSERT OR IGNORE INTO staff_roles (guild_id, role_id, role_type) VALUES (?, ?, ?)",
                (str(role.get("guild_id", "")), str(role.get("role_id", "")), "moderator"),
            )
            summary.bump("staff_roles")

        for role in data.get("admin_roles") or []:
            if not isinstance(role, dict):
                continue
            await db.execute(
                "INSERT OR IGNORE INTO staff_roles (guild_id, role_id, role_type) VALUES (?, ?, ?)",
                (str(role.get("guild_id", "")), str(role.get("role_id", "")), "administrator"),
            )
            summary.bump("staff_roles")

        for warning in data.get("warnings") or []:
            if not isinstance(warning, dict):
                summary.warn("Skipping malformed warning")
                continue
            await db.execute(
                """
                INSERT INTO warnings (
                    id, guild_id, user_id, moderator_id, reason, source, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    warning.get("id"),
                    str(warning.get("guild_id", "")),
                    str(warning.get("user_id", "")),
                    str(warning.get("moderator_id", "")),
                    warning.get("reason") or "",
                    warning.get("source"),
                    "active",
                    _ms_to_iso(warning.get("created_at")),
                ),
            )
            summary.bump("warnings")

        for note in data.get("notes") or []:
            if not isinstance(note, dict):
                summary.warn("Skipping malformed note")
                continue
            await db.execute(
                """
                INSERT INTO notes (id, guild_id, user_id, author_id, content, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    note.get("id"),
                    str(note.get("guild_id", "")),
                    str(note.get("user_id", "")),
                    str(note.get("author_id", "")),
                    note.get("content") or "",
                    _ms_to_iso(note.get("created_at")),
                    _ms_to_iso(note.get("updated_at") or note.get("created_at")),
                ),
            )
            summary.bump("notes")

        for case in data.get("cases") or []:
            if not isinstance(case, dict):
                summary.warn("Skipping malformed case")
                continue
            extra = case.get("extra") or case.get("metadata") or {}
            metadata = extra if isinstance(extra, dict) else {}
            if case.get("source") and "source" not in metadata:
                metadata["source"] = case.get("source")
            if case.get("status") and "status" not in metadata:
                metadata["status"] = case.get("status")
            await db.execute(
                """
                INSERT INTO cases (
                    guild_id, case_number, user_id, moderator_id, action,
                    reason, source, status, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, case_number) DO NOTHING
                """,
                (
                    str(case.get("guild_id", "")),
                    int(case.get("case_number", 0)),
                    str(case.get("user_id", "")),
                    str(case.get("moderator_id", "")),
                    case.get("action") or "",
                    case.get("reason"),
                    case.get("source") or metadata.get("source"),
                    case.get("status") or metadata.get("status"),
                    json.dumps(metadata),
                    _ms_to_iso(case.get("created_at")),
                ),
            )
            summary.bump("cases")

        for guild_id, next_number in (data.get("case_counters") or {}).items():
            await db.execute(
                """
                INSERT INTO case_counters (guild_id, next_case_number)
                VALUES (?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET next_case_number = excluded.next_case_number
                """,
                (
                    str(guild_id),
                    int(next_number) + 1 if isinstance(next_number, int) else int(next_number),
                ),
            )
            summary.bump("case_counters")

        for action in data.get("timed_actions") or []:
            if not isinstance(action, dict):
                summary.warn("Skipping malformed timed_action")
                continue
            ends_at = _ms_to_iso(action.get("ends_at"))
            if not ends_at:
                summary.warn(f"Skipping timed_action without ends_at: {action.get('id')}")
                summary.bump("timed_actions", skipped=True)
                continue
            created_at = _ms_to_iso(action.get("created_at")) or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%fZ")
            await db.execute(
                """
                INSERT INTO timed_actions (
                    id, guild_id, user_id, channel_id, role_id, action, permission,
                    previous_state, applied_state, ends_at, status, attempt_count,
                    next_retry_at, last_error, last_logged_error, moderator_id, metadata_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    action.get("id"),
                    str(action.get("guild_id", "")),
                    action.get("user_id"),
                    action.get("channel_id"),
                    action.get("role_id"),
                    action.get("action") or "",
                    action.get("permission"),
                    action.get("previous_state"),
                    action.get("applied_state"),
                    ends_at,
                    action.get("status", "pending"),
                    int(action.get("attempt_count", 0)),
                    _ms_to_iso(action.get("next_retry_at")),
                    action.get("last_error"),
                    action.get("last_logged_error"),
                    action.get("moderator_id"),
                    json.dumps(action.get("metadata") or {}),
                    created_at,
                ),
            )
            summary.bump("timed_actions")

        for entry in data.get("mod_queue") or []:
            if not isinstance(entry, dict):
                summary.warn("Skipping malformed mod_queue entry")
                continue
            await db.execute(
                """
                INSERT INTO mod_queue (
                    id, guild_id, channel_id, author_id, message_id, queue_message_id,
                    content, reason, status, moderator_id, created_at, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO NOTHING
                """,
                (
                    entry.get("id"),
                    str(entry.get("guild_id", "")),
                    str(entry.get("channel_id", "")),
                    str(entry.get("author_id", "")),
                    entry.get("message_id"),
                    entry.get("queue_message_id"),
                    entry.get("content"),
                    entry.get("reason") or "",
                    entry.get("status", "pending"),
                    entry.get("moderator_id"),
                    _ms_to_iso(entry.get("created_at")),
                    _ms_to_iso(entry.get("resolved_at")),
                ),
            )
            summary.bump("mod_queue")

        for word in banned_words:
            await db.execute(
                """
                INSERT OR IGNORE INTO banned_words (guild_id, value, match_mode, created_by, created_at)
                VALUES (?, ?, ?, ?, COALESCE(?, strftime('%Y-%m-%dT%H:%M:%fZ', 'now')))
                """,
                (
                    word["guild_id"],
                    word["value"],
                    word["match_mode"],
                    word.get("created_by"),
                    word.get("created_at"),
                ),
            )
            summary.bump("banned_words")

        for link in data.get("automod_links") or []:
            if not isinstance(link, dict):
                continue
            await db.execute(
                "INSERT OR IGNORE INTO automod_links (guild_id, link, list_type) VALUES (?, ?, ?)",
                (
                    str(link.get("guild_id", "")),
                    str(link.get("link", "")).strip().lower(),
                    str(link.get("list_type", "blacklist")).lower(),
                ),
            )
            summary.bump("automod_links")

        for channel in data.get("automod_ignored_channels") or []:
            if not isinstance(channel, dict):
                continue
            await db.execute(
                "INSERT OR IGNORE INTO automod_ignored_channels (guild_id, channel_id) VALUES (?, ?)",
                (str(channel.get("guild_id", "")), str(channel.get("channel_id", ""))),
            )
            summary.bump("automod_ignored_channels")

        for role in data.get("automod_ignored_roles") or []:
            if not isinstance(role, dict):
                continue
            await db.execute(
                "INSERT OR IGNORE INTO automod_ignored_roles (guild_id, role_id) VALUES (?, ?)",
                (str(role.get("guild_id", "")), str(role.get("role_id", ""))),
            )
            summary.bump("automod_ignored_roles")

        summary.skipped["mod_logs"] = len(data.get("mod_logs") or [])

        await db.execute("COMMIT")
    except Exception:
        await db.execute("ROLLBACK")
        raise


def print_summary(summary: ImportSummary, *, dry_run: bool) -> None:
    mode = "DRY RUN" if dry_run else "IMPORT"
    print(f"\n=== Legacy JSON {mode} Summary ===")
    if summary.imported:
        print("\nImported:")
        for key, count in sorted(summary.imported.items()):
            print(f"  {key}: {count}")
    if summary.skipped:
        print("\nSkipped:")
        for key, count in sorted(summary.skipped.items()):
            print(f"  {key}: {count}")
    if summary.warnings:
        print(f"\nWarnings ({len(summary.warnings)}):")
        for message in summary.warnings[:20]:
            print(f"  - {message}")
        if len(summary.warnings) > 20:
            print(f"  ... and {len(summary.warnings) - 20} more")
    if summary.errors:
        print(f"\nErrors ({len(summary.errors)}):")
        for message in summary.errors:
            print(f"  - {message}")


async def run_import(
    *,
    json_path: Path,
    db_path: Path,
    dry_run: bool,
    force: bool,
) -> int:
    summary = ImportSummary()

    if not json_path.is_file():
        summary.error(f"Source JSON not found: {json_path}")
        print_summary(summary, dry_run=dry_run)
        return 1

    raw_text = json_path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        summary.error(f"Invalid JSON in {json_path}: {exc}")
        print_summary(summary, dry_run=dry_run)
        return 1

    try:
        data = validate_store_json(data)
    except ValueError as exc:
        summary.error(str(exc))
        print_summary(summary, dry_run=dry_run)
        return 1

    db = Database(db_path)
    await db.connect()
    try:
        await run_migrations(db, MIGRATIONS_DIR)

        if await database_has_data(db) and not force and not dry_run:
            summary.error(
                "Target database already contains guild settings. "
                "Use --force to import anyway or choose an empty database.",
            )
            print_summary(summary, dry_run=dry_run)
            return 1

        if db_path.exists() and not dry_run:
            backup_path = await backup_database(db_path)
            print(f"Backed up existing database to {backup_path}")

        await import_data(db, data, dry_run=dry_run, summary=summary)
    finally:
        await db.close()

    print_summary(summary, dry_run=dry_run)
    return 0 if not summary.errors else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json",
        "--source",
        dest="json",
        type=Path,
        default=DEFAULT_JSON_PATH,
        help=f"Path to legacy store.json (default: {DEFAULT_JSON_PATH})",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=_ROOT / DEFAULT_DATABASE_PATH,
        help=f"Target SQLite database (default: {_ROOT / DEFAULT_DATABASE_PATH})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report without writing to SQLite",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Import even if the target database already has data",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    import asyncio

    return asyncio.run(
        run_import(
            json_path=args.json.resolve(),
            db_path=args.db.resolve(),
            dry_run=args.dry_run,
            force=args.force,
        ),
    )


if __name__ == "__main__":
    raise SystemExit(main())
