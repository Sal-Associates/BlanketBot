Perform the complete conversion of this Discord moderation bot from JavaScript/Bun to Python in one full migration pass.

**Repository status (2026):** Conversion **complete**. Production code lives in [`python/`](python/). The legacy JavaScript/Bun reference lives in [`node-bun/`](node-bun/). Repository separation is complete; future production changes belong under `python/`. Historical references below to `python/` or root-level `src/` describe the pre-reorganization layout.

The Python implementation must become a complete, cleaned-up, production-ready replacement for the JavaScript version.

Do not stop after individual stages. Continue until all currently implemented and approved features have been ported, tested, documented, and verified.

## Core rules

1. Do not edit, delete, or overwrite the JavaScript reference implementation under `node-bun/`.
2. Build the complete Python bot under:

```text
python/
```

3. The final Python bot must not require:

   * Node.js
   * Bun
   * npm
   * JavaScript
   * TypeScript

4. Use:

   * Python 3.12+
   * discord.py 2.x
   * aiosqlite
   * python-dotenv
   * pytest
   * pytest-asyncio
   * Ruff
   * full type annotations

5. Use SQLite as the production database.

6. Do not recreate the JSON write queue architecture.

7. Do not perform a mechanical line-by-line translation.

8. Preserve approved behavior from the JavaScript implementation while cleaning up architecture, naming, duplication, and dead code.

## Completion requirement

Do not report partial completion as finished.

Continue until:

* all approved JavaScript features are ported;
* all Python commands are registered;
* all services and repositories are implemented;
* all tests pass;
* Ruff passes;
* documentation is complete;
* the legacy JSON importer exists;
* no production placeholder or TODO remains for an approved feature.

If a feature cannot be safely ported, document the exact blocker and continue completing everything else.

# 1. Final Python architecture

Use a clean structure similar to:

```text
python/
├── bot/
│   ├── __init__.py
│   ├── __main__.py
│   ├── client.py
│   ├── config.py
│   ├── constants.py
│   ├── errors.py
│   ├── result_types.py
│   ├── checks/
│   ├── cogs/
│   ├── database/
│   │   ├── connection.py
│   │   ├── migrations.py
│   │   ├── models.py
│   │   └── repositories/
│   ├── services/
│   ├── automod/
│   ├── scheduler/
│   ├── utils/
│   └── views/
├── migrations/
├── scripts/
├── tests/
├── pyproject.toml
├── requirements.txt
├── .env.example
└── README.md
```

Use multiple focused cogs and services.

Cogs should:

* parse command input;
* resolve Discord objects;
* call services;
* format replies.

Services should contain:

* business rules;
* authorization;
* hierarchy checks;
* transactions;
* moderation workflows;
* Automod decisions;
* permission restoration;
* retry policy.

Repositories should contain:

* SQL;
* typed persistence operations;
* transaction-aware database access.

Avoid:

* giant cogs;
* SQL inside commands;
* global mutable business state;
* circular imports;
* bare `except`;
* synchronous database or file access in Discord handlers;
* duplicated validation logic.

# 2. Configuration and startup

Required environment variables:

```env
DISCORD_TOKEN=
GUILD_ID=
SUPERUSER_IDS=
DATABASE_PATH=data/modbot.sqlite3
```

Requirements:

* Validate configuration before connecting.
* `GUILD_ID` must be 17–20 digits.
* `SUPERUSER_IDS` is optional and comma-separated.
* Fail clearly on invalid configuration.
* Never log the token.
* Configure structured, readable logging.
* Run migrations before normal bot operation.
* Confirm the bot is connected to the configured guild.
* Ignore DMs and all foreign-guild events.
* Close the database and Discord client cleanly on shutdown.

# 3. Dynamic prefix and help

Preserve prefix commands.

Implement:

```text
?prefix
?prefix <new-prefix>
```

Requirements:

* Default prefix: `?`
* Database-backed.
* Changes work immediately without restart.
* Mentioning only the bot returns the current prefix and help hint.
* Accept normal and nickname mention forms.
* Ignore bot messages.
* Prefix length and safety validation.
* No slash commands.

Implement a complete help command reflecting the final Python command structure.

Ensure `on_message` does not prevent command processing or call `process_commands()` more than once.

# 4. Single-server enforcement

The bot is designed for exactly one Discord server.

Apply the guild guard before:

* database reads;
* permission checks;
* Automod;
* moderation;
* queue logic;
* logging;
* scheduler actions.

Ignore foreign-guild messages and events silently.

For interactions that require acknowledgement, use a minimal ephemeral rejection without exposing configuration details.

# 5. SQLite schema and migrations

Use:

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
```

Implement numbered transactional migrations and `schema_migrations`.

Use normalized tables for at least:

* guild settings;
* staff roles;
* guild modules;
* warnings;
* staff notes;
* note revisions if implemented;
* case counters;
* moderation cases;
* timed actions;
* moderation queue;
* banned words;
* Automod ignored channels;
* Automod ignored roles;
* Automod links;
* lockdown channels;
* lockdown operations;
* lockdown channel snapshots;
* strike rules or strike configuration;
* any required operation-deduplication records.

Use:

* foreign keys;
* unique constraints;
* useful indexes;
* UTC timestamps;
* generated IDs;
* safe concurrent case numbering.

Use JSON columns only for genuinely flexible optional metadata.

Cases are the sole persistent moderation history.

Do not create a legacy `mod_logs` table in the new Python schema.

The configured Discord mod-log channel remains a live notification destination.

# 6. Legacy JSON importer

Create:

```text
python/scripts/import_legacy_json.py
```

It must import the final JavaScript `store.json` format into SQLite.

Requirements:

* Never modify the source JSON.
* Validate the JSON before import.
* Back up an existing SQLite database before import.
* Support dry-run mode.
* Avoid duplicate imports.
* Produce a summary.
* Log malformed or skipped records.
* Preserve supported data, including:

  * prefix;
  * guild settings;
  * staff roles;
  * modules;
  * warnings;
  * notes;
  * cases;
  * timed actions;
  * moderation queue;
  * banned words and modes;
  * ignored channels and roles;
  * link lists;
  * Automod thresholds;
  * lockdown channels;
  * active lockdown snapshots;
  * failed timed actions.

Do not import deprecated duplicate `mod_logs` records.

# 7. Authorization model

Implement reusable authorization services and decorators.

Administrator authorization includes:

* configured superusers;
* guild owner;
* native Discord Administrator;
* configured administrator roles.

Moderator authorization includes:

* all administrator-authorized users;
* configured moderator roles;
* Moderate Members;
* Manage Messages;
* any JavaScript-reference native moderator permissions still intentionally supported.

Superusers receive command authorization but do not bypass Discord hierarchy.

Implement:

```python
@moderator_required()
@administrator_required()
```

Use clear denial messages.

# 8. Hierarchy and target validation

Port the approved hierarchy model.

Enforce:

* self-target denied;
* guild owner cannot be targeted;
* issuer highest role must be above target;
* equal role denied;
* guild owner may bypass issuer-versus-target comparison;
* bot highest role must be above target;
* administrators do not bypass hierarchy;
* superusers do not bypass hierarchy;
* member-only actions require a member;
* raw user-ID bans may target non-members.

Return structured results with explicit denial reasons.

Use the same service for every target-based command and automated strike action.

# 9. Staff and configuration commands

Implement:

```text
?staff mod add @role
?staff mod remove @role|role-id
?staff mod list

?staff admin add @role
?staff admin remove @role|role-id
?staff admin list
```

Requirements:

* Administrator-only.
* Reject `@everyone`.
* Reject duplicates.
* Permit stale-ID removal.
* Show deleted roles clearly.
* Do not auto-delete stale configuration.

Implement:

```text
?module <name>
?modules
```

At minimum support:

```text
Automod
```

Use one module master switch only.

Do not recreate `automod_enabled`.

Implement:

```text
?modlog
?modlog #channel
?modlog off

?modqueue
?modqueue #channel
?modqueue off

?muterole
?muterole @role
?muterole off
```

Validate channel and bot permissions.

Reject invalid or unassignable mute roles.

# 10. Moderation cases

Cases are immutable historical records.

Implement:

```text
?case <case-number>
?case view <case-number>
?case list
?case list @user
```

Preserve sensible legacy aliases.

Cases should support:

* action;
* target;
* moderator;
* reason;
* source;
* status;
* date;
* warning linkage;
* queue linkage;
* timed-action linkage;
* duration/end time;
* failure reason;
* channel metadata where relevant.

Use pagination or chunking.

Do not allow normal case deletion or editing.

# 11. Warnings

Implement:

```text
?warn add <user> <reason>
?warn remove <warning-id>
?warn del <warning-id>
?warn clear <user>
?warn list [user]
?warn view <warning-id>
```

Preserve useful JavaScript aliases.

Requirements:

* Warning plus case created in one transaction.
* Strike evaluation only after commit.
* Show:

  * warning ID;
  * user;
  * moderator;
  * reason;
  * date;
  * linked case;
  * current status.
* Use active/voided semantics rather than destructive historical loss where practical.

Recommended cleanup:

* `remove` or `del` should void the warning rather than erase it.
* `clear` should void all active warnings for the user.
* Cases remain immutable.
* Strike counts use active warnings only.

If preserving hard deletion is necessary for exact parity, explain why and still preserve historical case evidence.

# 12. Strike escalation

Port and clean the strike system.

Requirements:

* Configurable enable state.
* Configurable thresholds and actions.
* Active-warning count, not raw lifetime deleted records.
* Deterministic threshold ordering.
* No accidental repeated action at the same threshold.
* Concurrent warnings must not duplicate escalation.
* Track which threshold has already been applied for the current warning state or offense cycle.
* Validate configured actions.
* Bot hierarchy enforced.
* Failure cases recorded accurately.
* Original warning remains if escalation fails.
* Temporary escalation persists case and timed reversal transactionally.
* Persistence failure after Discord action attempts rollback.
* Permanent escalation logging failure does not falsely report the Discord action as failed.

Implement administrator configuration and status commands matching the JavaScript reference where practical.

If the current JavaScript strike design allows unsafe repeated triggers, preserve the intended feature but correct the unsafe behavior in Python.

# 13. Staff notes

Implement:

```text
?note add <user> <text>
?note edit <note-id> <text>
?note remove <note-id>
?note del <note-id>
?note list <user>
?note view <note-id>
```

Requirements:

* Staff-only context.
* Notes do not count as warnings.
* Users are not notified.
* Notes do not trigger strikes.
* Show author and timestamps.
* Preserve updated timestamp.
* Prefer note revision history if reasonably implementable.
* Removal may soft-delete rather than erase.
* Notes should appear in staff-focused user history such as `?whois`, clearly separated from punishments.

# 14. Core moderation commands

Implement:

```text
?mod ban <user-or-id> [duration] [reason]
?mod unban <user-id> [reason]
?mod kick <member> [reason]
?mod softban <member> [reason]
?mod mute <member> [duration] [reason]
?mod unmute <member> [reason]
?mod deafen <member> [reason]
?mod undeafen <member> [reason]
```

Preserve the final JavaScript syntax and aliases where possible.

Requirements:

* Central target validation.
* Accurate member versus non-member behavior.
* Typed duration parser.
* Try/catch around Discord API calls.
* Cases for all meaningful moderation actions, including:

  * deafen;
  * undeafen.
* Mod-log channel notifications after case persistence.
* Notification failure does not invalidate the case.
* Permanent-action case failure reports partial success.
* Temporary action flow:

  1. Apply Discord action.
  2. Persist case and timed reversal transactionally.
  3. On persistence failure, attempt rollback.
  4. Report rollback success or manual intervention required.

# 15. Timed actions and scheduler

Implement a persistent scheduler using `discord.ext.tasks`.

Support:

* unban;
* unmute;
* channel permission restoration;
* lockdown channel restoration.

Requirements:

* Run immediately after ready.
* Poll around every 15 seconds.
* Claim actions safely.
* Avoid duplicate processing.
* Persist:

  * pending;
  * processing;
  * failed;
  * completed where useful.
* Retry transient failures.
* Missing permissions remain retryable.
* Use bounded backoff:

  * 30 seconds;
  * 1 minute;
  * 2 minutes;
  * capped at 5 minutes.
* Maximum attempts: 10.
* Retain terminal failed records for diagnostics.
* Sanitize stored errors.
* Do not flood mod logs.
* Overdue actions process after restart.
* Graceful shutdown stops scheduler safely.

Implement diagnostic output through an existing status command or a small administrator-only command for pending/failed timed actions.

# 16. Channel management

Implement:

```text
?channel lock [duration] [reason]
?channel unlock [reason]
?channel slowmode <duration|off>
```

Requirements:

* Exact `SendMessages` prior-state capture:

  * allow;
  * deny;
  * unset.
* Temporary locks persist through restart.
* Overlapping temporary locks keep the original pre-lock state and update the expiration.
* Manual unlock restores stored prior state.
* Manual conflict preserves later administrator changes.
* Failed restore retries.
* Cases and live logs.
* Do not blindly set permission to `true` or `null`.

# 17. Server lockdown

Implement the completed lockdown design:

```text
?channel lockdown channel add #channel
?channel lockdown channel remove #channel|channel-id
?channel lockdown channel list
?channel lockdown enable [reason]
?channel lockdown disable [reason]
?channel lockdown status
```

Preserve aliases:

```text
?channel lockdown
?channel lockdown end
```

Requirements:

* Administrator-only.
* Explicit configured channel list.
* Persistent active snapshot.
* Store prior states.
* One active lockdown.
* Concurrent enable/disable produces one winner.
* Continue through partial channel failures.
* Active if at least one channel succeeds.
* Total failure leaves inactive.
* Disabling restores only unchanged bot-applied states.
* Preserve manual changes.
* Deleted channels handled once.
* Transient restoration failures create retry actions.
* Failed restorations retained.
* Restart-safe.
* One summary case per operation.
* One live mod-log summary.

# 18. Purge

Port all working filters:

* count;
* user;
* match;
* not;
* startswith;
* endswith;
* links;
* invites;
* images;
* mentions;
* embeds;
* bots;
* humans;
* text.

Do not add the removed `after` filter.

Requirements:

* Moderator permission.
* Validate limits.
* Respect Discord bulk-delete age restrictions.
* Report deleted and skipped counts accurately.
* Create one case.
* Temporary UI-message deletion timers may remain in memory because they are not moderation state.

# 19. Native Discord audit lookup

Port the existing audit command.

Requirements:

* Clearly identify that it reads Discord’s native audit log.
* Require appropriate staff permission.
* Handle missing `View Audit Log`.
* Do not confuse it with internal cases or the live mod-log channel.
* Avoid exposing unnecessary sensitive information.

# 20. Information commands

Port:

* server info;
* channel info;
* user info;
* avatar;
* whois;
* any other working information commands found in the final JavaScript inventory.

`?whois` should show useful staff context:

* active warnings;
* recent cases;
* staff notes;
* relevant membership/account information.

Use pagination where necessary.

# 21. Automod master switch

Use the `Automod` module as the sole master switch.

Runtime order:

1. Configured guild.
2. Automod module enabled.
3. Ignored channel.
4. Ignored role.
5. Moderator bypass.
6. Individual checks.

Do not use a separate `automod_enabled` field.

# 22. Automod individual protections

Port:

* anti-spam;
* anti-caps;
* anti-invite;
* anti-mention;
* banned words;
* link blacklist;
* link whitelist;
* ignored channels;
* ignored roles;
* moderation queue;
* direct delete behavior.

Preserve moderator bypass policy from the final JavaScript implementation.

Do not persist spam tracker history.

# 23. Automod thresholds

Preserve:

* caps threshold default: 70%;
* fixed minimum alphabetic length: 8;
* spam count default: 5;
* spam window default: 5000 ms;
* mention threshold default: 5.

Ranges:

* caps: 50–100;
* spam count: 3–20;
* spam window: 1–60 seconds;
* mentions: 2–50.

Commands:

```text
?automod threshold caps <percentage>
?automod threshold spam-count <messages>
?automod threshold spam-window <duration>
?automod threshold mentions <count>
?automod threshold show
?automod threshold reset caps|spam|mentions|all
```

Requirements:

* Changing thresholds does not enable protections.
* Disabling protections does not erase thresholds.
* `@everyone` and `@here` always trigger anti-mention.
* Count user and role mentions according to Discord parsed mentions.
* Normalize legacy values during import.
* Clean stale spam tracker entries.
* Threshold changes apply immediately.

# 24. Automod ignore management

Implement:

```text
?automod ignore channel add #channel
?automod ignore channel remove #channel|channel-id
?automod ignore channel list

?automod ignore role add @role
?automod ignore role remove @role|role-id
?automod ignore role list
```

Preserve aliases:

```text
?automod ignorechannel
?automod ignorerole
?automod ignored
```

Requirements:

* Administrator-only.
* Reject `@everyone`.
* Remove stale IDs.
* List deleted entries.
* Ignore checks happen before expensive Automod work.
* Any ignored role bypasses Automod.

# 25. Banned words

Use one table and two modes:

```text
contains
exact
```

Commands:

```text
?automod word add contains <text>
?automod word add exact <text>
?automod word remove <entry-id>
?automod word list
```

Preserve aliases:

```text
?automod banword
?automod banexact
?automod unbanword
```

Matching:

### Contains

Case-insensitive substring.

### Exact

Case-insensitive escaped whole-token regex using word boundaries.

Requirements:

* Stable IDs.
* Same value allowed once per mode.
* Same value may exist in both modes.
* One database read per Automod message flow.
* First deterministic match.
* Log matched value and mode.
* Chunk large lists.

# 26. Link handling

Port blacklist and whitelist management.

Preserve:

* case-insensitive behavior where applicable;
* anti-invite;
* reliable non-stateful regex testing;
* multi-link extraction using a fresh local matcher;
* no global mutable regex state.

Audit and port the current JavaScript link commands exactly.

# 27. Moderation queue

Port the moderation queue with Discord buttons/views.

Requirements:

* Persistent queue entries.
* Pending/approved/denied states.
* Queue message ID stored.
* Approve and deny transitions are atomic.
* Only one moderator decision wins.
* Deny-with-warning transactionally:

  * marks denied;
  * creates warning;
  * creates case.
* Strike evaluation only after commit.
* Second moderator receives already-processed response.
* Persistent views re-register after restart.
* Unauthorized users cannot use queue buttons.
* Deleted queue messages handled safely.
* Queue disabled or unavailable follows existing direct-delete behavior.

# 28. Mod-log notifications

Implement a channel notification service.

Requirements:

* Cases persist independently from channel notifications.
* No database `mod_logs` table.
* Notification failures logged.
* No duplicate case creation.
* No token or full environment leakage.
* Clear embeds for:

  * moderation;
  * warnings;
  * strike success/failure;
  * queue decisions;
  * channel restoration;
  * lockdown;
  * timed action failures.

# 29. Error handling and response consistency

Implement a centralized command error handler.

Handle:

* missing arguments;
* bad user/member/role/channel conversion;
* permission denial;
* hierarchy denial;
* invalid duration;
* invalid setting;
* database errors;
* Discord API errors;
* unexpected errors.

Use consistent success and error embeds/messages.

Do not expose tracebacks or SQL to users.

Log unexpected failures with context.

# 30. Code cleanup requirements

While porting, clean up the design.

Remove or avoid:

* deprecated `anti_duplicate`;
* duplicate `automod_enabled`;
* deprecated database `mod_logs`;
* unused reaction intent;
* unused `CLIENT_ID`;
* unused `DEFAULT_PREFIX`;
* unimplemented purge `after`;
* unused exports;
* duplicate validation;
* dead compatibility code not needed in Python;
* JavaScript-specific workaround architecture.

Do not add:

* slash commands;
* fuzzy word matching;
* AI moderation;
* duplicate-message Automod;
* automatic inclusion of every channel in lockdown.

# 31. Backward-compatible command aliases

Preserve useful aliases already approved in the final JavaScript implementation.

All aliases must delegate to canonical Python handlers.

Do not duplicate business logic.

Document canonical syntax and legacy aliases.

# 32. Tests

Create comprehensive Python tests.

Use:

* pytest;
* pytest-asyncio;
* temporary SQLite databases;
* mocked Discord objects;
* service-level tests;
* command callback tests where useful.

Test at minimum:

## Foundation

* configuration validation;
* migration rerun;
* WAL and foreign keys;
* guild enforcement;
* graceful shutdown.

## Prefix/configuration

* dynamic prefix;
* mention discovery;
* staff roles;
* modules;
* mod-log channel;
* queue channel;
* mute role.

## Authorization

* superuser;
* owner;
* native admin;
* configured admin;
* configured moderator;
* native moderator permissions;
* ordinary member.

## Hierarchy

Port all approved scenarios.

## Database concurrency

* race-safe guild settings;
* case numbering;
* duplicate staff role prevention;
* queue decisions;
* lockdown enable/disable;
* duplicate ignore additions.

## Warnings/cases/notes

* atomic warning and case;
* active warning counts;
* warning voiding;
* note editing;
* immutable cases;
* user history.

## Moderation workflows

* temporary mute rollback;
* temporary ban rollback;
* permanent action logging failure;
* Discord failure before persistence;
* successful transactional timed action.

## Scheduler

* due processing;
* restart recovery;
* retries;
* max attempts;
* failed retention;
* missing permission recovery.

## Channel locks

* allow/deny/unset restoration;
* overlapping locks;
* manual conflict;
* manual unlock;
* deleted channel.

## Lockdown

Port all final JavaScript tests.

## Automod

* module disabled;
* ignored channels;
* ignored roles;
* banned words;
* invite detection;
* links;
* caps;
* mentions;
* spam;
* threshold updates;
* tracker pruning;
* moderator bypass.

## Queue

* concurrent decisions;
* unauthorized interaction;
* deny-with-warning;
* persistent view restart.

## Importer

* dry run;
* valid import;
* malformed records;
* duplicate prevention;
* backup;
* deprecated mod-log skip.

## Commands

* canonical syntax;
* retained aliases;
* safe error messages;
* list chunking or pagination.

# 33. Quality gates

Run from `python/`:

```bash
python -m pytest
ruff check .
ruff format --check .
```

Also run:

```bash
python -m compileall bot
```

There must be:

* no failing tests;
* no Ruff errors;
* no format drift;
* no syntax errors.

If mypy or Pyright is configured, run it too and report the result.

# 34. Feature parity audit

Create:

```text
docs/PYTHON_FEATURE_PARITY.md
```

For every feature in the final JavaScript inventory, mark:

* Ported;
* Ported with intentional cleanup;
* Replaced by safer behavior;
* Not ported, with exact reason.

Do not claim full parity while approved features remain missing.

# 35. Documentation

Update:

```text
python/README.md
docs/PYTHON_MIGRATION_PLAN.md
docs/PYTHON_FEATURE_PARITY.md
```

Document:

* installation;
* environment;
* SQLite database;
* migration;
* JSON import;
* commands;
* permissions;
* modules;
* moderation;
* warnings;
* strikes;
* notes;
* cases;
* timed actions;
* channel lock;
* lockdown;
* Automod;
* queue;
* troubleshooting;
* backup recommendations;
* test commands.

Update the root README only to state:

* JavaScript is the legacy reference;
* Python is the new production implementation;
* where to find Python setup instructions.

Do not rewrite JavaScript documentation as though it is still production.

# 36. Final cleanup audit

Before reporting completion:

1. Search the Python project for:

   * TODO
   * FIXME
   * pass
   * NotImplementedError
   * placeholder
   * temporary stub
   * mock production implementation

2. Distinguish legitimate:

   * empty `__init__.py`;
   * abstract interfaces;
   * test mocks.

3. Remove all production placeholders for approved features.

4. Search for:

   * synchronous SQLite calls;
   * direct SQL in cogs;
   * un-awaited coroutines;
   * duplicate command names;
   * unused imports;
   * dead modules;
   * broad exception swallowing;
   * token logging.

5. Confirm every cog is loaded.

6. Confirm every command appears in help.

7. Confirm scheduler and persistent views start correctly.

8. Confirm tests never use the production database.

# 37. Final execution report

Only after the full conversion is complete, report:

* Python version;
* dependencies;
* complete file list created/changed;
* final architecture;
* database tables and migrations;
* all commands implemented;
* aliases preserved;
* all features ported;
* intentional behavior improvements;
* deprecated functionality removed;
* importer behavior;
* test count;
* test results;
* Ruff results;
* format results;
* compile results;
* remaining known limitations;
* JavaScript files confirmed unchanged.

Do not stop after Stage 2 or any other intermediate milestone.

Complete the total conversion and code cleanup in this single task.
