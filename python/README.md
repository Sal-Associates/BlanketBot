# Discord Mod Bot (Python)

**Production** moderation bot for Discord. Uses Python 3.12+, [discord.py](https://discordpy.readthedocs.io/), and SQLite.

The legacy JavaScript/Bun implementation in [`../node-bun/`](../node-bun/) remains available as a **reference** for behavior comparison. New deployments should use this Python stack.

## Requirements

- Python 3.12+
- A Discord bot token with **Message Content Intent** enabled
- A target guild ID (`GUILD_ID`)

## Setup

```bash
cd python
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix: source .venv/bin/activate
pip install -r requirements.txt
# or: pip install -e ".[dev]"
```

## Configuration

```bash
cp .env.example .env
```

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_TOKEN` | Yes | Bot token from the Discord Developer Portal |
| `GUILD_ID` | Yes | 17–20 digit snowflake for the managed server |
| `SUPERUSER_IDS` | No | Comma-separated user IDs with full mod/admin command access |
| `DATABASE_PATH` | No | SQLite path (default: `data/modbot.sqlite3`) |

## Run

```bash
python -m bot
```

Migrations run automatically on startup before the Discord client connects.

## Database

Runtime data defaults to:

```text
python/data/modbot.sqlite3
```

Set `DATABASE_PATH` in `.env` to override.

## Legacy data import

One-time import from the Node/Bun JSON store (read-only on source file):

```bash
# Preview without writing
python scripts/import_legacy_json.py --dry-run

# Import using default source (../node-bun/data/store.json)
python scripts/import_legacy_json.py

# Explicit source path
python scripts/import_legacy_json.py --source ../node-bun/data/store.json
```

The importer:

- Validates JSON structure before writing
- Backs up an existing SQLite database
- Skips deprecated `mod_logs` records
- Never modifies the Node/Bun JSON source
- Prints a summary report

Use `--force` to import into a database that already contains guild settings.

## Development

```bash
python -m pytest
ruff check .
ruff format --check .
python -m compileall bot
```

### Test coverage

Tests in `tests/` port behavioral checks from the legacy `node-bun/scripts/verify-*.mjs` suite.

## Project layout

```text
python/
├── bot/                 # Application package (`python -m bot`)
├── migrations/          # SQL schema migrations
├── scripts/             # import_legacy_json.py
├── tests/               # pytest suite
├── data/                # SQLite runtime data (gitignored)
├── pyproject.toml
└── requirements.txt
```

## Documentation

- Feature parity: [`docs/PYTHON_FEATURE_PARITY.md`](../docs/PYTHON_FEATURE_PARITY.md)
- Migration history: [`docs/PYTHON_MIGRATION_PLAN.md`](../docs/PYTHON_MIGRATION_PLAN.md)
- Commands: [`node-bun/COMMANDS.md`](../node-bun/COMMANDS.md)
