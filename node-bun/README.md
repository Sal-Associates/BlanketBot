# Discord Mod Bot (Node/Bun — legacy reference)

**Legacy reference implementation.** This is the original JavaScript/Bun moderation bot, retained for behavior comparison and migration validation. **Do not use for new production deployments** — use [`../python/`](../python/) instead.

## Requirements

- [Bun](https://bun.sh)
- A Discord bot token with **Message Content Intent** enabled
- A target guild ID (`GUILD_ID`)

## Setup

```bash
cd node-bun
bun install
cp .env.example .env
# Edit .env — set DISCORD_TOKEN and GUILD_ID
```

## Run

```bash
bun start
```

Dev mode with auto-reload:

```bash
bun run dev
```

## Tests

```bash
bun run test
```

This runs `scripts/verify-moderation-workflows.mjs`, which exercises moderation workflows, automod, lockdown, and related behavior.

## Database

Runtime data is stored in:

```text
node-bun/data/store.json
```

Override the path with the `STORE_PATH` environment variable. Atomic writes use `.tmp` / `.bak` files alongside the store.

## Environment

| Variable | Required | Description |
|----------|----------|-------------|
| `DISCORD_TOKEN` | Yes | Bot token |
| `GUILD_ID` | Yes | Managed server snowflake |
| `SUPERUSER_IDS` | No | Comma-separated user IDs |
| `STORE_PATH` | No | Override JSON store path (tests) |

## Command reference

See [`COMMANDS.md`](COMMANDS.md) for the full prefix-command reference.

## Relationship to Python

The production bot lives in [`../python/`](../python/). It uses SQLite and the same command surface. To import this JSON store into Python SQLite:

```bash
cd ../python
python scripts/import_legacy_json.py --dry-run
python scripts/import_legacy_json.py --source ../node-bun/data/store.json
```

The importer never modifies `node-bun/data/store.json`.
