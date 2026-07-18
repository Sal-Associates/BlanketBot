"""
Tests for pure logic and database functions.
"""
import os
import sys
import pytest
from datetime import timedelta
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from utils import parse_duration, format_duration


class TestParseDuration:
    def test_seconds(self):
        assert parse_duration("30s") == timedelta(seconds=30)
        assert parse_duration("30sec") == timedelta(seconds=30)
        assert parse_duration("30seconds") == timedelta(seconds=30)

    def test_minutes(self):
        assert parse_duration("10m") == timedelta(minutes=10)
        assert parse_duration("10min") == timedelta(minutes=10)
        assert parse_duration("10mins") == timedelta(minutes=10)
        assert parse_duration("10minutes") == timedelta(minutes=10)

    def test_hours(self):
        assert parse_duration("2h") == timedelta(hours=2)
        assert parse_duration("2hr") == timedelta(hours=2)
        assert parse_duration("2hours") == timedelta(hours=2)

    def test_days(self):
        assert parse_duration("1d") == timedelta(days=1)
        assert parse_duration("1day") == timedelta(days=1)
        assert parse_duration("1days") == timedelta(days=1)

    def test_invalid(self):
        assert parse_duration("invalid") is None
        assert parse_duration("") is None
        assert parse_duration(None) is None
        assert parse_duration("10x") is None

    def test_case_insensitive(self):
        assert parse_duration("10M") == timedelta(minutes=10)
        assert parse_duration("2H") == timedelta(hours=2)


class TestFormatDuration:
    def test_minutes(self):
        assert format_duration(timedelta(minutes=10)) == "10m"

    def test_hours(self):
        assert format_duration(timedelta(hours=2)) == "2h"

    def test_days(self):
        assert format_duration(timedelta(days=1)) == "1d"

    def test_compound(self):
        assert format_duration(timedelta(days=1, hours=2)) == "1d 2h"
        assert format_duration(timedelta(hours=1, minutes=30)) == "1h 30m"

    def test_zero(self):
        assert format_duration(timedelta(0)) == "0s"


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    import importlib
    monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
    import db
    importlib.reload(db)
    db.init_db()
    return db


class TestDatabase:
    def test_init_creates_tables(self, test_db):
        with test_db.get_db() as conn:
            tables = {r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()}
        expected = {
            "guild_settings", "guild_case_seq", "staff_roles",
            "warnings", "mod_actions", "timed_mutes",
            "permission_snapshots", "notes", "banned_words",
            "automod_ignored", "automod_links", "lockdown_channels",
        }
        assert expected.issubset(tables)

    def test_next_case_number_sequential(self, test_db):
        with test_db.get_db() as conn:
            assert test_db.next_case_number(conn, 111) == 1
            assert test_db.next_case_number(conn, 111) == 2
            assert test_db.next_case_number(conn, 111) == 3

    def test_next_case_number_per_guild(self, test_db):
        with test_db.get_db() as conn:
            assert test_db.next_case_number(conn, 111) == 1
            assert test_db.next_case_number(conn, 222) == 1
            assert test_db.next_case_number(conn, 111) == 2

    def test_ensure_guild_settings(self, test_db):
        test_db.ensure_guild_settings(999)
        row = test_db.get_guild_settings(999)
        assert row is not None
        assert row["guild_id"] == 999
        assert row["automod_enabled"] == 0

    def test_ensure_guild_settings_idempotent(self, test_db):
        test_db.ensure_guild_settings(999)
        test_db.ensure_guild_settings(999)
        assert test_db.get_guild_settings(999) is not None

    def test_permission_snapshot_roundtrip(self, test_db):
        test_db.save_permission_snapshot(1, 100, "lock", None)
        assert test_db.pop_permission_snapshot(1, 100, "lock") is None

        test_db.save_permission_snapshot(1, 100, "lock", True)
        assert test_db.pop_permission_snapshot(1, 100, "lock") is True

        test_db.save_permission_snapshot(1, 100, "lock", False)
        assert test_db.pop_permission_snapshot(1, 100, "lock") is False

    def test_pop_snapshot_removes_entry(self, test_db):
        test_db.save_permission_snapshot(1, 100, "lock", True)
        test_db.pop_permission_snapshot(1, 100, "lock")
        assert test_db.pop_permission_snapshot(1, 100, "lock") is None

    def test_get_guild_settings_missing(self, test_db):
        assert test_db.get_guild_settings(99999) is None


from cogs.purge import _filter_messages


def _msg(bot=False, content="hello", attachments=None, embeds=None, mentions=None):
    m = MagicMock()
    m.author.bot = bot
    m.content = content
    m.attachments = attachments or []
    m.embeds = embeds or []
    m.mentions = mentions or []
    m.role_mentions = []
    return m


class TestPurgeFilters:
    def test_bots(self):
        msgs = [_msg(bot=True), _msg(bot=False), _msg(bot=True)]
        assert len(_filter_messages(msgs, "bots", None, 10)) == 2

    def test_humans(self):
        msgs = [_msg(bot=True), _msg(bot=False), _msg(bot=True)]
        assert len(_filter_messages(msgs, "humans", None, 10)) == 1

    def test_match(self):
        msgs = [_msg(content="hello world"), _msg(content="goodbye"), _msg(content="hello again")]
        assert len(_filter_messages(msgs, "match", "hello", 10)) == 2

    def test_not(self):
        msgs = [_msg(content="hello world"), _msg(content="goodbye"), _msg(content="hello again")]
        assert len(_filter_messages(msgs, "not", "hello", 10)) == 1

    def test_startswith(self):
        msgs = [_msg(content="hello world"), _msg(content="goodbye"), _msg(content="hey")]
        assert len(_filter_messages(msgs, "startswith", "he", 10)) == 2

    def test_count_limit(self):
        msgs = [_msg(bot=True) for _ in range(10)]
        assert len(_filter_messages(msgs, "bots", None, 3)) == 3

    def test_any(self):
        msgs = [_msg(), _msg(), _msg()]
        assert len(_filter_messages(msgs, "any", None, 10)) == 3

    def test_text_only(self):
        plain = _msg(content="hello")
        with_embed = _msg(content="hello", embeds=[MagicMock()])
        with_attachment = _msg(content="hello", attachments=[MagicMock()])
        assert _filter_messages([plain, with_embed, with_attachment], "text", None, 10) == [plain]