#!/usr/bin/env python3
"""
Import Dyno moderation cases into the bot database.

Usage:
    python scripts/import_dyno.py --guild-id 123456789 --json dyno-cases.json
    python scripts/import_dyno.py --guild-id 123456789 --json dyno-cases.json --mod-map scripts/mod_id_map.json
    python scripts/import_dyno.py --guild-id 123456789 --json dyno-cases.json --dry-run
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import db

ACTION_MAP = {
    "warn":         "warn",
    "mute":         "mute",
    "mute [auto]":  "mute",
    "unmute":       "unmute",
    "ban":          "ban",
    "unban":        "unban",
    "kick":         "kick",
    "softban":      "softban",
    "role persist": "role_persist",
}


def parse_timestamp(s: str) -> str | None:
    if not s:
        return None
    return s if len(s) > 16 else s + ":00"


def load_mod_map(path: str) -> dict[str, int]:
    with open(path) as f:
        raw = json.load(f)
    resolved = {}
    skipped = []
    for display, user_id in raw.items():
        if user_id is not None:
            resolved[display] = int(user_id)
        else:
            skipped.append(display)
    if skipped:
        print(f"  {len(skipped)} moderators not mapped (will use display name only):")
        for name in skipped:
            print(f"    {name}")
    return resolved


def run(guild_id: int, json_path: str, mod_map: dict, dry_run: bool):
    with open(json_path) as f:
        data = json.load(f)

    cases = data.get("cases", [])
    if not cases:
        print("No cases found in file.")
        return

    counts = {}
    skipped = 0
    warnings_inserted = 0
    id_resolved = 0

    with db.get_db() as conn:
        for case in cases:
            raw_action = case.get("action", "").strip().lower()
            action = ACTION_MAP.get(raw_action)
            if not action:
                skipped += 1
                continue

            target_id = int(case["target_user_id"])
            moderator_display = case.get("moderator_display") or None
            moderator_id = mod_map.get(moderator_display, 0) if moderator_display else 0
            if moderator_id:
                id_resolved += 1

            reason = case.get("reason") or None
            if reason:
                reason = reason[:1000]
            created_at = parse_timestamp(case.get("occurred_at_local"))

            if not dry_run:
                case_number = db.next_case_number(conn, guild_id)
                conn.execute(
                    "INSERT INTO mod_actions "
                    "(guild_id, case_number, action, target_id, moderator_id, moderator_display, reason, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (guild_id, case_number, action, target_id, moderator_id, moderator_display, reason, created_at)
                )

                if action == "warn":
                    conn.execute(
                        "INSERT INTO warnings (guild_id, user_id, reason, moderator_id, created_at) "
                        "VALUES (?, ?, ?, ?, ?)",
                        (guild_id, target_id, reason, moderator_id, created_at)
                    )
                    warnings_inserted += 1

            counts[action] = counts.get(action, 0) + 1

    label = "[DRY RUN] " if dry_run else ""
    total = sum(counts.values())
    print(f"\n{label}Imported {total} cases ({skipped} skipped - unknown action type)")
    for action, n in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {action:<15} {n}")
    if warnings_inserted:
        print(f"\n  {warnings_inserted} warn cases also written to warnings table")
    if mod_map:
        print(f"  {id_resolved}/{total} cases had moderator IDs resolved")
    if dry_run:
        print("\nRe-run without --dry-run to commit.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--guild-id", required=True, type=int)
    parser.add_argument("--json",     required=True)
    parser.add_argument("--mod-map",  default=None, help="Path to mod_id_map.json")
    parser.add_argument("--db",       default=None, help="Override DB path")
    parser.add_argument("--dry-run",  action="store_true")
    args = parser.parse_args()

    if args.db:
        os.environ["DB_PATH"] = args.db
        import importlib
        importlib.reload(db)

    db.init_db()

    mod_map = {}
    if args.mod_map:
        print(f"Loading mod map from {args.mod_map}...")
        mod_map = load_mod_map(args.mod_map)
        print(f"  {len(mod_map)} moderators resolved to IDs")

    run(args.guild_id, args.json, mod_map, args.dry_run)


if __name__ == "__main__":
    main()
