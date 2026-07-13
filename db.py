import sqlite3
from contextlib import contextmanager

DB_PATH = "bot.db"

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