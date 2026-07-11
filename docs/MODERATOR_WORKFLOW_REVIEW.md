# Moderator Workflow Review

**Scope:** Warnings, strike escalation, staff notes, and moderation cases.  
**Authority:** Current source code (`src/`, `scripts/`). Documentation cited only where it matches code.  
**Date:** Review pass — no source changes.

---

## Executive summary

The four systems are **partially separated** in data model but **blur in moderator UX**:

| System | Intended role | Actual role |
|--------|---------------|-------------|
| **Warnings** | Mutable active discipline counter | Mutable records; drive strikes; paired with immutable cases on create |
| **Strikes** | Threshold-based escalation | Runs on every new warning; **can re-mute** after manual unmute; **can re-ban** if user returns with warnings intact |
| **Notes** | Staff-only context | Correctly isolated (no cases, no user notify) |
| **Cases** | Immutable history | Append-only in practice; no edit/delete API; primary audit trail |

**Strike safety rating: requires fixes before use** (enabled by default; repeat escalation; no de-escalation on warning removal). See §8.

**Subcommand counts:** warnings **4**, notes **4**, cases **2** command patterns (numeric view + `list`).

---

## 1. System inventory

### 1.1 Warnings

| Field | Detail |
|-------|--------|
| **Purpose** | Track active disciplinary warnings per user; feed strike escalation |
| **Schema** | `warnings[]`: `{ id, guild_id, user_id, moderator_id, reason, source?, created_at }` |
| **Commands** | `?warn add\|list\|del\|clear` — default subcommand `add` if omitted |
| **Permission** | Mod (`checkMod`) |
| **Creation** | `createWarningWithCase()` — warning + case `warn` in one DB transaction |
| **Edit** | None |
| **Removal** | `?warn del <id>` (single), `?warn clear <user>` (all for user) |
| **List** | `?warn list [user]` — defaults to command author if user omitted |
| **Relationships** | Case `extra.warning_id` on create; strikes read `getWarnings().length` |
| **Mod-log** | Live embed on add (`sendModLog`, action `warn`) |
| **Retention** | Permanent until `del`/`clear`; no expiration |
| **User notified** | **No** DM; only mod channel reply + mod-log |
| **Source files** | `src/commands/moderation/warn.js`, `src/database/db.js` |

### 1.2 Strike escalation

| Field | Detail |
|-------|--------|
| **Purpose** | Auto-mute / auto-ban when warning count crosses thresholds |
| **Schema** | Guild settings: `strike_enabled`, `strike_mute_at`, `strike_ban_at` |
| **Commands** | `?strike status\|set\|on\|off` (Admin) — not under `?warn` |
| **Permission** | Admin (`checkAdmin`) |
| **Trigger** | After `?warn add` and mod-queue **Deny & Warn** only |
| **Escalation actions** | Mute role add; guild ban (permanent, `deleteMessageSeconds: 0`) |
| **Cases** | `strike_mute`, `strike_ban`, `strike_mute_failed`, `strike_ban_failed` |
| **Mod-log** | On success and failure paths |
| **Retention** | Settings persistent; no strike history table (only cases) |
| **User notified** | **No** explicit DM; mute/ban are visible in Discord |
| **Source files** | `src/utils/strikes.js`, `src/commands/admin/strike.js` |

**Defaults:** `strike_enabled: 1`, `strike_mute_at: 3`, `strike_ban_at: 5` (`src/database/db.js`).

### 1.3 Staff notes

| Field | Detail |
|-------|--------|
| **Purpose** | Internal staff context; not disciplinary |
| **Schema** | `notes[]`: `{ id, guild_id, user_id, moderator_id, content, created_at }` |
| **Commands** | `?note add\|list\|edit\|del` — default `add` |
| **Permission** | Mod |
| **Creation** | `addNote()` |
| **Edit** | `?note edit <id> <text>` — overwrites `content`; no history |
| **Removal** | `?note del <id>` — permanent delete |
| **List** | `?note list <user>` — **requires** user (no default) |
| **Relationships** | None to warnings/cases |
| **Mod-log** | **None** |
| **Retention** | Permanent until deleted |
| **User notified** | **Never** |
| **whois** | Note **count** only (not content) |
| **Source files** | `src/commands/moderation/note.js`, `src/database/db.js` |

### 1.4 Moderation cases

| Field | Detail |
|-------|--------|
| **Purpose** | Append-only moderation audit log |
| **Schema** | `cases[]`: `{ case_number, guild_id, user_id, moderator_id, action, reason, extra, created_at }`; per-guild counter `case_counters` |
| **Commands** | `?case <number>`, `?case list [user]` |
| **Permission** | Mod |
| **Creation** | `createCase()` / `createCaseInData()` from mod actions, warns, strikes, queue, purge, lockdown, channel lock/unlock |
| **Edit / delete** | **No API or commands** — effectively immutable |
| **List** | User filter: last **15** cases; global recent: last **10** |
| **Detail view** | Action, user, moderator, reason, date, `extra` fields |
| **Mod-log** | Parallel live notification for many actions (not stored in DB as `mod_logs`) |
| **Retention** | Permanent |
| **Source files** | `src/commands/moderation/case.js`, `src/database/db.js`, callers across handlers |

**`extra` linkage fields:** `source`, `status`, `warning_id`, `queue_id`, `timed_action_id`, `timed_action`, `ends_at`, plus action-specific blobs (e.g. lockdown counts).

---

## 2. Warning workflow

### Commands

| Subcommand | Syntax | Target resolution | Notes |
|------------|--------|-------------------|-------|
| **add** | `?warn add <user> [reason]` | `resolveMember` — **member must be in server** | Hierarchy check; creates warning + case; strike check |
| **list** | `?warn list [user]` | Defaults to **command author** if omitted | No moderator column; no case link |
| **del** | `?warn del <warning-id>` | Numeric ID only | Does not verify guild; does not touch case |
| **clear** | `?warn clear <user>` | Member required | Removes all warnings; no case changes |

There is **no** `?warn view <id>` subcommand.

### Moderator FAQ (from code)

| Question | Answer |
|----------|--------|
| How many current warnings? | `?warn list @user` or `?whois @user` (count only) |
| Why was each issued? | List shows `reason` only |
| Who issued it? | **Not shown in list** (stored as `moderator_id`, not displayed) |
| When issued? | `formatDate(created_at)` in list |
| Which case belongs? | **Not shown in list**; `?case list` or inspect case `extra.warning_id` |
| Delete one warning? | Removed from `warnings[]`; **case remains** |
| Clear warnings? | All removed; **cases and punishments unchanged** |
| Recalculate strikes after delete? | **No** — no de-escalation, no re-evaluation |
| User DM / public notice? | **No** |

### Unclear / misleading behavior

1. **List omits moderator and case number** — hard to tie warnings to audit trail.
2. **`?warn list` without user lists the moderator's own warnings** — surprising default.
3. **`del` / `clear` do not void cases** — historical case still says `warn` while active count drops.
4. **Deleting warnings does not undo strike mutes/bans** — count and punishment diverge.
5. **`resolveMember` does not accept raw user IDs** for warn (unlike `?mod ban`).
6. **Warning IDs are global counters** — not per-user sequence; fine but worth documenting.

---

## 3. Strike workflow

### Calculation

```text
warnCount = getWarnings(guildId, userId).length   // all stored warnings, no "active" filter
```

**Lifetime / active:** Uses **all warnings in DB** after any deletions. Deleting warnings lowers count; adding raises it. No separate “active” flag.

### Thresholds

| Setting | Default | Config |
|---------|---------|--------|
| `strike_mute_at` | 3 | `?strike set <muteAt> <banAt>` (muteAt < banAt) |
| `strike_ban_at` | 5 | Same |
| `strike_enabled` | **1 (on)** | `?strike on\|off`; `set` also forces enabled |

### Evaluation order (`checkStrikeEscalation`)

1. If `!strike_enabled` → return null  
2. Count warnings  
3. If `warnCount >= banAt` → attempt **ban** (permanent)  
4. Else if `warnCount >= muteAt` → attempt **mute** only if user **does not already have** mute role  

### Repeat-trigger analysis (critical)

| Threshold | Can repeat? | Mechanism |
|-----------|-------------|-----------|
| **Mute at 3** | **Yes**, conditionally | Mute runs only when `!target.roles.cache.has(muteRole)`. After **manual unmute**, next warning with `warnCount >= muteAt` **mutes again** and creates a **new** `strike_mute` case. Warnings 4, 5, … while still muted: **silent skip** (no escalation message). |
| **Ban at 5** | **Yes**, if user still a member | **No** “already banned” guard. Each qualifying warn attempts `target.ban()`. If user was unbanned but warnings remain ≥ banAt, **next warn bans again** with a new `strike_ban` case. |
| **Same threshold** | N/A | `set` requires `muteAt < banAt` — cannot set equal. |
| **Above ban threshold** | Every new warn | Warnings 6, 7, … still `>= banAt` → ban attempted each time (while member). |

**Example (mute=3, ban=5):** Warnings 4–5 while muted do **not** re-mute but still accumulate. Warning 5 triggers **ban**, not another mute.

### Deletion interaction

- `?warn del` / `?warn clear`: **no strike callback** — mute/ban persist.
- Re-adding warnings can re-trigger escalation.

### Failure behavior

- Bot hierarchy / Discord errors → `strike_*_failed` case + mod-log; punishment not applied.
- Ban succeeds but case write fails → user banned; mod sees `persistenceLoggingFailureMessage`.
- Queue deny when user left → warning path skipped; `queue_deny` case without warning.

### Temporary vs permanent

- Strike **mute**: permanent role until manual `?mod unmute` (no timed action).
- Strike **ban**: permanent (`deleteMessageSeconds: 0`).
- Contrast: `?mod mute 1d` uses timed `unmute` action + case metadata.

### Configuration gaps

- No validation that thresholds are positive beyond `set` parse.
- No maximum cap on thresholds.
- No strike cooldown or per-threshold deduplication table.

---

## 4. Staff-note workflow

### Commands

| Subcommand | Syntax |
|------------|--------|
| add | `?note add <user> <text>` |
| list | `?note list <user>` |
| edit | `?note edit <note-id> <text>` |
| del | `?note del <note-id>` |

### Clarifications

| Topic | Behavior |
|-------|----------|
| Staff-only | Yes — mod permission; not exposed to users in commands |
| Creates cases? | **No** |
| In `?whois`? | **Count only** — content requires `?note list` |
| User notified? | **Never** |
| Edit history? | **None** — `updateNote` replaces `content` |
| Deletion | **Permanent** |
| Expiration | **None** |

### Confusion risk with warnings

| Factor | Notes |
|--------|-------|
| Naming | `warn` vs `note` — distinct commands ✓ |
| Color / embed | Warnings yellow (`0xfee75c`), notes pink (`0xeb459e`) ✓ |
| ID namespaces | Separate counters — `#3` warning ≠ `#3` note |
| whois | Shows both counts side-by side — could imply equal weight |

**Risk level:** Moderate — training issue; no automatic cross-link.

---

## 5. Case workflow

### Commands

| Pattern | Syntax | Result |
|---------|--------|--------|
| View | `?case <number>` | Single case embed |
| List | `?case list [user]` | 15 per user / 10 recent guild-wide |

### Displayed fields

- **List:** case #, action, reason, moderator mention, date  
- **Detail:** action, user, moderator, reason, date, `extra` (source, status, warning_id, queue_id, timed_action*, ends_at)

### Linkage

| Link | Supported |
|------|-----------|
| Warning | `extra.warning_id` on `warn` / `queue_deny` cases |
| Queue | `extra.queue_id` on queue cases |
| Timed punishment | `timed_action_id`, `timed_action`, `ends_at` on temp ban/mute |
| Reverse (warning → case) | **No command** — search case list |

### Immutability

No `updateCase` / `deleteCase` in codebase. **Cases are intentionally append-only.**

### Actions that create cases

| Action | Case action(s) | Source |
|--------|----------------|--------|
| Warn | `warn` | `warn.js` |
| Ban / unban / kick / mute / unmute / softban | same as action | `mod.js` |
| Temp ban / mute | `ban` / `mute` + timed metadata | `mod.js` |
| Purge | `purge` | `purge.js` |
| Channel lock / unlock | `lock` / `unlock` | `channel.js` |
| Lockdown | `lockdown_*` | `lockdownHandler.js` |
| Queue approve | `queue_approve` | `interactionCreate.js` |
| Queue deny | `queue_deny` (+ warning) | `interactionCreate.js` |
| Strike mute / ban | `strike_mute` / `strike_ban` | `strikes.js` |
| Strike failures | `strike_mute_failed` / `strike_ban_failed` | `strikes.js` |

### Actions without cases (minimum set + others found)

| Action | Mod-log? | Recommendation |
|--------|----------|----------------|
| **deafen / undeafen** | No | **Recommended:** add case — voice moderation is a mod action |
| **Timed unban / unmute (scheduler)** | No | **Optional:** case on completion — low priority; initial case has `ends_at` |
| **channel_unlock_skipped / failed (scheduler)** | Live mod-log only | **Optional:** case for terminal failure |
| **slowmode** | No | **Avoid** — minor; live log sufficient |
| **Automod delete (no queue)** | No | **Avoid** — not a mod decision |
| **Config commands** (strike, automod, staff, etc.) | No | **Avoid** — unless audit compliance required |
| **Notes** | No | **Avoid** — correct |

---

## 6. Command consistency review

### Cross-system comparison

| Aspect | warn | note | case |
|--------|------|------|------|
| Add syntax | `add <user> [reason]` | `add <user> <text>` | N/A (view by #) |
| Remove verb | `del` | `del` | — |
| Clear all | `clear <user>` | — | — |
| Edit | — | `edit <id> <text>` | — |
| List | `list [user]` (optional user) | `list <user>` (required) | `list [user]` |
| ID targeting | warning id | note id | case number |
| Raw user ID | **No** (`resolveMember`) | **No** | N/A |
| Pagination | None (Discord limit risk) | None | Slice 10/15 |
| Default subcommand | `add` | `add` | — |

### Inconsistencies

- `del` vs hypothetical `remove` — internal consistent between warn/note.
- **List user optional vs required** (warn vs note).
- **Case “view”** uses bare number subcommand, not `case view <n>`.
- Queue cases use action `queue_deny` not `warn` though a warning is created.

### Proposed canonical structure (minimal breaking change)

```text
?warn add <user> [reason]          # keep
?warn list <user>                  # change: require user (breaking) OR document current default
?warn remove <warning-id>          # alias for del
?warn clear <user>                 # keep

?note add <user> <text>            # keep
?note list <user>                  # keep
?note edit <note-id> <text>        # keep
?note remove <note-id>             # alias for del

?case <number>                     # keep (alias: case view)
?case list [user]                  # keep
```

**Strongest simplification:** unify list UX (always require `<user>` for warn/note), show **moderator + case #** on `?warn list`, add `?warn remove` alias, document `?case <n>` as “view”.

---

## 7. Relationship model

### Proposed model vs implementation

| Concept | Proposed | Current |
|---------|----------|---------|
| Warning = mutable discipline | Yes | Yes — but deletion erodes strike input without undoing punishments |
| Strike = derived from warnings | Yes | Yes — count-based, on each add |
| Note = unrelated context | Yes | Yes |
| Case = immutable history | Yes | Yes — but warning delete leaves case describing a “warn” that no longer exists in active set |

### Flagged mismatches

1. **Deleting warnings deletes disciplinary evidence from strike input but not from cases** — cases remain the audit source; warnings are the “active” source of truth for strikes only.
2. **Notes never touch cases** ✓  
3. **Cases duplicate warning reason at creation** — expected snapshot, not live sync ✓  
4. **Strike uses all stored warnings** — no “voided” state; `del` is hard delete ✓  
5. **Case is historical** — but moderators may treat warning list as authoritative for “how many strikes until ban” ✓  

---

## 8. Strike safety analysis

### Checks performed

| Check | Finding |
|-------|---------|
| Repeated escalation at same threshold | **Mute:** skipped if role present; **re-applies after manual unmute**. **Ban:** re-attempts while member and count ≥ banAt. |
| Concurrent warnings | DB `mutateDatabase` serializes — one warning per transaction ✓ |
| Delete + re-add | Count changes; can cross thresholds again |
| Queue + manual warn | Both call `checkStrikeEscalation` after atomic write |
| Bot hierarchy failure | Recorded; no punishment ✓ |
| Temp punishment recovery | Strike mute/ban **not** tied to timed-actions system |
| User left server | `?warn add` blocked; queue deny can still case without warn |
| Threshold validation | Only `muteAt < banAt` on `set` |
| Equal thresholds | Prevented on `set` |
| Irreversible ban | **Yes** — strike ban is permanent |

### Rating: **requires fixes before use**

**Reasons:**

1. **`strike_enabled` defaults to on** with auto-ban at 5 warnings.  
2. **Repeat mute** after manual unmute without moderator intent.  
3. **Repeat ban** possible if warnings not cleared when unbanning.  
4. **No deduplication** — multiple `strike_mute` / `strike_ban` cases for the same threshold band.  
5. **Warning deletion does not de-escalate** — policy ambiguity and abuse potential (warn to threshold → delete warnings → repeat).  

Not **should be removed** — strikes are core to the bot’s value proposition once hardened.

Closer to **safe but should default off** until deduplication and void semantics exist.

---

## 9. Moderator experience scenarios

### Scenario A: Basic warning

| Step | Command / system |
|------|------------------|
| Warn | `?warn add @user spam` |
| Review warning | `?warn list @user` — reason + date; **no case #** |
| Review case | `?case list @user` — find `warn` action |
| Mod-log | Live embed with case # |

**Gaps:** Two commands to connect warning ↔ case; list missing moderator.

### Scenario B: Warning mistake

| Step | Issue |
|------|-------|
| Wrong user warned | `?warn del <id>` or `?warn clear @wrong` |
| Case remains | Case # still shows erroneous warn |
| Strike | If threshold crossed, **punishment not auto-reversed** |
| Correct user | `?warn add @right ...` |

**Unsafe:** Delete warning after strike ban does not unban.

### Scenario C: Repeated offenses

| Step | Behavior |
|------|----------|
| 3rd warn | Auto-mute + `strike_mute` case |
| 4th–5th warn while muted | No new mute; count rises |
| 5th warn | Auto-ban |
| Remove 1 old warn (`?warn del`) | Count 4; **still banned**; no auto-unban |

**Confusing:** Punishment state decoupled from warning count after deletion.

### Scenario D: Staff context

| Step | Command |
|------|---------|
| Record appeal | `?note add @user appealed mute on 2024-01-01; approved` |
| No discipline | No case, no strike change ✓ |

**Clear** if staff know notes vs warns.

### Scenario E: Historical investigation

| Need | Command |
|------|---------|
| All cases | `?case list @user` (max 15) |
| Warnings | `?warn list @user` |
| Notes | `?note list @user` |
| Failed strikes | `?case list` — look for `strike_*_failed` |
| Queue | Case `extra.queue_id`; queue rows in `mod_queue` (no list command) |
| Bans / mutes | Cases + live Discord state |

**Gaps:** 15-case cap; no unified timeline; queue history not exposed via command.

---

## 10. Recommended command design

### Keep unchanged

- `?warn add <user> [reason]`
- `?note add|list|edit|del` structure
- `?case <number>` and `?case list [user]`
- `?strike status|set|on|off` (admin separation is appropriate)

### Keep with aliases

| Canonical | Alias (retain) |
|-----------|----------------|
| `?warn remove <id>` | `?warn del <id>` |
| `?note remove <id>` | `?note del <id>` |
| `?case view <n>` | `?case <n>` |

### Breaking change recommended (only if behavior fixed alongside)

| Change | Why |
|--------|-----|
| Require `<user>` on `?warn list` | Stops accidental self-list |
| Rename queue case action to include warn linkage in `?case` display | `queue_deny` obscures that a warning was added |
| Default `strike_enabled` to **off** | Safer onboarding |

**Do not implement in this review.**

---

## 11. Candidate behavior changes

| Change | Classification | Rationale |
|--------|----------------|-----------|
| Warning **void** (keep case + strike recount) vs hard **delete** | **Essential** | Aligns warnings with immutable cases |
| Warning **edit** (reason only) | **Optional** | Rare; case snapshot would stay |
| **Immutable cases** (keep as-is) | **Essential** | Already correct |
| Note **edit history** | **Optional** | Audit nicety |
| Note **deletion** (keep) | **Recommended** | GDPR / mistake correction |
| **User notification** for warnings (DM) | **Optional** | Policy choice; currently absent |
| Warning **expiration** | **Optional** | Not in model today |
| **Strike deduplication** (per threshold band) | **Essential** | Prevents repeat mute/ban |
| **Strike cooldown** | **Recommended** | Secondary safety net |
| **Active vs lifetime** warning counts | **Recommended** | Voided warnings excluded from strikes |
| Cases for **deafen/undeafen** | **Recommended** | Closes audit gap |
| Cases for **scheduler outcomes** | **Optional** | Initial case has expiry metadata |
| De-escalate on warning delete | **Essential** if delete kept | Or ban void entirely |

---

## 12. Final decision table

| System / command | Current behavior | Main issue | Proposed change | Breaking? | Priority | Reason |
|------------------|------------------|------------|-----------------|-----------|----------|--------|
| `?warn add` | Warning + case + optional strike | No user notify; list lacks case # | Enrich list output | No | Medium | Traceability |
| `?warn list` | Optional user, no moderator | Defaults to self | Require `<user>` or rename | Yes | Low | UX clarity |
| `?warn del` | Hard delete warning | Case/orphan; strike not reversed | Void + strike recount | Yes | **High** | Safety |
| `?warn clear` | Delete all warnings | Same as del | Void-all or forbid | Yes | **High** | Safety |
| Strike mute | Re-applies after manual unmute | Repeat punishment | Dedup per threshold | No | **High** | Correctness |
| Strike ban | Re-applies when count ≥ banAt | Repeat permanent ban | Dedup + warn on unban | No | **High** | Correctness |
| `strike_enabled` default | On | Risky for new guilds | Default off | No | **High** | Safety |
| `?note *` | Isolated | Minor ID confusion with warns | Training / docs | No | Low | — |
| `?case *` | Immutable, capped lists | 10/15 limit | Pagination | No | Medium | Investigation |
| `?case` linkage | warning_id in extra | No reverse lookup | `?case list` shows warning_id | No | Medium | UX |
| Queue deny case | `queue_deny` action | Looks unlike warn | Display “warn + queue” | No | Low | Clarity |
| `?mod deafen` | No case | Audit gap | Add case | No | Medium | Completeness |
| Scheduler unmute/unban | No case | Relies on original case | Optional completion case | No | Low | Nice-to-have |
| `?whois` | Counts + 5 cases; no mod check | Public case exposure | Restrict or redact | Yes | Medium | Privacy |

---

## Appendix A: Threshold / automod (out of scope but adjacent)

Automod **without queue** deletes message — **no warning, no case**. Queue **Deny & Warn** is a fifth warning source equivalent to `?warn add` for strikes.

---

## Appendix B: File reference

| Area | Files |
|------|-------|
| Warnings | `src/commands/moderation/warn.js`, `src/database/db.js` |
| Strikes | `src/utils/strikes.js`, `src/commands/admin/strike.js` |
| Notes | `src/commands/moderation/note.js` |
| Cases | `src/commands/moderation/case.js`, `src/database/db.js` |
| Queue → warn | `src/events/interactionCreate.js`, `src/handlers/modQueue.js` |
| whois | `src/commands/info/whois.js` |
| Mod-log | `src/utils/modLog.js` |

---

*End of review. No source files were modified.*
