# Python Feature Parity

**Status:** Production implementation in `python/`.  
**Legacy reference:** JavaScript/Bun project in `node-bun/` (`node-bun/src/`, `node-bun/data/store.json`).

This document maps the legacy JavaScript moderation bot to the Python implementation and records behavioral parity decisions.

---

## Stack

| Area | JavaScript (legacy) | Python (production) |
|------|---------------------|---------------------|
| Runtime | Bun | Python 3.12+ |
| Discord API | discord.js | discord.py 2.x |
| Persistence | `node-bun/data/store.json` | SQLite (`python/data/modbot.sqlite3`) |
| Commands | Prefix only | Prefix only |
| Deployment scope | Single guild (`GUILD_ID`) | Single guild (`GUILD_ID`) |

---

## Architecture

| Concern | JavaScript | Python |
|---------|----------|--------|
| Bootstrap | `node-bun/src/index.js` | `bot/__main__.py`, `bot/client.py` |
| Configuration | `.env` + `node-bun/src/utils/guild.js` | `bot/config.py`, `bot/services/guild_guard.py` |
| Authorization | `node-bun/src/utils/permissions.js`, `checks.js` | `bot/services/authorization.py`, `bot/checks/` |
| Hierarchy | `node-bun/src/utils/permissions.js` | `bot/services/hierarchy.py` |
| Business logic | handlers + utils | `bot/services/`, `bot/automod/` |
| Persistence | `node-bun/src/database/db.js` | `bot/database/repositories/`, `migrations/` |
| Scheduler | `node-bun/src/handlers/scheduler.js`, `timedActions.js` | `bot/scheduler/` |
| Commands | `node-bun/src/commands/**` | `bot/cogs/**` |

---

## Data model changes

| Legacy JSON | Python SQLite | Notes |
|-------------|---------------|-------|
| `mod_logs` | *(not imported)* | Cases are the sole internal history |
| `guild_settings.lockdown_state` | `lockdown_operations` + `lockdown_channel_snapshots` | Normalized state machine |
| `guild_settings.lockdown_channels` | `lockdown_channels` | Per-guild channel list |
| `automod_words` | `banned_words` | Importer merges legacy rows |
| `automod_enabled` | `disabled_modules` | Importer migrates `automod_enabled: 0` → `Automod` disabled |
| Warning delete | `warnings.status = voided` | Cases remain immutable |
| Case `extra` | `cases.metadata_json` | Same linkage fields preserved |

---

## Feature parity matrix

| Feature | JS reference | Python module | Parity |
|---------|--------------|---------------|--------|
| Single-guild guard | `guild.js` | `guild_guard.py` | Yes |
| SQLite migrations | N/A | `migrations/`, `database/migrations.py` | Yes |
| Staff roles | `staff.js`, `db.js` | `staff_roles.py`, `authorization.py` | Yes |
| Prefix config | `prefix.js` | `prefix.py` | Yes |
| Module master switch (`Automod`) | `module.js`, `db.js` | `guild_settings.py` | Yes |
| Mod-log channel notifications | `modLog.js` | `mod_log.py` | Yes |
| Mod queue | `modQueue.js` | `mod_queue.py` (repo), automod handler | Yes |
| Warnings + cases | `warn.js`, `db.js` | `warnings.py`, `cases.py` | Yes |
| Notes + revisions | `note.js` | `notes.py` | Yes |
| Strike escalation | `strikes.js` | `strikes.py`, `strike_state.py` | Yes |
| Core moderation | `mod.js` | `moderation.py` | Yes |
| Temporary ban/mute | `db.js`, `timedActions.js` | `timed_actions.py`, `moderation.py` | Yes |
| Channel lock/unlock/slowmode | `channel.js` | channel cogs + `timed_actions.py` | Yes |
| Server lockdown | `lockdownHandler.js` | `lockdown.py` (service + repo) | Yes |
| Automod thresholds | `automodThresholds.js` | `automod/thresholds.py` | Yes |
| Banned words | `bannedWords.js` | `automod/banned_words.py`, `banned_words.py` | Yes |
| Automod ignore lists | `automodIgnore.js` | `automod/ignore.py`, `automod.py` | Yes |
| Link lists | `db.js` | `automod.py` | Yes |
| Spam tracker (in-memory) | `automodHandler.js` | `automod/spam_tracker.py` | Yes |
| Purge | `purge.js` | `cogs/moderation/purge.py` | Planned / partial |
| Audit sync | `audit.js` | `cogs/moderation/audit.py` | Planned / partial |
| Info commands | `info/*.js` | `cogs/info/` | Planned / partial |
| Legacy JSON import | N/A | `scripts/import_legacy_json.py` | Yes |

---

## Behavioral notes (intentional parity)

1. **Superusers** receive command authorization but do not bypass Discord role hierarchy.
2. **Cases** are append-only; voiding warnings does not delete cases.
3. **Mod-log channel** failures do not roll back persisted cases.
4. **Spam tracker** is in-memory and resets on process restart.
5. **`mod_logs`** in legacy JSON are skipped during import; Discord mod-log channel remains the live notification surface.
6. **Caps minimum letter count** is fixed at 8 (not configurable).
7. **Lockdown** restores prior `SendMessages` states unless manually changed during lockdown.

---

## Verification

Python tests in `python/tests/` port the behavioral checks from `node-bun/scripts/verify-*.mjs`:

| JS verifier | Python tests |
|-------------|--------------|
| `verify-moderation.mjs` | `test_hierarchy.py`, `test_authorization.py` |
| `verify-database.mjs` | `test_database.py`, `test_prefix.py` |
| `verify-moderation-workflows.mjs` | `test_moderation.py`, `test_mod_queue.py` |
| `verify-cases-consolidation.mjs` | `test_warnings_cases.py` |
| `verify-timed-channel.mjs` | `test_timed_actions.py` |
| `verify-lockdown.mjs` | `test_lockdown.py` |
| `verify-banned-words.mjs` | `test_banned_words.py` |
| `verify-automod-module.mjs` | `test_automod.py` |
| `verify-automod-thresholds.mjs` | `test_automod.py` |
| Legacy import | `test_importer.py` |

Run:

```bash
cd python
python -m pytest
ruff check .
```

---

## Legacy import

One-time migration from `node-bun/data/store.json`:

```bash
cd python
python scripts/import_legacy_json.py --dry-run
python scripts/import_legacy_json.py --source ../node-bun/data/store.json
```

The importer never modifies the source JSON, backs up an existing SQLite file, validates structure, skips `mod_logs`, and prints a summary report.
