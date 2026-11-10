# BlanketBot

A Discord moderation and logging bot

---

## Requirements

- Python 3.12+
- discord.py 2.7.1+
- python-dotenv 1.2.2+
- aiohttp, Pillow, pytesseract, python-Levenshtein (scam detection)
- Tesseract OCR installed on the host (`apt install tesseract-ocr`), not needed with Docker
- A Working Computer

```
pip install -r requirements.txt
```

---
## Setup (Docker)

1. Create a bot at [discord.com/developers/applications](https://discord.com/developers/applications)
2. Under **Bot**, enable: **Server Members Intent**, **Message Content Intent**
3. Under **OAuth2 → URL Generator**, select scopes: `bot`, `applications.commands`
4. Select permissions: Manage Roles, Manage Channels, Kick Members, Ban Members, Moderate Members, Manage Messages, Read Message History, Attach Files, View Audit Log
5. Copy `.env.example` to `.env` and fill in your token
6. Run: `docker compose up -d`

The image includes Tesseract. The project folder is mounted at `/data`, so `bot.db` and `scam_hashes.txt` are created in the project folder and survive rebuilds. After pulling code or dependency changes, rebuild with `docker compose up -d --build`. View logs with `docker compose logs -f bot`.

## Setup

1. Create a bot at [discord.com/developers/applications](https://discord.com/developers/applications)
2. Under **Bot**, enable: **Server Members Intent**, **Message Content Intent**
3. Under **OAuth2 → URL Generator**, select scopes: `bot`, `applications.commands`
4. Select permissions: Manage Roles, Manage Channels, Kick Members, Ban Members, Moderate Members, Manage Messages, Read Message History, Attach Files, View Audit Log
5. Copy `.env.example` to `.env` and fill in your token
6. Install Tesseract OCR with your package manager
7. Run: `python3 bot.py`

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN` | Yes | Your bot token |
| `LOG_CHANNEL_ID` | No | Fallback log channel ID if a guild hasn't run `?settings logchannel` |
| `DB_PATH` | No | Path to the SQLite database. Defaults to `bot.db`. Docker sets `/data/bot.db`. The scam hash file is stored in the same folder. |

---

## First-Time Setup

Run these after inviting the bot.

```
?settings logchannel #mod-log        set log channel
?muterole create                     create the Muted role
?memberrole set @Member              choose the role given by ?memberrole give
?staff mod add @Moderator            give a role access to mod commands
?staff admin add @Admin              give a role access to admin commands
?lockdown channel add #general       add channels to the lockdown list (repeat as needed)
?automod on                          enable automod (off by default)
```

---

## Command Reference

Prefix: `?`  
Moderation commands also have `/` slash equivalents. Staff roles work with both.  
Admin commands are prefix-only.

---

### Moderation

| Command | Description |
|---|---|
| `?kick @user [reason]` | Kick a member |
| `?ban @user\|<user_id> [reason]` | Ban a member, or any user by ID including users who have left. Deletes the last 12 hours of their messages and sends them a DM with the reason. |
| `?unban <user_id> [reason]` | Unban a user by ID |
| `?softban @user [reason]` | Ban + immediately unban (deletes 7 days of messages) |
| `?mute @user [duration] [reason]` | Mute using the mute role. Duration is optional. Timed mutes survive bot restarts. Without a mute role, a duration is required and a Discord timeout is used. |
| `?unmute @user` | Remove mute role (and clear timeout if present) |
| `?warn @user <reason>` | Issue a warning |
| `?warndel <#id>` | Delete a warning by its ID |
| `?warnings @user` | View all warnings for a member |
| `?clearwarnings @user` | Clear all warnings (admin only) |
| `?memberrole give @user` | Give a member the configured member role |

Duration format: `10s`, `5m`, `2h`, `1d`, `1day`, `30mins`, etc.

Slash equivalents: `/kick`, `/ban`, `/unban`, `/mute`, `/unmute`, `/softban`, `/warn`, `/warndel`, `/warnings`, `/clearwarnings`, `/memberrole`.

---

### Notes & Tools

| Command | Description |
|---|---|
| `?note add @user <text>` | Add a staff note |
| `?note list @user` | List notes for a member |
| `?note edit <#id> <text>` | Edit a note |
| `?note del <#id>` | Delete a note |
| `?purge [filter] [args]` | Bulk delete messages (see filters below) |
| `?channel lock [#channel]` | Lock a channel (deny @everyone send messages) |
| `?channel unlock [#channel]` | Unlock a channel, restoring its previous permission state |
| `?channel slowmode <seconds> [#channel]` | Set slowmode (0 to disable) |

**Purge filters:** `user @user`, `match <text>`, `not <text>`, `startswith <text>`, `endswith <text>`, `links`, `invites`, `images`, `mentions`, `embeds`, `bots`, `humans`, `text`  
Default (no filter): deletes up to 100 recent messages. Messages older than 14 days are skipped.

Slash equivalents: `/note`, `/notes`, `/notedel`, `/purge`, `/lock`, `/unlock`, `/slowmode`.

---

### Case History

| Command | Description |
|---|---|
| `?modlogs @user\|<user_id>` | View mod history for a user, including users who have left |
| `?modstats [@mod]` | Mod action stats. Omit mod for server-wide stats. |
| `?case <number>` | Look up a specific case by number |
| `?whois [@user]` | User profile: roles, join date, warning count, recent cases |

Slash equivalents: `/modlogs`, `/modstats`, `/case`, `/whois`.

Case numbers are assigned per server from an atomic counter. Every moderation action, including purge, lock, unlock and lockdown, is written to the case history and posted to the log channel.

---

### Info

| Command | Description |
|---|---|
| `?info server` | Server info (member count, roles, boost level, creation date) |
| `?info channel [#channel]` | Channel info |
| `?help` | Command list |
| `?about` | Bot info |

---

### Admin - Settings

| Command | Description |
|---|---|
| `?settings` | View current guild settings |
| `?settings logchannel #channel` | Set the mod log channel |
| `?settings logchannel off` | Clear the mod log channel |

---

### Admin - Mute Role

| Command | Description |
|---|---|
| `?muterole` | View current mute role |
| `?muterole create` | Create a Muted role and apply deny permissions to all text channels |
| `?muterole set @role` | Use an existing role as the mute role |
| `?muterole off` | Clear mute role (mutes fall back to Discord timeout) |

The mute role must sit below the bot's highest role.

---

### Admin - Member Role

| Command | Description |
|---|---|
| `?memberrole` | View the current member role |
| `?memberrole set @role` | Use an existing role as the member role |
| `?memberrole off` | Clear the member role |
| `?memberrole give @user` | Give a member the member role (moderator) |
| `/memberrole @user` | Slash equivalent of `give` |

The member role must sit below the bot's highest role. Moderators can only assign it if it is below their own highest role. Admins and the server owner are exempt from that check.

---

### Admin - Staff Roles

Staff roles grant members access to mod/admin commands even without the corresponding Discord permission.

| Command | Description |
|---|---|
| `?staff mod add @role` | Add a moderator role |
| `?staff mod del @role` | Remove a moderator role |
| `?staff mod list` | List moderator roles |
| `?staff admin add @role` | Add an admin role |
| `?staff admin del @role` | Remove an admin role |
| `?staff admin list` | List admin roles |

---

### Admin - Automod

Automod is disabled by default. Enable it with `?automod on`. Members with a moderator or admin role, and members or channels on the ignore lists, are skipped.

| Command | Description |
|---|---|
| `?automod` | View automod status |
| `?automod on / off` | Enable or disable automod |
| `?automod antispam on/off` | Toggle spam detection |
| `?automod anticaps on/off` | Toggle caps filter |
| `?automod antiinvite on/off` | Toggle invite blocking (Discord invites and Telegram links) |
| `?automod antimention on/off` | Toggle mass mention protection |
| `?automod word add contains\|exact <word,...>` | Add banned words (comma-separated) |
| `?automod word del <#id or text>` | Remove a banned word by ID or value |
| `?automod word list` | List banned words |
| `?automod blacklist add <domain,...>` | Block domains/URLs |
| `?automod blacklist remove <domain>` | Remove a blacklisted domain |
| `?automod blacklist list` | List blacklisted domains |
| `?automod whitelist add <domain,...>` | Whitelist domains (bypass blacklist) |
| `?automod whitelist remove <domain>` | Remove a whitelisted domain |
| `?automod whitelist list` | List whitelisted domains |
| `?automod ignore channel add #channel` | Exclude a channel from automod |
| `?automod ignore channel remove #channel` | Re-include a channel |
| `?automod ignore channel list` | List ignored channels |
| `?automod ignore role add @role` | Exclude a role from automod |
| `?automod ignore role remove @role` | Re-include a role |
| `?automod ignore role list` | List ignored roles |
| `?automod ignored` | View all ignored channels and roles |
| `?automod threshold show` | View current thresholds |
| `?automod threshold reset caps\|spam\|mentions\|all` | Reset thresholds to defaults |
| `?automod threshold spam-count <n>` | Messages before spam trigger (3–20) |
| `?automod threshold spam-window <s>` | Spam detection window in seconds (1–60) |
| `?automod threshold caps <n>` | Caps percentage to trigger filter (50–100) |
| `?automod threshold mentions <n>` | Mention count to trigger filter (2–50) |

Links are allowed by default. Add domains to the blacklist to block them. The whitelist exempts a domain from the blacklist. Invite blocking is separate and does not depend on the blacklist.

Removed messages get a generic notice. The matched word is not shown to the user.

---

### Admin - Lockdown

| Command | Description |
|---|---|
| `?lockdown enable [reason]` | Deny @everyone send messages in all configured channels |
| `?lockdown disable [reason]` | Restore each channel's previous send messages setting |
| `?lockdown status` | Show locked/unlocked state per channel |
| `?lockdown channel add #channel` | Add a channel to the lockdown list |
| `?lockdown channel remove #channel` | Remove a channel from the lockdown list |
| `?lockdown channel list` | List all lockdown channels |

The previous permission state is saved when a channel is locked and restored on unlock. Locking a channel that is already locked does not overwrite the saved state.

---

## Scam Image Detection

Every image attachment from a non-bot user is downloaded and scanned with Tesseract OCR. The recognized text is compared against a list of scam keywords using fuzzy matching. When enough keywords match, the bot:

1. Times the user out for 60 seconds
2. Forwards the original message to the log channel
3. Deletes the message
4. Posts an analysis embed with the matched words and score

Images from detected scam messages are hashed with SHA-256 and saved to `scam_hashes.txt`, next to the database. A later message containing an image with a known hash is removed immediately without running OCR. The hash list is loaded into memory at startup.

Scam detection needs no configuration. Alerts go to the server's log channel.

---

## Logging

The log channel receives mod action cases, member joins and leaves, message edits and message deletions. Deleted messages that contained images are logged with the images attached. Image bytes are cached in memory for the 500 most recent image messages, so images from before a bot restart cannot be recovered.

---

## Importing Dyno Cases

`scripts/import_dyno.py` imports a Dyno moderation case export into the database. Warn cases are also written to the warnings table.

```
python scripts/import_dyno.py --guild-id <id> --json dyno-cases.json --dry-run
python scripts/import_dyno.py --guild-id <id> --json dyno-cases.json --mod-map scripts/mod_id_map.json
```

Dyno exports moderator names, not IDs. Fill in `scripts/mod_id_map.json` with Discord user IDs to link imported cases to real accounts. Names left as `null` are imported with the display name only. Use `--db <path>` to target a database other than the default.

---

## Tests

```
pip install pytest
python -m pytest tests/
```

---

## Permissions Required

| Permission | Used for |
|---|---|
| Manage Roles | Mute role and member role assignment |
| Manage Channels | Channel lock, lockdown, slowmode, mute role setup |
| Kick Members | Kick |
| Ban Members | Ban, unban, softban |
| Moderate Members | Discord timeout (scam detection, mute fallback) |
| Manage Messages | Purge, automod and scam message deletion |
| Read Message History | Purge |
| Attach Files | Deleted image logs |
| View Audit Log | (optional) Audit log features |

---

# Credits

- **K1ngblanket**
- **LaiZBoi**
- **Tilley8**