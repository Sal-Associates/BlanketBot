-- Strike escalation tracking and note revisions

CREATE TABLE IF NOT EXISTS strike_escalation_state (
    guild_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    last_mute_at_count INTEGER NOT NULL DEFAULT 0,
    last_ban_at_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS note_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    note_id INTEGER NOT NULL,
    guild_id TEXT NOT NULL,
    author_id TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    FOREIGN KEY (note_id) REFERENCES notes (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_note_revisions_note ON note_revisions (note_id);
