# Discord Mod Bot — Simplification & Maintenance Review

**Companion to:** `FEATURE_INVENTORY.md`  
**Purpose:** Overlap analysis, usability findings, completeness gaps, risk ratings, and preliminary disposition recommendations. **No code changes.**

---

## 1. Overlap and duplication analysis

### Cases vs mod logs vs Discord audit log vs mod-log channel

| System | Role | Status |
|--------|------|--------|
| **Cases** (`cases`) | Sole persistent internal moderation history | **Active** — all new actions write here only |
| **Mod-log channel** | Live Discord embed notifications via `sendModLog` | **Active** — not a database write |
| **`?audit`** | Discord native audit log | **Unchanged** — external data source |
| **`mod_logs` collection** | Legacy duplicate rows | **Deprecated** — no new writes; old data preserved on load |

**Disposition:** **Complete** — cases are the internal source of truth.

---

### Warnings vs strikes

| System | Role |
|--------|------|
| **Warnings** | Counted records; `?warn` CRUD |
| **Strikes** | Threshold rules triggering auto-mute/ban on warn count |

**Tradeoffs:** Strikes are not separate records — they react to warning count. Clear mental model if documented.

**Disposition:** **Remain separate** conceptually; ensure docs clarify strikes = automation on warnings.

---

### Notes vs cases

Notes are staff-only text without case numbers or mod-log posts. Cases are formal actions.

**Disposition:** **Remain separate** — different audience and workflow.

---

### Automod queue vs direct automod delete

When `mod_queue_enabled`: message queued for review. When disabled or queue fails: message deleted + 5s warning.

**Tradeoffs:** Two punishment paths; queue is safer, direct delete has no DB record until deny.

**Disposition:** **Remain separate** modes; consider always logging automod deletes even without queue.

---

### Module toggle (sole Automod master switch)

| Control | Effect |
|---------|--------|
| `?module Automod` | `disabled_modules` JSON — Automod listed = disabled; absent = enabled |

Automod runs only when the module is enabled **and** the relevant individual protection is on or configured.

**Disposition:** **Complete** — single master switch via module system.

---

### Ban / temp ban / softban

All use `?mod ban` with optional duration. Softban is separate action (ban+unban for message purge).

**Disposition:** **Remain separate** actions; syntax is consolidated appropriately.

---

### Mute / temp mute / deafen

Mute uses role; temp mute uses timed `unmute`. Deafen is voice-only with no DB record.

**Disposition:** **Remain separate**; deafen should either get cases or be documented as ephemeral-only.

---

### Channel lock vs lockdown

| Feature | Scope | Persistence |
|---------|-------|-------------|
| `?channel lock` | Single channel; optional timed unlock | DB timed action (`channel_unlock`) |
| `?channel lockdown` | Administrator-configured channel list | `lockdown_state` snapshot + optional `lockdown_channel_restore` retries |

**Disposition:** **Complete** — separate concerns; lockdown has configuration, persistence, and conflict-safe restoration.

---

### Banned words (unified)

One `banned_words` collection with `match_mode`: `contains` (substring) or `exact` (word-boundary token). Commands: `?automod word add|remove|list`. Legacy `banword` / `banexact` / `unbanword` aliases delegate to the same implementation.

**Disposition:** **Complete** — consolidated storage and commands.

---

### Link blacklist vs anti-invite

Anti-invite uses regex on Discord invite patterns. Blacklist is custom domain/path matching. Empty blacklist blocks all links when anti-link path triggers.

**Disposition:** **Remain separate** — complementary; document interaction when both enabled.

---

### Admin roles vs Discord Administrator

Admin commands accept either Discord Administrator **or** configured admin role. Mod commands also accept Administrator.

**Disposition:** **Remain separate** — flexible for large servers; document clearly.

---

### `staff` vs separate role commands

Single `?staff` command covers mod and admin roles.

**Disposition:** **Keep** — already consolidated.

---

## 2. Usability review

### Confusing syntax

| Issue | Example |
|-------|---------|
| Nested subcommands | `?staff mod add @Role` — three levels |
| `mod` action as subcommand | `?mod ban` not `?ban` |
| `channel lock` channel/time ordering | `#channel` must come before duration |
| `purge` filter/count parsing | Count often last arg; ambiguous with text filters |
| `case` number as subcommand | `?case 42` uses subcommand slot for digits |
| `modqueue` channel vs `off`/`status` | First token disambiguation |

### Discovery

- **Good:** `?help`, mention bot for prefix
- **Weak:** timed channel lock behavior not in help embeds
- **No slash commands** — all prefix-only

### Inconsistent patterns

| Area | Inconsistency |
|------|----------------|
| User targeting | `?mod unban` uses raw ID; others use @mention |
| Duration position | After user on ban/mute; after channel on lock |
| Permission on info | `?whois` exposes mod history to anyone |
| Case creation | Deafen/undeafen/slowmode have none |
| Success messages | Mix of embeds and plain text |
| Error messages | Generally `❌` prefix via `error()` helper |

### Destructive actions

- **No confirmation** for ban, kick, purge, strike thresholds, lockdown
- **Appropriate** for mod bot speed; purge is especially destructive with no preview count confirmation

### Message / embed limits

- `?case list`, `?warn list`, `?note list`, `?audit` — can exceed embed 4096 chars with many entries
- No pagination

### Missing UX affordances

- Mod queue uses buttons (good)
- No buttons for case navigation, warning management, or timed-action diagnostics
- `?whois` could be mod-only or hide counts from regular members

### Help documentation

- `?help` lists commands only — no permission levels, duration formats, or strike behavior
- `COMMANDS.md` superuser hierarchy text corrected to match code

---

## 3. Completeness and dead-code review

### Documented but not in code (or wrong)

| Item | Issue |
|------|--------|

### Removed in dead-code cleanup (2026)

| Item | Resolution |
|------|------------|
| Superuser hierarchy bypass (docs) | Docs corrected — superusers get command access only |
| `CLIENT_ID`, `DEFAULT_PREFIX` | Removed from `.env.example` |
| Purge `after` filter | Removed from `PURGE_FILTERS` |
| `anti_duplicate` | Removed from default settings; legacy DB keys tolerated |
| `addModLog()`, `getModLogs()`, `updateModQueueStatus()` | Exports removed |
| `checkModule()` | Removed |
| `MOD_PERMS` / `ADMIN_PERMS` | Removed |
| `isDiscordRateLimitError` / `isDiscordMissingPermissionsError` | Removed |
| `GuildMessageReactions` intent + reaction partials | Removed |
| Unused `removeIgnoredChannel/Role` imports in automod.js | Removed (DB functions retained) |

### Implemented but missing from docs

| Item | Notes |
|------|-------|
| Channel timed unlock persistence + retry | Recent hardening; not in COMMANDS.md |
| `channel_unlock_skipped` / `channel_unlock_failed` mod-log types | Scheduler-only |
| Transaction helpers (`createWarningWithCase`, etc.) | Internal |
| `getChannelRestoreDiagnostics` | No user-facing command |
| Graceful shutdown / DB flush | Operational |
| Failed timed channel unlock records (`status: failed`) | Admin visibility gap |
| Rollback messages for temp ban/mute | User-facing error strings |

### Unreachable / unused code

| Item | Location |
|------|----------|
| Command aliases | Loader supports; no command defines `aliases` |
| `addWarning()` alone | Superseded for main flows; still exported |
| `removeIgnoredChannel` / `removeIgnoredRole` | Wired to `?automod ignore channel|role remove` |

### Incomplete feature branches

| Feature | Gap |
|---------|-----|
| Deafen/undeafen | No cases or mod logs |
| Slowmode | No case/log; no timed restore |
| Automod ignore lists | Full add/remove/list via `?automod ignore` |
| Spam tracker | In-memory only |
| Note commands | No hierarchy check on target |

### Obsolete / post-refactor duplication

- Cases are the sole persistent internal moderation record
- `mod_logs` collection may remain in older databases but is no longer written

### Tests

| Script | In `bun run test`? |
|--------|-------------------|
| `verify-moderation-workflows.mjs` | Yes (entry) |
| `verify-timed-channel.mjs` | Yes (chained) |
| `verify-database.mjs` | Yes (chained) |
| `verify-regex.mjs` | Yes (chained) |
| `verify-moderation.mjs` | Yes (chained) |
| `verify-cleanup.mjs` | Yes (chained) |
| `verify-automod-module.mjs` | Yes (chained) |
| `verify-cases-consolidation.mjs` | Yes (chained) |
| `verify-banned-words.mjs` | Yes (chained) |

No standalone CI config beyond `bun run test`.

---

## 4. Risk and maintenance review

| Feature | Reliability | Abuse risk | Maintenance complexity | Moderator usefulness |
|---------|:-----------:|:----------:|:----------------------:|:--------------------:|
| Core mod actions (`?mod`) | **High** | Medium | Medium | **High** |
| Warning + strikes | **High** | Medium | Medium | **High** |
| JSON database layer | **High** | Low | Medium | High |
| Timed ban/mute | **High** | Medium | Medium | **High** |
| Timed channel lock | **High** | Low | **High** | Medium |
| Automod engine | Medium | Medium | Medium | **High** |
| Mod queue | **High** | Low | Medium | **High** |
| Purge | Medium | **High** | Low | **High** |
| Lockdown | Low | Medium | Low | Low |
| `?whois` public mod data | Medium | **High** | Low | Medium |
| `mod_logs` duplication | Medium | Low | **High** | Low |
| In-memory spam tracker | Low | Medium | Low | Medium |
| Notes (no hierarchy) | Medium | Medium | Low | Medium |

### High complexity explanations

- **Timed channel lock:** Permission state capture, retry/backoff, manual unlock restore, scheduler — many edge cases, well-tested but intricate.
- **`mod_logs` duplication:** Two sources of truth for the same events; confusing for future features.

### High abuse risk explanations

- **`?purge`:** Mass delete up to 100 messages, no confirmation.
- **`?whois`:** Any member can see warning/case counts.

---

## 5. Permission inconsistencies

| Issue | Detail |
|-------|--------|
| `?modules` vs admin category | Listed under Admin in docs; no permission check |
| `?whois` mod data | Anyone can view warning/case summary |
| Notes without hierarchy | Mod can note any user regardless of role position |
| COMMANDS superuser claim | Docs say hierarchy bypass; code does not |
| `checkAdmin` redundancy | Checks `isAdmin` then `Administrator` again |
| Deafen hierarchy | Checked; but no audit trail |

---

## 6. Final classification table

| Feature | Current purpose | Status | Suggested disposition | Priority | Reason |
|---------|-----------------|--------|----------------------|----------|--------|
| `?mod` (ban/kick/mute/…) | Core punishment | Complete | **Keep** | — | Central workflow |
| Temp ban/mute + rollback | Safe timed punishments | Complete | **Keep** | — | Recently hardened |
| `?warn` + atomic case | Official warnings | Complete | **Keep** | — | Strike input |
| Strike escalation | Auto-mute/ban thresholds | Complete | **Keep** | — | Key differentiator |
| `?note` | Staff notes | Complete | **Keep** | Low | Consider hierarchy check |
| `?case` | Case lookup | Complete | **Keep but simplify** | Medium | Add pagination |
| `?audit` | Discord audit sync | Complete | **Keep** | Low | Complements cases |
| `?purge` | Bulk delete | Complete | **Keep** | Medium | Optional confirm? |
| `?channel lock` + scheduler | Channel mute w/ timer | Complete | **Keep** | — | Recently hardened |
| `?channel unlock` | Manual restore | Complete | **Keep** | — | |
| `?channel slowmode` | Rate limit | Complete | **Keep** | Low | Optional case log |
| `?channel lockdown` | Multi-channel lock | Complete | **Keep** | — | Configurable channel list, persistent state, restoration |
| `?staff` | Role-based perms | Complete | **Keep** | — | |
| `?prefix` / `?modlog` / `?modqueue` / `?strike` | Server setup | Complete | **Keep** | — | |
| `?module` / `?modules` | Module toggles | Complete | **Keep** | — | Sole Automod master switch |
| `?automod` | Automod config | Complete | **Keep** | — | Threshold commands added |
| Mod queue buttons | Review automod hits | Complete | **Keep** | — | Good UX |
| Direct automod delete | Fast path w/o queue | Complete | **Keep** | Low | |
| `?help` / `?info` | Discovery / info | Complete | **Keep but simplify** | Medium | Richer help content |
| `?whois` | User + mod summary | Complete | **Keep but simplify** | **High** | Restrict to Mod |
| `mod_logs` collection | Legacy duplicate of cases | Deprecated writes | **Keep legacy data** | — | No new entries |
| Cases collection | Numbered records | Complete | **Keep** | — | Source of truth |
| `lockdown_channels` setting | Lockdown targets | Complete | **Keep** | — | Set via `?channel lockdown channel add` |
| `lockdown_state` setting | Active lockdown snapshot | Complete | **Keep** | — | Survives restart |
| `getChannelRestoreDiagnostics` | Admin diagnostics | Complete (internal) | **Expand later** | Medium | No command |
| In-memory spam tracker | Spam detection | Questionable | **Keep** | Low | Lost on restart |
| `CLIENT_ID` / `DEFAULT_PREFIX` env | App metadata | Unused | **Remove** from example | Low | Confusing |
| Reaction intent | Unknown | Unused | **Remove** | Low | Dead |
| Superuser hierarchy bypass (docs) | — | Wrong | **Rename** docs | High | Mismatch with code |
| Deafen / undeafen | Voice mod | Questionable | **Expand later** | Medium | No case trail |
| Transaction helpers | DB integrity | Complete | **Keep** | — | Internal |

---

## 7. Strongest merge candidates

1. **`mod_logs` table + `cases`** — **merged** (cases only for new writes)  
2. **Lock + lockdown** — intentionally separate; single-channel lock vs server lockdown

---

## 8. Strongest removal candidates (remaining)

1. **Lockdown** — if not planned, remove half-finished branch  

---

## 9. Summary statistics (for parent report)

| Metric | Value |
|--------|------:|
| Top-level commands | **18** |
| Subcommands / action modes | **~72** |
| Undocumented commands/features | **~8** (diagnostics, failed timed actions, rollback errors, shutdown, dual automod flags, etc.) |
| Documented but wrong/unimplemented | **0** |
| Unused/incomplete settings | **~2** |

---

*Preliminary recommendations only — not implementation instructions.*
