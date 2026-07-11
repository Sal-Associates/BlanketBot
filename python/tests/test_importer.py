"""Legacy JSON importer tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.import_legacy_json import ImportSummary, import_data, run_import, validate_store_json


def test_validate_store_json_requires_top_level_keys(empty_legacy_store: dict) -> None:
    validate_store_json(empty_legacy_store)
    normalized = validate_store_json({"guild_settings": {}})
    assert normalized["banned_words"] == []


@pytest.mark.asyncio
async def test_dry_run_does_not_modify_database(
    migrated_database,
    legacy_store_path: Path,
    tmp_db_path: Path,
) -> None:
    migrated_database.path = tmp_db_path
    exit_code = await run_import(json_path=legacy_store_path, db_path=tmp_db_path, dry_run=True, force=False)
    assert exit_code == 0
    row = await migrated_database.fetchone("SELECT COUNT(*) AS count FROM guild_settings")
    assert int(row["count"]) == 0


@pytest.mark.asyncio
async def test_import_sample_store_skips_mod_logs(
    migrated_database,
    legacy_store_path: Path,
    tmp_db_path: Path,
) -> None:
    exit_code = await run_import(json_path=legacy_store_path, db_path=tmp_db_path, dry_run=False, force=True)
    assert exit_code == 0

    guild_count = await migrated_database.fetchone("SELECT COUNT(*) AS count FROM guild_settings")
    warnings_count = await migrated_database.fetchone("SELECT COUNT(*) AS count FROM warnings")
    cases_count = await migrated_database.fetchone("SELECT COUNT(*) AS count FROM cases")
    assert int(guild_count["count"]) >= 1
    assert int(warnings_count["count"]) >= 1
    assert int(cases_count["count"]) >= 1

    mod_logs_table = await migrated_database.table_exists("mod_logs")
    assert mod_logs_table is False


@pytest.mark.asyncio
async def test_import_never_modifies_source_json(legacy_store_path: Path, tmp_path: Path) -> None:
    before = legacy_store_path.read_text(encoding="utf-8")
    db_path = tmp_path / "import.sqlite3"
    await run_import(json_path=legacy_store_path, db_path=db_path, dry_run=False, force=True)
    after = legacy_store_path.read_text(encoding="utf-8")
    assert before == after


@pytest.mark.asyncio
async def test_duplicate_import_blocked_without_force(
    migrated_database,
    legacy_store_path: Path,
    tmp_db_path: Path,
) -> None:
    first = await run_import(json_path=legacy_store_path, db_path=tmp_db_path, dry_run=False, force=True)
    assert first == 0
    second = await run_import(json_path=legacy_store_path, db_path=tmp_db_path, dry_run=False, force=False)
    assert second == 1


@pytest.mark.asyncio
async def test_migrate_automod_enabled_to_disabled_modules(
    migrated_database,
    empty_legacy_store,
) -> None:
    empty_legacy_store["guild_settings"] = {
        "legacy-disabled": {
            "guild_id": "legacy-disabled",
            "automod_enabled": 0,
            "disabled_modules": "[]",
        },
    }
    summary = ImportSummary()
    await import_data(migrated_database, empty_legacy_store, dry_run=False, summary=summary)
    row = await migrated_database.fetchone(
        "SELECT disabled_modules FROM guild_settings WHERE guild_id = ?",
        ("legacy-disabled",),
    )
    disabled = json.loads(row["disabled_modules"])
    assert "Automod" in disabled
