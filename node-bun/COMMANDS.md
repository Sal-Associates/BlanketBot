# Command Quick Reference

Default prefix: `?` (change with `?prefix`)

**Permissions**
- **Mod** — `Administrator`, `Moderate Members`, `Manage Messages`, or a role from `?staff mod add`
- **Admin** — `Administrator`, or a role from `?staff admin add`
- **Superuser** — Discord user IDs in `.env` `SUPERUSER_IDS` (comma-separated); full mod + admin command access on every server. Superusers still must respect issuer-target role hierarchy and the bot's role position (cannot target themselves)

---

## Admin

| Command | Who | Usage |
|---------|-----|-------|
| `staff` | Admin | `?staff mod\|admin add\|del\|list [@role]` |
| `prefix` | Admin | `?prefix [new prefix]` |
| `modlog` | Admin | `?modlog [#channel]` — live Discord notifications (not database storage) |
| `modqueue` | Admin | `?modqueue [#channel]` · `?modqueue off` · `?modqueue status` |
| `strike` | Admin | `?strike status` · `?strike set <muteAt> <banAt>` · `?strike on\|off` |
| `module` | Admin | `?module Automod` — master Automod on/off toggle |
| `modules` | Anyone | `?modules` — list module status |

---

## Moderation

| Command | Who | Usage |
|---------|-----|-------|
| `mod` | Mod | `?mod ban\|unban\|kick\|mute\|unmute\|softban\|deafen\|undeafen` |
| `warn` | Mod | `?warn add\|list\|del\|clear` |
| `note` | Mod | `?note add\|list\|edit\|del` |
| `case` | Mod | `?case <number>` · `?case list [@user]` — database case history |
| `channel` | Mod (lockdown: Admin) | `?channel lock\|unlock\|slowmode\|lockdown` |
| `audit` | Mod | `?audit <user> [limit]` — Discord native audit log |
| `purge` | Mod | `?purge [count]` or `?purge <filter> [args]` |

### `?mod` actions

```
?mod ban @user [1d] [reason]
?mod unban <userId> [reason]
?mod kick @user [reason]
?mod mute @user [1h] [reason]
?mod unmute @user [reason]
?mod softban @user [reason]
?mod deafen @user [reason]
?mod undeafen @user
```

### `?warn`

```
?warn add @user [reason]
?warn list [@user]
?warn del <id>
?warn clear @user
```

### `?note`

```
?note add @user <text>
?note list @user
?note edit <id> <text>
?note del <id>
```

### `?channel`

```
?channel lock [#channel] [duration]
?channel unlock [#channel]
?channel slowmode <seconds>
?channel lockdown channel add #channel
?channel lockdown channel remove #channel
?channel lockdown channel list
?channel lockdown enable [reason]
?channel lockdown disable [reason]
?channel lockdown status
```

**Lockdown** (Administrator only): configure which text channels participate in server lockdown. When enabled, the bot denies `SendMessages` for `@everyone` in each configured channel, stores the exact prior permission state per channel, and restores only channels whose permissions still match the bot-applied deny. Partial failures are reported with accurate counts. State survives bot restarts.

Legacy aliases: `?channel lockdown` (enable) and `?channel lockdown end` (disable).

### `?purge` filters

`user` · `match` · `not` · `startswith` · `endswith` · `links` · `invites` · `images` · `mentions` · `embeds` · `bots` · `humans` · `text`

```
?purge 50
?purge user @user 20
?purge links 10
```

---

## Automod

| Command | Who | Usage |
|---------|-----|-------|
| `automod` | Admin | `?automod [subcommand]` |

```
?automod status
?automod word add contains <text>
?automod word add exact <text>
?automod word remove <entry-id>
?automod word list
?automod banword word1, word2
?automod banexact word
?automod unbanword <entry-id|text> [contains|exact]
?automod blacklist domain.com
?automod whitelist domain.com
?automod ignore channel add #channel
?automod ignore channel remove #channel
?automod ignore channel list
?automod ignore role add @role
?automod ignore role remove @role
?automod ignore role list
?automod ignorechannel #channel
?automod ignorerole @role
?automod ignored
?automod antispam on|off
?automod anticaps on|off
?automod antiinvite on|off
?automod antimention on|off
?automod threshold caps <50-100>
?automod threshold spam-count <3-20>
?automod threshold spam-window <1s-60s>
?automod threshold mentions <2-50>
?automod threshold show
?automod threshold reset caps|spam|mentions|all
```

**Master switch:** `?module Automod` enables or disables all Automod processing. `?automod status` shows master status plus individual protection settings (marked inactive when the module is disabled).

**Banned words:** One unified list with two match modes — `contains` (substring) and `exact` (whole-token). Use `?automod word` commands; legacy `banword` / `banexact` / `unbanword` aliases still work.

**Ignore lists:** Channels and roles in the ignore lists bypass all Automod checks (not manual moderation). Use `?automod ignore channel|role add|remove|list`. Removal accepts raw IDs even when the channel or role was deleted. `@everyone` cannot be added to ignored roles. Legacy `ignorechannel` / `ignorerole` add aliases remain; `?automod ignored` shows a combined summary.

**Thresholds:** Configure caps %, spam count/window, and mention limit with `?automod threshold`. Toggles (`antispam`, `anticaps`, `antimention`) are independent — changing a threshold does not enable the protection. Spam window accepts durations like `5s` or `1m` (stored as milliseconds). Caps detection requires at least 8 letters (hardcoded, not configurable). `@everyone`/`@here` always trigger anti-mention regardless of count.

---

## Info

| Command | Who | Usage |
|---------|-----|-------|
| `help` | Anyone | `?help` · `?help <command>` |
| `info` | Anyone | `?info server\|user\|channel\|avatar [@user/#channel]` |
| `whois` | Anyone | `?whois [@user]` |

---

## First-time setup

```
?staff mod add @Moderator
?modlog #mod-logs
?modqueue #mod-review
?strike set 3 5
?help
```

---

## Notes

- Timed bans/mutes: `?mod ban @user 1d reason` · `?mod mute @user 2h reason`
- Strike escalation runs on `?warn add` and mod queue deny
- Cases are created for ban, kick, mute, warn, purge, lock/unlock, etc.
- Data stored in `node-bun/data/store.json`
