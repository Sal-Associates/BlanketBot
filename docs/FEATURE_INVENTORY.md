# Discord Mod Bot — Feature Inventory

> **Path note:** JavaScript sources listed as `src/...` are under `node-bun/src/...`. Production Python code is in `python/`.

**Generated from source code review** (not README/COMMANDS alone).  
**Scope:** Single-server moderation bot (`GUILD_ID` enforced).  
**Default prefix:** `?` (per-guild, configurable).

---

## Summary counts

| Metric | Count |
|--------|------:|
| Top-level prefix commands | **18** |
| Distinct subcommands / action modes | **~72** |
| Command aliases | **0** (none registered) |
| Slash / application commands | **0** |
| Button interaction flows | **2** (mod queue approve/deny) |

---

## 1. Command inventory

### Permission legend

| Level | Who qualifies |
|-------|----------------|
| **Anyone** | Any member in the configured guild |
| **Mod** | Superuser ID, Discord `Administrator`, `Moderate Members`, `Manage Messages`, or `?staff mod` role |
| **Admin** | Superuser ID, Discord `Administrator`, or `?staff admin` role |

**Superuser** (`SUPERUSER_IDS` in `.env`): grants Mod + Admin command access. **Does not bypass role hierarchy** for targeting members (code in `permissions.js`).

**Hierarchy:** Issuer must be above target (except guild owner issuer). Bot role must be above target for member actions.

---

### Administration

#### `staff`

| Field | Value |
|-------|--------|
| **Syntax** | `?staff mod\|admin add\|del\|list [role]` |
| **Aliases** | None |
| **Category** | Admin |
| **Permission** | Admin |
| **Discord permission** | None required on issuer |
| **Source** | `src/commands/admin/staff.js` |

| Subcommand | Arguments | Defaults | Behavior |
|------------|-----------|----------|----------|
| `mod list` | — | — | Lists configured moderator roles |
| `mod add` | `@role` / name / ID | — | Adds role to `mod_roles` |
| `mod del` | `@role` | — | Removes role from `mod_roles` |
| `admin list` | — | — | Lists configured admin roles |
| `admin add` | `@role` | — | Adds role to `admin_roles` |
| `admin del` | `@role` | — | Removes role from `admin_roles` |

| DB | Discord | Cases / logs | Duration | Failures | Status |
|----|---------|--------------|----------|----------|--------|
| `mod_roles` / `admin_roles` | None | None | N/A | Missing role arg, no roles configured | **Complete** |

---

#### `prefix`

| Field | Value |
|-------|--------|
| **Syntax** | `?prefix [new prefix]` |
| **Permission** | Admin |
| **Source** | `src/commands/admin/prefix.js` |

| Arguments | Default | Behavior |
|-----------|---------|----------|
| `new prefix` | — | Sets `guild_settings.prefix` (max 5 chars) |

| DB | Discord | Cases | Status |
|----|---------|-------|--------|
| `guild_settings.prefix` | None | None | **Complete** |

**Failures:** Empty or >5 characters rejected.

---

#### `modlog`

| Field | Value |
|-------|--------|
| **Syntax** | `?modlog [channel]` |
| **Permission** | Admin |
| **Source** | `src/commands/admin/modlog.js` |

| Arguments | Default | Behavior |
|-----------|---------|----------|
| `#channel` | Current channel | Sets `mod_log_channel` |

| DB | Discord | Cases | Status |
|----|---------|-------|--------|
| `guild_settings.mod_log_channel` | None | None | **Complete** |

---

#### `modqueue`

| Field | Value |
|-------|--------|
| **Syntax** | `?modqueue [#channel]` · `?modqueue off` · `?modqueue status` |
| **Permission** | Admin |
| **Source** | `src/commands/admin/modqueue.js` |

| Subcommand | Behavior |
|------------|----------|
| `status` | Shows enabled flag and channel |
| `off` | Sets `mod_queue_enabled` = 0 |
| `#channel` (or implicit current) | Sets channel + enables queue |

| DB | Discord | Cases | Status |
|----|---------|-------|--------|
| `mod_queue_channel`, `mod_queue_enabled` | None | None | **Complete** |

---

#### `strike`

| Field | Value |
|-------|--------|
| **Syntax** | `?strike status\|set\|on\|off [muteAt] [banAt]` |
| **Permission** | Admin |
| **Source** | `src/commands/admin/strike.js` |

| Subcommand | Arguments | Behavior |
|------------|-----------|----------|
| `status` | — | Shows thresholds and enabled state |
| `set` | `<muteAt> <banAt>` | Sets thresholds; enables strikes; muteAt < banAt |
| `on` / `off` | — | Toggles `strike_enabled` |

| DB | Discord | Cases | Status |
|----|---------|-------|--------|
| `strike_mute_at`, `strike_ban_at`, `strike_enabled` | None | None | **Complete** |

---

#### `module`

| Field | Value |
|-------|--------|
| **Syntax** | `?module Automod` |
| **Permission** | Admin |
| **Source** | `src/commands/admin/module.js` |

Toggles `disabled_modules` JSON array entry for `Automod`. This is the **sole master switch** for Automod. Individual protection settings are unchanged when toggling.

| DB | Status |
|----|--------|
| `guild_settings.disabled_modules` | **Complete** (only one module exists) |

---

#### `modules`

| Field | Value |
|-------|--------|
| **Syntax** | `?modules` |
| **Permission** | Anyone (no check) |
| **Source** | `src/commands/admin/modules.js` |

Lists module enable/disable status. COMMANDS.md labels as Admin-adjacent but code has **no permission gate**.

---

### Moderation

#### `mod`

| Field | Value |
|-------|--------|
| **Syntax** | `?mod <action> [args]` |
| **Permission** | Mod |
| **Source** | `src/commands/moderation/mod.js` |

| Action | Syntax | Duration | Hierarchy | Bot Discord actions | DB | Cases |
|--------|--------|----------|-----------|---------------------|-----|-------|
| `ban` | `?mod ban <user> [duration] [reason]` | Optional (`ms` format) | Yes (user need not be member) | `guild.members.ban` | Temp: case + `timed_actions` (unban) atomically; Perm: case only | `ban` |
| `unban` | `?mod unban <userId> [reason]` | No | Self-check only | `members.unban` | Case | `unban` |
| `kick` | `?mod kick <user> [reason]` | No | Yes | `member.kick` | Case | `kick` |
| `mute` | `?mod mute <user> [duration] [reason]` | Optional | Yes | Mute role add | Temp: case + `unmute` timed action; Perm: case | `mute` |
| `unmute` | `?mod unmute <user> [reason]` | No | Yes | Mute role remove | Case | `unmute` |
| `softban` | `?mod softban <user> [reason]` | No | Yes | ban + immediate unban | Case | `softban` |
| `deafen` | `?mod deafen <user> [reason]` | No | Yes | `voice.setDeaf(true)` | **None** | **None** |
| `undeafen` | `?mod undeafen <user>` | No | Yes | `voice.setDeaf(false)` | **None** | **None** |

**Temporary punishment ordering:** Discord action first → atomic DB (case + timed reversal). On DB failure: rollback (unban / remove mute role) with explicit error messages.

**Permanent actions:** Discord first → case. On DB failure: reports “action succeeded, record could not be saved” (no rollback).

**Duration format:** Parsed via `ms` package (`1d`, `2h`, `30m`, etc.); minimum 1 second.

**Failures:** Discord API errors, hierarchy denial, rollback failure (temp only), case persistence failure.

**Status:** **Complete** except deafen/undeafen have no case/logging.

---

#### `warn`

| Field | Value |
|-------|--------|
| **Syntax** | `?warn add\|list\|del\|clear [args]` |
| **Permission** | Mod |
| **Source** | `src/commands/moderation/warn.js` |

| Subcommand | Behavior | DB | Cases |
|------------|----------|-----|-------|
| `add` | Warning + case atomically; mod-log channel notification; strike escalation after commit | `warnings` + `cases` | `warn` |
| `list` | Lists warnings for user | Read | None |
| `del` | Deletes warning by ID | `warnings` | None |
| `clear` | Clears all warnings for user | `warnings` | None |

**Failures:** Hierarchy, DB transaction failure (no warning/case/escalation).

**Status:** **Complete**

---

#### `note`

| Field | Value |
|-------|--------|
| **Syntax** | `?note add\|list\|edit\|del [args]` |
| **Permission** | Mod |
| **Source** | `src/commands/moderation/note.js` |

| Subcommand | DB | Cases / mod log |
|------------|-----|-----------------|
| `add` | `notes` | None |
| `list` | Read | None |
| `edit` | `notes` | None |
| `del` | `notes` | None |

**No hierarchy check** on notes (staff-only via Mod permission).

**Status:** **Complete**

---

#### `case`

| Field | Value |
|-------|--------|
| **Syntax** | `?case <number>` · `?case list [user]` |
| **Permission** | Mod |
| **Source** | `src/commands/moderation/case.js` |

Read-only view of `cases` collection. No Discord actions.

**Status:** **Complete** (embed length risk on large lists)

---

#### `channel`

| Field | Value |
|-------|--------|
| **Syntax** | `?channel lock\|unlock\|slowmode\|lockdown [args]` |
| **Permission** | Mod (lockdown subcommands: Admin) |
| **Source** | `src/commands/moderation/channel.js`, `src/handlers/lockdownHandler.js` |

| Subcommand | Duration | Discord | DB | Cases |
|------------|----------|---------|-----|-------|
| `lock` | Optional auto-unlock | Deny `SendMessages` for @everyone | `timed_actions` (`channel_unlock`) if duration | `lock` |
| `unlock` | — | Restores `previous_state` if pending timed lock; else inherit | Cancels pending `channel_unlock` | `unlock` |
| `slowmode` | — | `setRateLimitPerUser` | None | None |
| `lockdown channel add\|remove\|list` | — | — | `lockdown_channels` | None |
| `lockdown enable` | — | Deny `SendMessages` for @everyone in configured channels | `lockdown_state` snapshot | `lockdown_enable` / `lockdown_enable_partial` |
| `lockdown disable` | — | Restores recorded `previous_state` when current matches applied deny | Clears active lockdown; may queue `lockdown_channel_restore` | `lockdown_disable` / `lockdown_restore_failed` |
| `lockdown status` | — | — | Reads `lockdown_state` + restore queue | None |

**Lock persistence:** Captures prior permission state (allow/deny/unset); scheduled unlock survives restart via scheduler.

**Lockdown persistence:** Active lockdown and per-channel permission snapshots survive restart. Enabling twice does not overwrite original restoration data. Disabling preserves manual permission changes when they differ from the bot-applied deny. Failed disable restorations retry via `lockdown_channel_restore` timed actions.

**Status:** **Complete** (lockdown); slowmode has no case/log.

---

#### `audit`

| Field | Value |
|-------|--------|
| **Syntax** | `?audit <user> [limit]` |
| **Permission** | Mod |
| **Discord permission** | Bot needs **View Audit Log** |
| **Source** | `src/commands/moderation/audit.js` |

Fetches Discord native audit log (not bot DB). Default limit 10, max 25. No DB writes.

**Status:** **Complete**

---

### Purge

#### `purge`

| Field | Value |
|-------|--------|
| **Syntax** | `?purge [count]` · `?purge <filter> [args]` |
| **Permission** | Mod |
| **Source** | `src/commands/purge/purge.js` |

| Filter | Description |
|--------|-------------|
| *(none / number)* | Delete N messages (default 100, max 100) |
| `user` | Messages by user |
| `match` / `not` / `startswith` / `endswith` | Content filters |
| `links` / `invites` | URL / invite filters |
| `images` / `mentions` / `embeds` | Attachment/mention filters |
| `bots` / `humans` / `text` | Author type filters |

| DB | Discord | Cases |
|----|---------|-------|
| `cases` via `createCase` | `bulkDelete` / single delete | `purge` (target ID = channel ID) |

Messages older than 14 days are skipped (Discord limitation).

**Status:** **Complete**

---

### Automod (configuration)

#### `automod`

| Field | Value |
|-------|--------|
| **Syntax** | `?automod <subcommand> [args]` |
| **Permission** | Admin |
| **Source** | `src/commands/automod/automod.js` |

| Subcommand | DB collections / settings |
|------------|---------------------------|
| `banword` | `banned_words` (`contains`) — **legacy alias** for `word add contains` |
| `banexact` | `banned_words` (`exact`) — **legacy alias** for `word add exact` |
| `unbanword` | Removes from `banned_words` — **legacy alias** for `word remove` |
| `word` | `banned_words` CRUD: `add contains|exact`, `remove <id>`, `list` |
| `blacklist` / `whitelist` | `automod_links` |
| `ignore channel` | `automod_ignored_channels` — `add`, `remove`, `list` |
| `ignore role` | `automod_ignored_roles` — `add`, `remove`, `list` |
| `ignorechannel` | **Legacy alias** for `ignore channel add` |
| `ignorerole` | **Legacy alias** for `ignore role add` |
| `ignored` | Combined summary of both ignore lists |
| `threshold` | `caps_threshold`, `spam_threshold`, `spam_interval`, `mention_threshold` — configure/show/reset |
| `antispam` / `anticaps` / `antiinvite` / `antimention` | `guild_settings` toggles (independent from thresholds) |
| `status` | Read-only summary |

**Ignore policy:** `@everyone` cannot be added to ignored roles. Stale channel/role IDs remain until removed by raw ID. Ignored channels and roles bypass all Automod checks before individual protections run.

**Not configurable via command:** Caps minimum letter length (fixed at 8 in runtime).

**Status:** **Complete** for threshold configuration.

---

### Information

#### `help`

| Syntax | `?help` · `?help <command>` |
| Permission | Anyone |
| Source | `src/commands/info/help.js` |

Dynamic list from loaded commands. No DB.

---

#### `info`

| Subcommands | `server` (default), `user`, `channel`, `avatar` |
| Permission | Anyone |
| Source | `src/commands/info/info.js` |

Discord metadata only. No DB.

---

#### `whois`

| Syntax | `?whois [@user]` (default: self) |
| Permission | **Anyone** (no mod check) |
| Source | `src/commands/info/whois.js` |

Shows user info + **warning count, note count, recent cases** from DB to any member.

**Status:** **Complete** but permissive for sensitive mod data.

---

## 2. Event-driven features

### Message handler (`messageCreate`)

| Field | Value |
|-------|--------|
| **Trigger** | Any non-bot message in configured guild |
| **Source** | `src/events/messageCreate.js` |

| Behavior | Details |
|----------|---------|
| Guild guard | Ignores messages outside `GUILD_ID` |
| Prefix ping | Reply with prefix if bot mentioned without command |
| Commands | Parse `prefix` + route to command map |
| Automod | Runs on non-commands and unknown commands |
| DB read failure | Logs error; skips message processing |
| Command error | Generic “An error occurred” reply |

---

### Automod engine

| Field | Value |
|-------|--------|
| **Trigger** | Non-command messages (and unknown commands) |
| **Source** | `src/handlers/automodHandler.js`, `src/handlers/modQueue.js` |

| Check | Configuration |
|-------|----------------|
| Module disabled | `?module Automod` |
| Master switch | `?module Automod` (`disabled_modules` — Automod absent = enabled) |
| Check order | Module disabled → ignored channel → ignored role → moderator bypass → individual checks |
| Ignored channel/role | `?automod ignore channel|role` — bypass all Automod checks |
| Moderator bypass | Mod-level users skip automod (after ignore lists) |
| Banned words | `banned_words` (`match_mode`: `contains` or `exact`) |
| Anti-invite | `anti_invite` |
| Anti-mention | `anti_mention`, `mention_threshold` (user + role count; `@everyone`/`@here` always) |
| Link blacklist/whitelist | `automod_links` |
| Anti-caps | `anti_caps`, `caps_threshold` (default 70%) |
| Anti-spam | `anti_spam`, `spam_threshold` (5), `spam_interval` (5000 ms) |

| Outcome | Discord | DB |
|---------|---------|-----|
| Mod queue enabled | Delete message; post embed + buttons to queue channel | `mod_queue` entry |
| Queue disabled / failed | Delete message; ephemeral-style warning 5s | None |

**Spam tracker:** In-memory `Map` (lost on restart).

**Failure:** Mod queue errors logged; falls through to silent delete path if queue send fails.

---

### Mod queue buttons

| Field | Value |
|-------|--------|
| **Trigger** | `queue_approve_*` / `queue_deny_*` button clicks |
| **Source** | `src/events/interactionCreate.js` |

| Action | DB (atomic) | Discord | Logging |
|--------|-------------|---------|---------|
| Approve | `mod_queue` → approved + case | Edits queue message | Mod log + case |
| Deny (member present) | status + warning + case | Edits queue message | Mod log; strike escalation |
| Deny (user left) | status only | Edits message | None |

**Race handling:** `processModQueueDecision` re-checks `pending` inside DB transaction.

**Permission:** Mod-level required.

---

### Strike escalation

| Field | Value |
|-------|--------|
| **Trigger** | After successful `?warn add` or mod-queue deny warn |
| **Source** | `src/utils/strikes.js` |

| Threshold | Action |
|-----------|--------|
| `warnCount >= strike_ban_at` | Auto-ban + `strike_ban` case (or `strike_ban_failed`) |
| `warnCount >= strike_mute_at` | Auto-mute if not already muted + `strike_mute` case (or failed case) |

**Ordering:** Warning committed first; escalation Discord action second; case third. Permanent escalation (no timed reversal).

**Failures:** Bot hierarchy, Discord API, case logging — warning is never rolled back.

---

### Timed-action scheduler

| Field | Value |
|-------|--------|
| **Trigger** | On ready (immediate) + every 15s |
| **Source** | `src/handlers/scheduler.js`, `src/handlers/timedActions.js` |

| Action type | Discord effect |
|-------------|----------------|
| `unban` | `guild.members.unban` |
| `unmute` | Remove mute role |
| `channel_unlock` | Restore captured permission state with conflict detection |

**Channel unlock retries:** Up to 10 attempts with backoff; `failed` status retained; terminal removal on success/conflict/missing channel.

**Diagnostics:** `getChannelRestoreDiagnostics()` — **no command exposes this**.

---

### Startup validation

| Check | Source |
|-------|--------|
| `DISCORD_TOKEN` required | `src/index.js` |
| `GUILD_ID` format + presence | `src/utils/guild.js` |
| Database initialize / validate | `src/database/db.js` |
| Bot member of configured guild | `ready` handler |

---

### Graceful shutdown

| Behavior | Source |
|----------|--------|
| SIGINT / SIGTERM | `flushDatabaseQueue(5000)` then `client.destroy()` | `src/index.js` |

---

### Other listeners

| Event | Handler |
|-------|---------|
| `messageCreate` | Commands + automod |
| `interactionCreate` | Mod queue buttons only |
| `ready` | Guild validation, scheduler start |

**Not used:** No reaction event handlers (reaction intent removed).

---

### Ephemeral UI timers (non-persistent)

| Feature | Duration | Source |
|---------|----------|--------|
| Automod warning reply | 5s delete | `automodHandler.js` |
| Purge success reply | 5s delete | `purge.js` |

---

## 3. Configuration inventory

### Environment variables (`.env`)

| Name | Type | Used in code | Default | Configure via | Documented |
|------|------|--------------|---------|---------------|------------|
| `DISCORD_TOKEN` | string | **Yes** — required | — | `.env` | Yes |
| `GUILD_ID` | snowflake | **Yes** — required | — | `.env` | Yes |
| `SUPERUSER_IDS` | CSV user IDs | **Yes** | empty | `.env` | Yes |
| `STORE_PATH` | path | **Yes** (tests) | `data/store.json` | env / test hook | No |

---

### Guild settings (`guild_settings` per guild)

| Key | Type | Default | Discord command | Used | Notes |
|-----|------|---------|---------------|------|-------|
| `prefix` | string | `?` | `?prefix` | Yes | |
| `mod_log_channel` | channel ID | null | `?modlog` | Yes | |
| `mute_role` | role ID | null | **None** | Yes | Auto-set by mute |
| `anti_spam` | 0/1 | 1 | `?automod antispam` | Yes | |
| `anti_caps` | 0/1 | 0 | `?automod anticaps` | Yes | |
| `anti_invite` | 0/1 | 0 | `?automod antiinvite` | Yes | |
| `anti_mention` | 0/1 | 0 | `?automod antimention` | Yes | |
| `caps_threshold` | number (%) | 70 | `?automod threshold caps` | Yes | Inclusive `>=`; min 8 letters hardcoded |
| `spam_threshold` | number | 5 | `?automod threshold spam-count` | Yes | Inclusive `>=` messages in window |
| `spam_interval` | ms | 5000 | `?automod threshold spam-window` | Yes | Sliding window |
| `mention_threshold` | number | 5 | `?automod threshold mentions` | Yes | User + role mentions; `@everyone`/`@here` always flagged |
| `lockdown_channels` | JSON array | `[]` | `?channel lockdown channel add\|remove` | Yes | Configured text channels for server lockdown |
| `lockdown_state` | JSON object | null | `?channel lockdown enable\|disable` | Yes | Active lockdown snapshot with per-channel permission states |
| `disabled_modules` | JSON array | `[]` | `?module` | Yes | |
| `mod_queue_channel` | channel ID | null | `?modqueue` | Yes | |
| `mod_queue_enabled` | 0/1 | 0 | `?modqueue` | Yes | |
| `strike_mute_at` | number | 3 | `?strike set` | Yes | |
| `strike_ban_at` | number | 5 | `?strike set` | Yes | |
| `strike_enabled` | 0/1 | 1 | `?strike on/off` | Yes | |

---

### Role lists

| Collection | Configure | Purpose |
|------------|-----------|---------|
| `mod_roles` | `?staff mod add/del` | Custom mod command access |
| `admin_roles` | `?staff admin add/del` | Custom admin command access |

---

### Hard-coded constants

| Constant | Value | Location | Effect |
|----------|-------|----------|--------|
| Scheduler poll | 15s | `timedActionRetry.js` | Min retry interval |
| Channel unlock max attempts | 10 | `timedActionRetry.js` | Failed action retention |
| Purge max count | 100 | `purge.js` | |
| Purge max age | 14 days | `purge.js` | |
| Mass mention threshold | 5 | `automodHandler.js` | |
| Automod mod-log field limit | 1000 chars | `modQueue.js` | |
| Prefix max length | 5 | `prefix.js` | |
| Valid modules | `['Automod']` | `module.js` | |

---

## 4. Database inventory

**Storage:** `data/store.json` (JSON file, atomic writes, `.bak` backup).

### Collections

#### `guild_settings`

| Field | Purpose |
|-------|---------|
| Per-guild key-value | All server configuration (see §3) |

**ID:** Guild snowflake as key. **Growth:** Fixed per guild (1). **Admin view:** Via commands / JSON. **Retention:** Permanent.

---

#### `mod_roles` / `admin_roles`

| Field | `guild_id`, `role_id` |
|-------|----------------------|
| **Purpose** | Custom permission roles |
| **ID** | Composite (no numeric ID) |
| **Growth** | Bounded by role count |
| **Admin remove** | `?staff mod/del` |

---

#### `warnings`

| Field | `id`, `guild_id`, `user_id`, `moderator_id`, `reason`, `source?`, `created_at` |
|-------|------|
| **ID** | `_counters.warnings` |
| **Create** | `createWarningWithCase`, `processModQueueDecision` |
| **Read** | `?warn list`, `?whois`, strikes |
| **Delete** | `?warn del/clear` |
| **Growth** | **Unbounded** |
| **Overlap** | Linked to warn cases via `extra.warning_id` |

---

#### `notes`

| Field | `id`, `guild_id`, `user_id`, `moderator_id`, `content`, `created_at` |
|-------|------|
| **ID** | `_counters.notes` |
| **Growth** | **Unbounded** |
| **Overlap** | Separate from cases; no mod log embed |

---

#### `cases`

| Field | `case_number`, `guild_id`, `user_id`, `moderator_id`, `action`, `reason`, `extra`, `created_at` |
|-------|------|
| **ID** | Per-guild `case_counters` increment |
| **Role** | **Sole persistent internal moderation history** |
| **Create** | Most mod commands, strikes, queue, purge |
| **Read** | `?case`, `?case list`, `?whois` |
| **Delete** | **None** |
| **Growth** | **Unbounded** (no automatic retention) |
| **`extra` fields** | `source`, `status`, `warning_id`, `queue_id`, `ends_at`, `timed_action`, `timed_action_id` (optional per case) |

---

#### `mod_logs` (legacy)

| Field | Same shape as historical case companion rows |
|-------|------|
| **Purpose** | **Deprecated** — legacy duplicate audit trail from before case-only storage |
| **Writes** | **None** — new moderation actions create cases only |
| **Read** | Not queried; use `cases` or the mod-log channel |
| **Retention** | Preserved in existing databases; not deleted automatically |

---

#### `mod_queue`

| Field | `id`, `guild_id`, `channel_id`, `author_id`, `content`, `reason`, `queue_message_id`, `status`, `created_at` |
|-------|------|
| **ID** | `_counters.mod_queue` |
| **Status** | `pending`, `approved`, `denied` |
| **Growth** | **Unbounded** (no purge command) |
| **Admin view** | None (only via DB/file) |

---

#### `timed_actions`

| Field | Varies by `action` |
|-------|-------------------|
| **Types** | `unban`, `unmute`, `channel_unlock` |
| **User actions** | `guild_id`, `user_id`, `action`, `ends_at`, retry metadata |
| **Channel unlock** | `channel_id`, `role_id`, `permission`, `previous_state`, `applied_state`, `moderator_id`, `status`, `attempt_count`, etc. |
| **Growth** | Completed actions deleted; **failed** channel unlocks retained |
| **Admin view** | `getChannelRestoreDiagnostics()` only (no command) |

---

#### `banned_words`

| Field | `id`, `guild_id`, `value`, `match_mode` (`contains`/`exact`), `created_at`, `created_by` |
|-------|------|
| **Role** | Canonical banned-word list for Automod |
| **Migration** | Legacy `automod_words` entries migrated once on load |

#### `automod_words` (legacy)

| Field | `guild_id`, `word`, `exact` (0/1) |
|-------|------|
| **Status** | **Deprecated** — migrated to `banned_words`; preserved on disk |

#### `automod_links`

| Field | `guild_id`, `link`, `type` (`blacklist`/`whitelist`) |

#### `automod_ignored_channels` / `automod_ignored_roles`

| Field | `guild_id`, `channel_id` / `role_id` |

**Growth:** Bounded by admin configuration. **Remove:** Via `?automod ignore channel|role remove` (raw ID supported for deleted entries).

---

#### `_counters` / `case_counters`

Internal ID allocation. Not user-facing.

---

## 5. Permission model (summary)

See §1 per-command tables. Key points:

| Actor | Mod commands | Admin commands | Hierarchy bypass |
|-------|--------------|----------------|------------------|
| Server owner | If also mod-qualified | If also admin-qualified | Issuer role check only |
| Superuser | Yes | Yes | **No** |
| Discord Administrator | Yes | Yes | No |
| Moderate Members / Manage Messages | Yes | No | No |
| Custom mod role | Yes | No | No |
| Custom admin role | Yes (also mod) | Yes | No |
| Anyone | `help`, `info`, `whois`, `modules` | — | — |

**Bot:** Must pass `checkBotCanActOn` for member-targeting moderation.

**Inconsistencies flagged:** See `SIMPLIFICATION_REVIEW.md`.

---

## 6. Test scripts (`bun run test`)

Chain: `verify-moderation-workflows.mjs` → `verify-timed-channel.mjs` → `verify-database.mjs` → `verify-regex.mjs` → `verify-moderation.mjs`.

All run from `package.json` `"test"` script.

---

*End of factual inventory.*
