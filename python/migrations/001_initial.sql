-- Initial schema for Python moderation bot (Stage 1)
-- Idempotent: uses IF NOT EXISTS throughout

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id TEXT PRIMARY KEY NOT NULL,
    prefix TEXT NOT NULL DEFAULT '?',
    mod_log_channel_id TEXT,
    mod_queue_channel_id TEXT,
    mod_queue_enabled INTEGER NOT NULL DEFAULT 0,
    mute_role_id TEXT,
    strike_enabled INTEGER NOT NULL DEFAULT 1,
    strike_mute_at INTEGER NOT NULL DEFAULT 3,
    strike_ban_at INTEGER NOT NULL DEFAULT 5,
    anti_spam INTEGER NOT NULL DEFAULT 1,
    anti_caps INTEGER NOT NULL DEFAULT 0,
    anti_invite INTEGER NOT NULL DEFAULT 0,
    anti_mention INTEGER NOT NULL DEFAULT 0,
    caps_threshold INTEGER NOT NULL DEFAULT 70,
    spam_threshold INTEGER NOT NULL DEFAULT 5,
    spam_interval_ms INTEGER NOT NULL DEFAULT 5000,
    mention_threshold INTEGER NOT NULL DEFAULT 5,
    disabled_modules TEXT NOT NULL DEFAULT '[]',
    automod_module_migrated INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS staff_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    role_type TEXT NOT NULL CHECK (role_type IN ('moderator', 'administrator')),
    UNIQUE (guild_id, role_id, role_type)
);

CREATE INDEX IF NOT EXISTS idx_staff_roles_guild ON staff_roles (guild_id);

CREATE TABLE IF NOT EXISTS warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    moderator_id TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    source TEXT,
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'voided')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_warnings_guild_user ON warnings (guild_id, user_id);
CREATE INDEX IF NOT EXISTS idx_warnings_status ON warnings (guild_id, status);

CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    author_id TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_notes_guild_user ON notes (guild_id, user_id);

CREATE TABLE IF NOT EXISTS case_counters (
    guild_id TEXT PRIMARY KEY NOT NULL,
    next_case_number INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS cases (
    guild_id TEXT NOT NULL,
    case_number INTEGER NOT NULL,
    user_id TEXT NOT NULL,
    moderator_id TEXT NOT NULL,
    action TEXT NOT NULL,
    reason TEXT,
    source TEXT,
    status TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    PRIMARY KEY (guild_id, case_number)
);

CREATE INDEX IF NOT EXISTS idx_cases_guild_user ON cases (guild_id, user_id);
CREATE INDEX IF NOT EXISTS idx_cases_guild_created ON cases (guild_id, created_at);

CREATE TABLE IF NOT EXISTS timed_actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    action TEXT NOT NULL,
    user_id TEXT,
    channel_id TEXT,
    role_id TEXT,
    permission TEXT,
    previous_state TEXT,
    applied_state TEXT,
    ends_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_retry_at TEXT,
    last_error TEXT,
    last_logged_error TEXT,
    moderator_id TEXT,
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_timed_actions_due ON timed_actions (status, ends_at);
CREATE INDEX IF NOT EXISTS idx_timed_actions_guild ON timed_actions (guild_id);

CREATE TABLE IF NOT EXISTS mod_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    author_id TEXT NOT NULL,
    message_id TEXT,
    queue_message_id TEXT,
    content TEXT,
    reason TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    moderator_id TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    resolved_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_mod_queue_guild_status ON mod_queue (guild_id, status);

CREATE TABLE IF NOT EXISTS banned_words (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    value TEXT NOT NULL,
    match_mode TEXT NOT NULL CHECK (match_mode IN ('contains', 'exact')),
    created_by TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE (guild_id, value, match_mode)
);

CREATE INDEX IF NOT EXISTS idx_banned_words_guild ON banned_words (guild_id);

CREATE TABLE IF NOT EXISTS automod_ignored_channels (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    UNIQUE (guild_id, channel_id)
);

CREATE TABLE IF NOT EXISTS automod_ignored_roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    role_id TEXT NOT NULL,
    UNIQUE (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS automod_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    link TEXT NOT NULL,
    list_type TEXT NOT NULL CHECK (list_type IN ('blacklist', 'whitelist')),
    UNIQUE (guild_id, link, list_type)
);

CREATE TABLE IF NOT EXISTS lockdown_channels (
    guild_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    PRIMARY KEY (guild_id, channel_id)
);

CREATE TABLE IF NOT EXISTS lockdown_operations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0,
    disabling INTEGER NOT NULL DEFAULT 0,
    started_at TEXT,
    started_by TEXT,
    reason TEXT,
    disabled_at TEXT,
    disabled_by TEXT,
    disable_reason TEXT,
    role_id TEXT,
    permission TEXT NOT NULL DEFAULT 'SendMessages',
    metadata_json TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_lockdown_ops_guild_active ON lockdown_operations (guild_id, active);

CREATE TABLE IF NOT EXISTS lockdown_channel_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation_id INTEGER NOT NULL,
    channel_id TEXT NOT NULL,
    previous_state TEXT,
    applied_state TEXT,
    result TEXT,
    disable_result TEXT,
    error TEXT,
    FOREIGN KEY (operation_id) REFERENCES lockdown_operations (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_lockdown_snapshots_op ON lockdown_channel_snapshots (operation_id);
