# BlanketBot

A Discord moderation and logging bot

---

## Requirements

- Python 3.12+
- discord.py 2.7.1+
- python-dotenv 1.2.2+
- A Working Computer

```
pip install -r requirements.txt
```

---
## Setup (Docker)

1. Create a bot at [discord.com/developers/applications](https://discord.com/developers/applications)
2. Under **Bot**, enable: **Server Members Intent**, **Message Content Intent**
3. Under **OAuth2 → URL Generator**, select scopes: `bot`, `applications.commands`
4. Select permissions: Manage Roles, Manage Channels, Kick Members, Ban Members, Moderate Members, Manage Messages, Read Message History, View Audit Log
5. Copy `.env.example` to `.env` and fill in your token
6. Run: `docker compose up -d`

## Setup

1. Create a bot at [discord.com/developers/applications](https://discord.com/developers/applications)
2. Under **Bot**, enable: **Server Members Intent**, **Message Content Intent**
3. Under **OAuth2 → URL Generator**, select scopes: `bot`, `applications.commands`
4. Select permissions: Manage Roles, Manage Channels, Kick Members, Ban Members, Moderate Members, Manage Messages, Read Message History, View Audit Log
5. Copy `.env.example` to `.env` and fill in your token
6. Run: `python3 bot.py`

---

## Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN` | Yes | Your bot token |
| `LOG_CHANNEL_ID` | No | Fallback log channel ID if a guild hasn't run `?settings logchannel` |

---

## First-Time Setup

Run these after inviting the bot.

```
?settings logchannel #mod-log        set log channel
?muterole create                     create the Muted role
?staff mod add @Moderator            give a role access to mod commands
?staff admin add @Admin              give a role access to admin commands
?lockdown channel add #general       add channels to the lockdown list (repeat as needed)
?automod on                          enable automod (off by default)
```

---

## Command Reference

Prefix: `?`  
Moderation commands also have `/` slash equivalents.  
Admin commands are prefix-only.

---

### Moderation

| Command | Description |
|---|---|
| `?kick @user [reason]` | Kick a member |
| `?ban @user [reason]` | Ban a member |
| `?unban <user_id> [reason]` | Unban a user by ID |
| `?softban @user [reason]` | Ban + immediately unban (deletes 7 days of messages) |
| `?mute @user [duration] [reason]` | Mute using the mute role. |
| `?unmute @user` | Remove mute role (and clear timeout if present) |
| `?warn @user <reason>` | Issue a warning |
| `?warndel <#id>` | Delete a warning by its ID |
| `?warnings @user` | View all warnings for a member |
| `?clearwarnings @user` | Clear all warnings (admin only) |

Duration format: `10s`, `5m`, `2h`, `1d`, `1day`, `30mins`, etc.

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
| `?channel unlock [#channel]` | Unlock a channel |
| `?channel slowmode <seconds> [#channel]` | Set slowmode (0 to disable) |

**Purge filters:** `user @user`, `match <text>`, `not <text>`, `startswith <text>`, `endswith <text>`, `links`, `invites`, `images`, `mentions`, `embeds`, `bots`, `humans`, `text`  
Default (no filter): deletes up to 100 recent messages.

---

### Case History

| Command | Description |
|---|---|
| `?modlogs <@user\|user_id>` | View mod history for a user (works with Discord user ID for imported / left users) |
| `?modstats [@mod]` | Mod action stats. Omit mod for server-wide stats. |
| `?case <number>` | Look up a specific case by number |
| `?whois [@user]` | User profile: roles, join date, warning count, recent cases |

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

Automod is disabled by default. Enable it with `?automod on`.

| Command | Description |
|---|---|
| `?automod` | View automod status |
| `?automod on / off` | Enable or disable automod |
| `?automod antispam on/off` | Toggle spam detection |
| `?automod anticaps on/off` | Toggle caps filter |
| `?automod antiinvite on/off` | Toggle Discord invite blocking |
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

---

### Admin - Lockdown

| Command | Description |
|---|---|
| `?lockdown enable [reason]` | Deny @everyone send messages in all configured channels |
| `?lockdown disable [reason]` | Restore send messages in all configured channels |
| `?lockdown status` | Show locked/unlocked state per channel |
| `?lockdown channel add #channel` | Add a channel to the lockdown list |
| `?lockdown channel remove #channel` | Remove a channel from the lockdown list |
| `?lockdown channel list` | List all lockdown channels |

---

## Permissions Required

| Permission | Used for |
|---|---|
| Manage Roles | Mute role assignment |
| Manage Channels | Channel lock, lockdown, slowmode, mute role setup |
| Kick Members | Kick |
| Ban Members | Ban, unban, softban |
| Moderate Members | Discord timeout fallback |
| Manage Messages | Purge, automod message deletion |
| Read Message History | Purge |
| View Audit Log | (optional) Audit log features |

---

# Credits

- **K1ngblanket**
- **LaiZBoi**
