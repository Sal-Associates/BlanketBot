import os
import sqlite3
from contextlib import contextmanager

DB_PATH = os.getenv("DB_PATH", "bot.db")

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id          INTEGER PRIMARY KEY,
                log_channel       INTEGER,
                mute_role_id      INTEGER,
                automod_enabled   INTEGER DEFAULT 0,
                anti_spam         INTEGER DEFAULT 0,
                anti_caps         INTEGER DEFAULT 0,
                anti_invite       INTEGER DEFAULT 0,
                anti_mention      INTEGER DEFAULT 0,
                caps_threshold    INTEGER DEFAULT 70,
                spam_count        INTEGER DEFAULT 5,
                spam_window       INTEGER DEFAULT 5,
                mention_threshold INTEGER DEFAULT 5
            );
            CREATE TABLE IF NOT EXISTS guild_case_seq (
                guild_id  INTEGER PRIMARY KEY,
                next_case INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS staff_roles (
                guild_id  INTEGER NOT NULL,
                role_id   INTEGER NOT NULL,
                role_type TEXT NOT NULL,
                PRIMARY KEY (guild_id, role_id, role_type)
            );
            CREATE TABLE IF NOT EXISTS warnings (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id     INTEGER NOT NULL,
                user_id      INTEGER NOT NULL,
                reason       TEXT,
                moderator_id INTEGER NOT NULL,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS mod_actions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id     INTEGER NOT NULL,
                case_number  INTEGER,
                action       TEXT NOT NULL,
                target_id    INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason       TEXT,
                duration     TEXT,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS timed_mutes (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id   INTEGER NOT NULL,
                user_id    INTEGER NOT NULL,
                role_id    INTEGER NOT NULL,
                expires_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS permission_snapshots (
                guild_id      INTEGER NOT NULL,
                channel_id    INTEGER NOT NULL,
                snapshot_type TEXT NOT NULL,
                send_messages INTEGER,
                PRIMARY KEY (guild_id, channel_id, snapshot_type)
            );
            CREATE TABLE IF NOT EXISTS notes (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id  INTEGER NOT NULL,
                user_id   INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                content   TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS banned_words (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id   INTEGER NOT NULL,
                word       TEXT NOT NULL,
                match_mode TEXT DEFAULT 'contains'
            );
            CREATE TABLE IF NOT EXISTS automod_ignored (
                guild_id  INTEGER NOT NULL,
                type      TEXT NOT NULL,
                target_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, type, target_id)
            );
            CREATE TABLE IF NOT EXISTS automod_links (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id  INTEGER NOT NULL,
                link      TEXT NOT NULL,
                list_type TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS lockdown_channels (
                guild_id   INTEGER NOT NULL,
                channel_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, channel_id)
            );
        """)
        for sql in [
            "ALTER TABLE mod_actions ADD COLUMN case_number INTEGER",
            "ALTER TABLE guild_settings ADD COLUMN mute_role_id INTEGER",
        ]:
            try:
                conn.execute(sql)
            except Exception:
                pass

def next_case_number(conn: sqlite3.Connection, guild_id: int) -> int:
    """Atomically increment and return the next case number for a guild."""
    conn.execute(
        "INSERT OR IGNORE INTO guild_case_seq (guild_id, next_case) VALUES (?, 1)",
        (guild_id,)
    )
    conn.execute(
        "UPDATE guild_case_seq SET next_case = next_case + 1 WHERE guild_id = ?",
        (guild_id,)
    )
    return conn.execute(
        "SELECT next_case - 1 FROM guild_case_seq WHERE guild_id = ?",
        (guild_id,)
    ).fetchone()[0]

def get_guild_settings(guild_id: int) -> sqlite3.Row | None:
    with get_db() as conn:
        return conn.execute(
            "SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)
        ).fetchone()

def ensure_guild_settings(guild_id: int) -> sqlite3.Row:
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO guild_settings (guild_id) VALUES (?)", (guild_id,)
        )
    return get_guild_settings(guild_id)

# permission_snapshots helpers
_SM_ENCODE = {None: -1, True: 1, False: 0}
_SM_DECODE = {-1: None, 1: True, 0: False}

def save_permission_snapshot(guild_id: int, channel_id: int, snapshot_type: str, send_messages):
    with get_db() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO permission_snapshots (guild_id, channel_id, snapshot_type, send_messages) VALUES (?, ?, ?, ?)",
            (guild_id, channel_id, snapshot_type, _SM_ENCODE.get(send_messages, -1))
        )

def pop_permission_snapshot(guild_id: int, channel_id: int, snapshot_type: str):
    """Returns the saved send_messages value and removes the snapshot."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT send_messages FROM permission_snapshots WHERE guild_id = ? AND channel_id = ? AND snapshot_type = ?",
            (guild_id, channel_id, snapshot_type)
        ).fetchone()
        conn.execute(
            "DELETE FROM permission_snapshots WHERE guild_id = ? AND channel_id = ? AND snapshot_type = ?",
            (guild_id, channel_id, snapshot_type)
        )
    if row is None:
        return None
    return _SM_DECODE.get(row["send_messages"], None)