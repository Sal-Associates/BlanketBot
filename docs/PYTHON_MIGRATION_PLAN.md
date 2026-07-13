# Python Migration Plan

**Status:** Complete — Python implementation in `python/` is production.  
**Reference implementation:** JavaScript/Bun project in `node-bun/` (`node-bun/src/`, `node-bun/data/store.json`) — legacy, retained for behavior comparison only.  
**Production stack:** `python/` — Python 3.12+, discord.py 2.x, SQLite via aiosqlite.

> **Note:** Earlier drafts referred to `python_bot/` at the repository root and `src/` at the root. Those paths were reorganized into `python/` and `node-bun/` respectively.

---

## Principles

1. **Behavior parity** — port working JS behavior, not line-by-line translation.
2. **Thin cogs** — parse input, call services, format output.
3. **Testable services** — business logic without a live Discord connection.
4. **SQLite transactions** — replace JSON mutation queue with explicit transactions and constraints.
5. **Single-server** — `GUILD_ID` enforced on all guild-scoped events.
6. **Prefix commands only** — no slash commands during migration.
7. **Cases are history** — no `mod_logs` table; Discord mod-log channel is live notification only.

---

## Environment

| Variable | Required | Notes |
|----------|----------|-------------|
| `DISCORD_TOKEN` | Yes | Bot token |
| `GUILD_ID` | Yes | 17–20 digit snowflake |
| `SUPERUSER_IDS` | No | Comma-separated user IDs |
| `DATABASE_PATH` | No | Default `python/data/modbot.sqlite3` (relative to `python/` cwd) |

---

## Migration stages (complete)

- [x] **Stage 1** — Foundation
- [x] **Stage 2** — Authorization and basic configuration
- [x] **Stage 3** — Cases, warnings, notes
- [x] **Stage 4** — Core moderation
- [x] **Stage 5** — Timed actions and channels
- [x] **Stage 6** — Automod
- [x] **Stage 7** — Remaining commands, importer, documentation
- [x] **Repository separation** — `python/` and `node-bun/` layout

---

## Legacy JSON import

Script: `python/scripts/import_legacy_json.py`

- Read-only on source `node-bun/data/store.json` (default; override with `--source` / `--json`)
- Backup existing SQLite before import
- Skip `mod_logs`
- Summary report on completion

```bash
cd python
python scripts/import_legacy_json.py --dry-run
python scripts/import_legacy_json.py --source ../node-bun/data/store.json
```

---

## Testing strategy

```bash
cd python
python -m pytest
ruff check .
ruff format --check .
```

Legacy behavioral reference tests remain in `node-bun/scripts/verify-*.mjs`:

```bash
cd node-bun
bun run test
```

---

## Decommission criteria (met)

1. All features in the inventory are ported and tested in `python/`.
2. Legacy JSON importer verified against `node-bun/data/store.json`.
3. Production runbook in `python/README.md`.
4. Repository reorganized: production `python/`, legacy `node-bun/`.

See [`PYTHON_FEATURE_PARITY.md`](PYTHON_FEATURE_PARITY.md) for the detailed feature matrix.

