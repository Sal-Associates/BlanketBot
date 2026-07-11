# Discord Mod Bot

A moderation-focused Discord bot with prefix commands (`?` by default). This repository contains **two independent implementations** of the same bot.

| Directory | Role | Stack |
|-----------|------|-------|
| [`python/`](python/) | **Production** — recommended for deployment | Python 3.12+, discord.py, SQLite |
| [`node-bun/`](node-bun/) | **Legacy reference** — behavior comparison only | JavaScript, Bun, JSON store |

The projects are separate: each has its own dependencies, environment file, runtime data, and README. They do not share a monorepo package manager.

## Quick start (Python — production)

```bash
cd python
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Set DISCORD_TOKEN and GUILD_ID
python -m bot
```

See [`python/README.md`](python/README.md) for migrations, tests, Ruff, and the legacy JSON importer.

## Quick start (Node/Bun — legacy reference)

```bash
cd node-bun
bun install
cp .env.example .env
# Set DISCORD_TOKEN and GUILD_ID
bun start
```

See [`node-bun/README.md`](node-bun/README.md) for tests and JSON database details.

## Shared documentation

- [`docs/PYTHON_MIGRATION_PLAN.md`](docs/PYTHON_MIGRATION_PLAN.md) — migration history (complete)
- [`docs/PYTHON_FEATURE_PARITY.md`](docs/PYTHON_FEATURE_PARITY.md) — feature parity matrix
- [`PLAN.md`](PLAN.md) — original conversion specification
- [`node-bun/COMMANDS.md`](node-bun/COMMANDS.md) — command quick reference

## Data locations

- **Python:** SQLite at `python/data/modbot.sqlite3` (configurable via `DATABASE_PATH`)
- **Node/Bun:** JSON at `node-bun/data/store.json`

To migrate legacy JSON into SQLite, run the Python importer from `python/` (see `python/README.md`). It does not modify the Node/Bun source file.
