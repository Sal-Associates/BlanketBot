import { writeFile, rename, copyFile, unlink, mkdir } from 'fs/promises';
import { existsSync, copyFileSync, readFileSync } from 'fs';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';
import { platform } from 'os';
import { AUTOMOD_THRESHOLD_DEFAULTS, normalizeAutomodThresholds } from '../utils/automodThresholds.js';

const __dirname = dirname(fileURLToPath(import.meta.url));

let dbPath = process.env.STORE_PATH || join(__dirname, '../../data/store.json');
let dataDir = dirname(dbPath);
let testHooks = {};

let writeQueue = Promise.resolve();

export class DatabaseError extends Error {
  constructor(message, cause) {
    super(message);
    this.name = 'DatabaseError';
    this.cause = cause;
  }
}

export class DatabaseFatalError extends DatabaseError {
  constructor(message, cause) {
    super(message, cause);
    this.name = 'DatabaseFatalError';
  }
}

const defaultData = {
  guild_settings: {},
  mod_roles: [],
  admin_roles: [],
  warnings: [],
  notes: [],
  /** @deprecated Legacy collection — no longer written; preserved for existing databases. */
  mod_logs: [],
  /** @deprecated Legacy collection — migrated to banned_words; preserved on disk. */
  automod_words: [],
  banned_words: [],
  automod_links: [],
  automod_ignored_channels: [],
  automod_ignored_roles: [],
  timed_actions: [],
  cases: [],
  mod_queue: [],
  case_counters: {},
  _counters: { warnings: 0, notes: 0, mod_logs: 0, timed_actions: 0, mod_queue: 0, banned_words: 0 },
};

const defaultSettings = {
  prefix: '?',
  mod_log_channel: null,
  mute_role: null,
  anti_spam: 1,
  anti_caps: 0,
  anti_invite: 0,
  anti_mention: 0,
  ...AUTOMOD_THRESHOLD_DEFAULTS,
  lockdown_channels: '[]',
  lockdown_state: null,
  disabled_modules: '[]',
  mod_queue_channel: null,
  mod_queue_enabled: 0,
  strike_mute_at: 3,
  strike_ban_at: 5,
  strike_enabled: 1,
};

export function configureDatabase({ path, hooks } = {}) {
  if (path) {
    dbPath = path;
    dataDir = dirname(path);
  }
  if (hooks) {
    testHooks = hooks;
  }
}

export function getDatabasePath() {
  return dbPath;
}

function corruptTimestamp() {
  return new Date().toISOString().replace(/[:.]/g, '-');
}

function validateDatabaseStructure(data) {
  if (!data || typeof data !== 'object' || Array.isArray(data)) return false;
  return Object.keys(defaultData).every((key) => key in data);
}

function parseDisabledModules(raw) {
  try {
    const parsed = JSON.parse(raw ?? '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function migrateAutomodModuleState(rawGuildSettings, mergedSettings) {
  const disabled = parseDisabledModules(rawGuildSettings.disabled_modules ?? mergedSettings.disabled_modules);

  if (disabled.includes('Automod')) {
    mergedSettings._automod_module_migrated = 1;
    return false;
  }

  if (rawGuildSettings._automod_module_migrated) {
    return false;
  }

  let changed = false;
  if ('automod_enabled' in rawGuildSettings && !rawGuildSettings.automod_enabled) {
    disabled.push('Automod');
    mergedSettings.disabled_modules = JSON.stringify(disabled);
    changed = true;
  }

  mergedSettings._automod_module_migrated = 1;
  if (!rawGuildSettings._automod_module_migrated) {
    changed = true;
  }

  return changed;
}

function bannedWordKey(guildId, value, matchMode) {
  return `${guildId}:${value}:${matchMode}`;
}

function migrateBannedWords(data) {
  data.banned_words = Array.isArray(data.banned_words) ? data.banned_words : [];
  if (data._banned_words_migrated) {
    return false;
  }

  let changed = false;
  const seen = new Set(
    data.banned_words.map((entry) => bannedWordKey(entry.guild_id, entry.value, entry.match_mode)),
  );

  for (const legacy of data.automod_words ?? []) {
    const value = String(legacy.word ?? legacy.value ?? '').trim().toLowerCase();
    if (!value) continue;
    const matchMode = legacy.exact === 1 || legacy.exact === true || legacy.match_mode === 'exact'
      ? 'exact'
      : 'contains';
    const key = bannedWordKey(legacy.guild_id, value, matchMode);
    if (seen.has(key)) continue;

    const id = nextId(data, 'banned_words');
    data.banned_words.push({
      id,
      guild_id: legacy.guild_id,
      value,
      match_mode: matchMode,
      created_at: legacy.created_at ?? Date.now(),
      created_by: legacy.created_by ?? null,
    });
    seen.add(key);
    changed = true;
  }

  for (const entry of data.banned_words) {
    if (!entry.id) {
      entry.id = nextId(data, 'banned_words');
      changed = true;
    }
  }

  data._banned_words_migrated = true;
  return true;
}

function normalizeDatabase(raw) {
  const data = { ...structuredClone(defaultData), ...raw };
  data._counters = { ...structuredClone(defaultData._counters), ...(raw._counters ?? {}) };
  data.case_counters = { ...(raw.case_counters ?? {}) };

  let migrationPending = false;
  for (const [guildId, rawGuildSettings] of Object.entries(data.guild_settings ?? {})) {
    const merged = { guild_id: guildId, ...defaultSettings, ...rawGuildSettings };
    if (migrateAutomodModuleState(rawGuildSettings, merged)) {
      migrationPending = true;
    }
    const normalized = normalizeAutomodThresholds(merged);
    for (const key of Object.keys(AUTOMOD_THRESHOLD_DEFAULTS)) {
      if (merged[key] !== normalized[key]) {
        migrationPending = true;
      }
    }
    data.guild_settings[guildId] = normalized;
  }

  if (migrateBannedWords(data)) {
    migrationPending = true;
  }

  if (migrationPending) {
    data._migrationPending = true;
  }

  return data;
}

function loadDatabaseFromDisk() {
  if (!existsSync(dbPath)) return null;

  let raw;
  try {
    raw = readFileSync(dbPath, 'utf8');
  } catch (err) {
    throw new DatabaseError(`Failed to read database at ${dbPath}`, err);
  }

  let parsed;
  try {
    parsed = JSON.parse(raw);
  } catch (err) {
    const corruptName = `store.json.corrupt-${corruptTimestamp()}`;
    const corruptPath = join(dataDir, corruptName);
    copyFileSync(dbPath, corruptPath);
    throw new DatabaseFatalError(
      `Invalid JSON in database at ${dbPath}. Preserved copy at ${corruptPath}. Repair or replace the database before starting.`,
      err,
    );
  }

  if (!validateDatabaseStructure({ ...structuredClone(defaultData), ...parsed })) {
    const corruptName = `store.json.corrupt-${corruptTimestamp()}`;
    const corruptPath = join(dataDir, corruptName);
    copyFileSync(dbPath, corruptPath);
    throw new DatabaseFatalError(
      `Database at ${dbPath} has an invalid structure. Preserved copy at ${corruptPath}.`,
    );
  }

  return normalizeDatabase(parsed);
}

async function saveDatabaseAtomic(data, { skipBackup = false } = {}) {
  const json = JSON.stringify(data, null, 2);
  const tmpPath = `${dbPath}.tmp`;
  const bakPath = `${dbPath}.bak`;

  await mkdir(dataDir, { recursive: true });
  await writeFile(tmpPath, json, 'utf8');

  if (!skipBackup && existsSync(dbPath)) {
    await copyFile(dbPath, bakPath);
  }

  try {
    const doRename = testHooks.rename ?? rename;
    if (platform() === 'win32' && existsSync(dbPath)) {
      await unlink(dbPath);
    }
    await doRename(tmpPath, dbPath);
  } catch (err) {
    if (platform() === 'win32' && !existsSync(dbPath) && existsSync(bakPath)) {
      try {
        await copyFile(bakPath, dbPath);
      } catch {
        // ignore restore failure
      }
    }
    try {
      await unlink(tmpPath);
    } catch {
      // ignore cleanup failure
    }
    throw new DatabaseError(`Failed to save database at ${dbPath}`, err);
  }
}

async function loadDatabaseForMutation() {
  await mkdir(dataDir, { recursive: true });
  const existing = loadDatabaseFromDisk();
  if (existing) return existing;

  const data = structuredClone(defaultData);
  await saveDatabaseAtomic(data, { skipBackup: true });
  return data;
}

export async function readDatabase() {
  await writeQueue.catch(() => {});
  const data = loadDatabaseFromDisk();
  return data ? data : structuredClone(defaultData);
}

export async function mutateDatabase(mutator) {
  const operation = writeQueue.then(async () => {
    const data = await loadDatabaseForMutation();
    const result = await mutator(data);
    if ((testHooks.failNextMutations ?? 0) > 0) {
      testHooks.failNextMutations--;
      throw new DatabaseError('Simulated mutation failure');
    }
    await saveDatabaseAtomic(data);
    return result;
  });

  writeQueue = operation.catch((err) => {
    console.error('[database] Mutation failed:', err.message);
  });

  return operation;
}

export async function initializeDatabase() {
  await mkdir(dataDir, { recursive: true });
  if (!existsSync(dbPath)) {
    await saveDatabaseAtomic(structuredClone(defaultData), { skipBackup: true });
    return;
  }

  const data = loadDatabaseFromDisk();
  if (data?._migrationPending) {
    delete data._migrationPending;
    await saveDatabaseAtomic(data);
  }
}

export async function flushDatabaseQueue(timeoutMs = 5000) {
  const timeout = new Promise((_, reject) => {
    setTimeout(() => reject(new Error('Database flush timeout')), timeoutMs);
  });
  await Promise.race([writeQueue, timeout]);
}

function nextId(data, key) {
  data._counters[key] = (data._counters[key] || 0) + 1;
  return data._counters[key];
}

function ensureGuildSettings(data, guildId) {
  if (!data.guild_settings[guildId]) {
    data.guild_settings[guildId] = { guild_id: guildId, ...defaultSettings };
  }
  return data.guild_settings[guildId];
}

function guildSettingsFromData(data, guildId) {
  if (!data.guild_settings[guildId]) {
    return normalizeAutomodThresholds({ guild_id: guildId, ...defaultSettings });
  }
  return normalizeAutomodThresholds({
    guild_id: guildId,
    ...defaultSettings,
    ...data.guild_settings[guildId],
  });
}

export async function getGuildSettings(guildId) {
  return mutateDatabase((data) => {
    ensureGuildSettings(data, guildId);
    return guildSettingsFromData(data, guildId);
  });
}

export async function updateGuildSetting(guildId, key, value) {
  return mutateDatabase((data) => {
    ensureGuildSettings(data, guildId);
    data.guild_settings[guildId][key] = value;
  });
}

export async function updateGuildSettings(guildId, updates) {
  return mutateDatabase((data) => {
    ensureGuildSettings(data, guildId);
    for (const [key, value] of Object.entries(updates)) {
      data.guild_settings[guildId][key] = value;
    }
  });
}

export async function getModRoles(guildId) {
  const data = await readDatabase();
  return data.mod_roles.filter((r) => r.guild_id === guildId).map((r) => r.role_id);
}

export async function addModRole(guildId, roleId) {
  return mutateDatabase((data) => {
    if (!data.mod_roles.some((r) => r.guild_id === guildId && r.role_id === roleId)) {
      data.mod_roles.push({ guild_id: guildId, role_id: roleId });
    }
  });
}

export async function removeModRole(guildId, roleId) {
  return mutateDatabase((data) => {
    data.mod_roles = data.mod_roles.filter((r) => !(r.guild_id === guildId && r.role_id === roleId));
  });
}

export async function getAdminRoles(guildId) {
  const data = await readDatabase();
  return data.admin_roles.filter((r) => r.guild_id === guildId).map((r) => r.role_id);
}

export async function addAdminRole(guildId, roleId) {
  return mutateDatabase((data) => {
    if (!data.admin_roles.some((r) => r.guild_id === guildId && r.role_id === roleId)) {
      data.admin_roles.push({ guild_id: guildId, role_id: roleId });
    }
  });
}

export async function removeAdminRole(guildId, roleId) {
  return mutateDatabase((data) => {
    data.admin_roles = data.admin_roles.filter((r) => !(r.guild_id === guildId && r.role_id === roleId));
  });
}

export async function addWarning(guildId, userId, moderatorId, reason) {
  return mutateDatabase((data) => {
    const id = nextId(data, 'warnings');
    data.warnings.push({ id, guild_id: guildId, user_id: userId, moderator_id: moderatorId, reason, created_at: Date.now() });
    return id;
  });
}

export async function getWarnings(guildId, userId) {
  const data = await readDatabase();
  return data.warnings.filter((w) => w.guild_id === guildId && w.user_id === userId).sort((a, b) => b.created_at - a.created_at);
}

export async function deleteWarning(id) {
  return mutateDatabase((data) => {
    const before = data.warnings.length;
    data.warnings = data.warnings.filter((w) => w.id !== id);
    return { changes: before - data.warnings.length };
  });
}

export async function clearWarnings(guildId, userId) {
  return mutateDatabase((data) => {
    data.warnings = data.warnings.filter((w) => !(w.guild_id === guildId && w.user_id === userId));
  });
}

export async function addNote(guildId, userId, moderatorId, content) {
  return mutateDatabase((data) => {
    const id = nextId(data, 'notes');
    data.notes.push({ id, guild_id: guildId, user_id: userId, moderator_id: moderatorId, content, created_at: Date.now() });
    return id;
  });
}

export async function getNotes(guildId, userId) {
  const data = await readDatabase();
  return data.notes.filter((n) => n.guild_id === guildId && n.user_id === userId).sort((a, b) => b.created_at - a.created_at);
}

export async function deleteNote(id) {
  return mutateDatabase((data) => {
    const before = data.notes.length;
    data.notes = data.notes.filter((n) => n.id !== id);
    return { changes: before - data.notes.length };
  });
}

export async function updateNote(id, content) {
  return mutateDatabase((data) => {
    const note = data.notes.find((n) => n.id === id);
    if (note) note.content = content;
    return { changes: note ? 1 : 0 };
  });
}

function createCaseInData(data, guildId, userId, moderatorId, action, reason, extra = {}) {
  if (!data.case_counters[guildId]) data.case_counters[guildId] = 0;
  data.case_counters[guildId]++;
  const caseNumber = data.case_counters[guildId];

  data.cases.push({
    case_number: caseNumber,
    guild_id: guildId,
    user_id: userId,
    moderator_id: moderatorId,
    action,
    reason,
    extra,
    created_at: Date.now(),
  });

  return caseNumber;
}

export async function createCase(guildId, userId, moderatorId, action, reason, extra = {}) {
  return mutateDatabase((data) => createCaseInData(data, guildId, userId, moderatorId, action, reason, extra));
}

function createWarningInData(data, guildId, userId, moderatorId, reason, source = null) {
  const warningId = nextId(data, 'warnings');
  data.warnings.push({
    id: warningId,
    guild_id: guildId,
    user_id: userId,
    moderator_id: moderatorId,
    reason,
    source,
    created_at: Date.now(),
  });
  return warningId;
}

function createTimedActionInData(data, guildId, userId, action, endsAt, extra = {}) {
  const timedActionId = nextId(data, 'timed_actions');
  data.timed_actions.push({
    id: timedActionId,
    guild_id: guildId,
    user_id: userId,
    action,
    ends_at: endsAt,
    status: 'pending',
    attempt_count: 0,
    ...extra,
  });
  return timedActionId;
}

export async function createWarningWithCase({
  guildId,
  userId,
  moderatorId,
  reason,
  source = null,
  extra = {},
}) {
  return mutateDatabase((data) => {
    const warningId = createWarningInData(data, guildId, userId, moderatorId, reason, source);
    const caseNumber = createCaseInData(data, guildId, userId, moderatorId, 'warn', reason, {
      warning_id: warningId,
      source,
      ...extra,
    });
    return { warningId, caseNumber };
  });
}

export async function createTemporaryPunishmentRecords({
  guildId,
  userId,
  moderatorId,
  caseAction,
  caseReason,
  timedAction,
  endsAt,
  extra = {},
}) {
  return mutateDatabase((data) => {
    const timedActionId = createTimedActionInData(data, guildId, userId, timedAction, endsAt);
    const caseNumber = createCaseInData(data, guildId, userId, moderatorId, caseAction, caseReason, {
      source: 'moderation',
      ends_at: endsAt,
      timed_action: timedAction,
      timed_action_id: timedActionId,
      ...extra,
    });
    return { caseNumber, timedActionId };
  });
}

export async function processModQueueDecision({
  entryId,
  moderatorId,
  decision,
  warnReason = null,
  caseAction,
  caseReason,
}) {
  return mutateDatabase((data) => {
    const entry = data.mod_queue.find((q) => q.id === entryId);
    if (!entry) return { status: 'not_found' };
    if (entry.status !== 'pending') {
      return { status: 'already_processed', currentStatus: entry.status };
    }

    entry.status = decision === 'approve' ? 'approved' : 'denied';

    if (decision === 'approve') {
      const caseNumber = createCaseInData(
        data,
        entry.guild_id,
        entry.author_id,
        moderatorId,
        caseAction,
        caseReason,
        { source: 'mod_queue', queue_id: entryId },
      );
      return {
        status: 'success',
        decision: 'approved',
        caseNumber,
        entry: { ...entry },
      };
    }

    if (!warnReason) {
      return {
        status: 'success',
        decision: 'denied',
        entry: { ...entry },
      };
    }

    const warningId = createWarningInData(
      data,
      entry.guild_id,
      entry.author_id,
      moderatorId,
      warnReason,
      'mod_queue',
    );
    const caseNumber = createCaseInData(
      data,
      entry.guild_id,
      entry.author_id,
      moderatorId,
      caseAction,
      caseReason,
      { warning_id: warningId, source: 'mod_queue', queue_id: entryId },
    );
    return {
      status: 'success',
      decision: 'denied',
      warningId,
      caseNumber,
      entry: { ...entry },
    };
  });
}

export async function getCase(guildId, caseNumber) {
  const data = await readDatabase();
  return data.cases.find((c) => c.guild_id === guildId && c.case_number === caseNumber);
}

export async function getCasesForUser(guildId, userId, limit = 15) {
  const data = await readDatabase();
  return data.cases
    .filter((c) => c.guild_id === guildId && c.user_id === userId)
    .sort((a, b) => b.case_number - a.case_number)
    .slice(0, limit);
}

export async function getRecentCases(guildId, limit = 10) {
  const data = await readDatabase();
  return data.cases
    .filter((c) => c.guild_id === guildId)
    .sort((a, b) => b.case_number - a.case_number)
    .slice(0, limit);
}

export async function addModQueueEntry(guildId, channelId, authorId, content, reason) {
  return mutateDatabase((data) => {
    const id = nextId(data, 'mod_queue');
    const entry = {
      id,
      guild_id: guildId,
      channel_id: channelId,
      author_id: authorId,
      content,
      reason,
      queue_message_id: null,
      status: 'pending',
      created_at: Date.now(),
    };
    data.mod_queue.push(entry);
    return entry;
  });
}

export async function getModQueueEntry(id) {
  const data = await readDatabase();
  return data.mod_queue.find((q) => q.id === id);
}

export async function setModQueueMessageId(id, messageId) {
  return mutateDatabase((data) => {
    const entry = data.mod_queue.find((q) => q.id === id);
    if (entry) entry.queue_message_id = messageId;
  });
}

export async function addBannedWord(guildId, value, mode, moderatorId = null) {
  const trimmed = String(value ?? '').trim();
  if (!trimmed) {
    throw new DatabaseError('Banned word value cannot be empty');
  }

  const matchMode = mode?.toLowerCase();
  if (matchMode !== 'contains' && matchMode !== 'exact') {
    throw new DatabaseError(`Invalid match mode: ${mode}`);
  }

  const storedValue = trimmed.toLowerCase();

  return mutateDatabase((data) => {
    data.banned_words = data.banned_words ?? [];
    const duplicate = data.banned_words.some(
      (entry) => entry.guild_id === guildId && entry.value === storedValue && entry.match_mode === matchMode,
    );
    if (duplicate) {
      throw new DatabaseError('duplicate_banned_word');
    }

    const id = nextId(data, 'banned_words');
    data.banned_words.push({
      id,
      guild_id: guildId,
      value: storedValue,
      match_mode: matchMode,
      created_at: Date.now(),
      created_by: moderatorId,
    });
    return id;
  });
}

export async function removeBannedWord(guildId, entryId) {
  return mutateDatabase((data) => {
    const before = data.banned_words.length;
    data.banned_words = data.banned_words.filter(
      (entry) => !(entry.guild_id === guildId && entry.id === entryId),
    );
    return { removed: before - data.banned_words.length };
  });
}

export async function removeBannedWordByValue(guildId, value, mode = 'contains') {
  const storedValue = String(value ?? '').trim().toLowerCase();
  const matchMode = mode?.toLowerCase();
  return mutateDatabase((data) => {
    const before = data.banned_words.length;
    data.banned_words = data.banned_words.filter(
      (entry) => !(entry.guild_id === guildId && entry.value === storedValue && entry.match_mode === matchMode),
    );
    return { removed: before - data.banned_words.length };
  });
}

export async function getBannedWords(guildId) {
  const data = await readDatabase();
  return data.banned_words.filter((entry) => entry.guild_id === guildId);
}

export async function addAutomodLink(guildId, link, type) {
  return mutateDatabase((data) => {
    const entry = { guild_id: guildId, link: link.toLowerCase(), type };
    if (!data.automod_links.some((l) => l.guild_id === guildId && l.link === entry.link && l.type === type)) {
      data.automod_links.push(entry);
    }
  });
}

export async function removeAutomodLink(guildId, link, type) {
  return mutateDatabase((data) => {
    data.automod_links = data.automod_links.filter((l) => !(l.guild_id === guildId && l.link === link.toLowerCase() && l.type === type));
  });
}

export async function getAutomodLinks(guildId, type) {
  const data = await readDatabase();
  return data.automod_links.filter((l) => l.guild_id === guildId && l.type === type).map((l) => l.link);
}

export async function addIgnoredChannel(guildId, channelId) {
  return mutateDatabase((data) => {
    if (data.automod_ignored_channels.some((c) => c.guild_id === guildId && c.channel_id === channelId)) {
      throw new DatabaseError('duplicate_ignored_channel');
    }
    data.automod_ignored_channels.push({ guild_id: guildId, channel_id: channelId });
    return { added: true };
  });
}

export async function removeIgnoredChannel(guildId, channelId) {
  return mutateDatabase((data) => {
    const before = data.automod_ignored_channels.length;
    data.automod_ignored_channels = data.automod_ignored_channels.filter(
      (c) => !(c.guild_id === guildId && c.channel_id === channelId),
    );
    return { removed: before - data.automod_ignored_channels.length };
  });
}

export async function getIgnoredChannels(guildId) {
  const data = await readDatabase();
  return data.automod_ignored_channels.filter((c) => c.guild_id === guildId).map((c) => c.channel_id);
}

export async function addIgnoredRole(guildId, roleId) {
  return mutateDatabase((data) => {
    if (data.automod_ignored_roles.some((r) => r.guild_id === guildId && r.role_id === roleId)) {
      throw new DatabaseError('duplicate_ignored_role');
    }
    data.automod_ignored_roles.push({ guild_id: guildId, role_id: roleId });
    return { added: true };
  });
}

export async function removeIgnoredRole(guildId, roleId) {
  return mutateDatabase((data) => {
    const before = data.automod_ignored_roles.length;
    data.automod_ignored_roles = data.automod_ignored_roles.filter(
      (r) => !(r.guild_id === guildId && r.role_id === roleId),
    );
    return { removed: before - data.automod_ignored_roles.length };
  });
}

export async function getIgnoredRoles(guildId) {
  const data = await readDatabase();
  return data.automod_ignored_roles.filter((r) => r.guild_id === guildId).map((r) => r.role_id);
}

function parseLockdownChannelIds(raw) {
  try {
    const parsed = JSON.parse(raw ?? '[]');
    return Array.isArray(parsed) ? parsed.filter((id) => typeof id === 'string' && id.length > 0) : [];
  } catch {
    return [];
  }
}

export function parseLockdownState(raw) {
  if (!raw) return null;
  try {
    const state = typeof raw === 'string' ? JSON.parse(raw) : raw;
    return state && typeof state === 'object' ? state : null;
  } catch {
    return null;
  }
}

export async function addLockdownChannel(guildId, channelId) {
  return mutateDatabase((data) => {
    ensureGuildSettings(data, guildId);
    const settings = data.guild_settings[guildId];
    const channels = parseLockdownChannelIds(settings.lockdown_channels);
    if (channels.includes(channelId)) {
      throw new DatabaseError('duplicate_lockdown_channel');
    }
    channels.push(channelId);
    settings.lockdown_channels = JSON.stringify(channels);
    return channels;
  });
}

export async function removeLockdownChannel(guildId, channelId) {
  return mutateDatabase((data) => {
    ensureGuildSettings(data, guildId);
    const settings = data.guild_settings[guildId];
    const before = parseLockdownChannelIds(settings.lockdown_channels);
    const channels = before.filter((id) => id !== channelId);
    settings.lockdown_channels = JSON.stringify(channels);
    return { removed: before.length - channels.length };
  });
}

export async function getLockdownChannels(guildId) {
  const settings = await getGuildSettings(guildId);
  return parseLockdownChannelIds(settings.lockdown_channels);
}

export async function getLockdownState(guildId) {
  const settings = await getGuildSettings(guildId);
  return parseLockdownState(settings.lockdown_state);
}

export async function setLockdownState(guildId, state) {
  return mutateDatabase((data) => {
    ensureGuildSettings(data, guildId);
    data.guild_settings[guildId].lockdown_state = state ? JSON.stringify(state) : null;
    return state;
  });
}

export async function acquireLockdownEnable(guildId, meta) {
  return mutateDatabase((data) => {
    ensureGuildSettings(data, guildId);
    const settings = data.guild_settings[guildId];
    const existing = parseLockdownState(settings.lockdown_state);
    if (existing?.active) {
      return { ok: false, reason: 'already_active', state: existing };
    }
    const newState = {
      active: true,
      started_at: Date.now(),
      started_by: meta.moderatorId,
      reason: meta.reason ?? 'No reason provided',
      role_id: meta.roleId,
      permission: meta.permission ?? 'SendMessages',
      channels: [],
    };
    settings.lockdown_state = JSON.stringify(newState);
    return { ok: true, state: newState };
  });
}

export async function acquireLockdownDisable(guildId) {
  return mutateDatabase((data) => {
    ensureGuildSettings(data, guildId);
    const settings = data.guild_settings[guildId];
    const state = parseLockdownState(settings.lockdown_state);
    if (!state?.active) {
      return { ok: false, reason: 'not_active', state };
    }
    state.active = false;
    state.disabling = true;
    settings.lockdown_state = JSON.stringify(state);
    return { ok: true, state: { ...state, active: true, channels: state.channels ?? [] } };
  });
}

export async function clearLockdownState(guildId) {
  return setLockdownState(guildId, null);
}

export async function finalizeLockdownEnable(guildId, channelResults) {
  return mutateDatabase((data) => {
    ensureGuildSettings(data, guildId);
    const settings = data.guild_settings[guildId];
    const state = parseLockdownState(settings.lockdown_state);
    if (!state?.active) {
      throw new DatabaseError('no_active_lockdown');
    }
    state.channels = channelResults;
    settings.lockdown_state = JSON.stringify(state);
    return state;
  });
}

export async function finalizeLockdownDisable(guildId, meta) {
  return mutateDatabase((data) => {
    ensureGuildSettings(data, guildId);
    const settings = data.guild_settings[guildId];
    const state = parseLockdownState(settings.lockdown_state) ?? {};
    const nextState = {
      active: false,
      disabling: false,
      last_disabled_at: Date.now(),
      last_disabled_by: meta.moderatorId,
      disable_reason: meta.reason ?? 'No reason provided',
      disable_summary: meta.summary,
      role_id: state.role_id ?? meta.roleId,
      permission: state.permission ?? 'SendMessages',
      channels: meta.channelResults ?? state.channels ?? [],
      started_at: state.started_at ?? null,
      started_by: state.started_by ?? null,
      reason: state.reason ?? null,
    };
    settings.lockdown_state = JSON.stringify(nextState);
    return nextState;
  });
}

export async function addLockdownRestoreAction({
  guildId,
  channelId,
  roleId,
  permission,
  previousState,
  appliedState,
}) {
  return mutateDatabase((data) => {
    const existing = data.timed_actions.find((a) =>
      a.guild_id === guildId
      && a.channel_id === channelId
      && a.action === 'lockdown_channel_restore'
      && (a.status ?? 'pending') === 'pending',
    );
    if (existing) return existing.id;

    const id = nextId(data, 'timed_actions');
    data.timed_actions.push({
      id,
      guild_id: guildId,
      channel_id: channelId,
      role_id: roleId,
      user_id: null,
      action: 'lockdown_channel_restore',
      permission,
      previous_state: previousState,
      applied_state: appliedState,
      ends_at: Date.now(),
      status: 'pending',
      attempt_count: 0,
      last_attempt_at: null,
      last_error: null,
      last_logged_error: null,
      next_retry_at: null,
    });
    return id;
  });
}

export async function getLockdownRestoreDiagnostics(guildId = null) {
  const data = await readDatabase();
  const now = Date.now();
  const actions = data.timed_actions.filter((a) =>
    a.action === 'lockdown_channel_restore'
    && (!guildId || a.guild_id === guildId),
  );

  const mapAction = (a) => ({
    id: a.id,
    guild_id: a.guild_id,
    channel_id: a.channel_id,
    permission: a.permission,
    previous_state: a.previous_state,
    applied_state: a.applied_state,
    attempt_count: a.attempt_count ?? 0,
    last_error: a.last_error ?? null,
    next_retry_at: a.next_retry_at ?? null,
    due: isTimedActionDue(a, now),
  });

  return {
    pending: actions.filter((a) => (a.status ?? 'pending') === 'pending').map(mapAction),
    failed: actions.filter((a) => a.status === 'failed').map(mapAction),
  };
}

export async function addTimedAction(guildId, userId, action, endsAt, extra = {}) {
  return mutateDatabase((data) => {
    const id = nextId(data, 'timed_actions');
    data.timed_actions.push({ id, guild_id: guildId, user_id: userId, action, ends_at: endsAt, ...extra });
    return id;
  });
}

export async function upsertChannelTimedAction({
  guildId,
  channelId,
  roleId,
  action,
  permission,
  previousState,
  appliedState,
  endsAt,
  moderatorId,
}) {
  return mutateDatabase((data) => {
    const existing = data.timed_actions.find((a) =>
      a.guild_id === guildId
      && a.channel_id === channelId
      && a.action === action
      && a.permission === permission
      && (a.status ?? 'pending') === 'pending'
    );

    if (existing) {
      existing.ends_at = endsAt;
      existing.applied_state = appliedState;
      existing.moderator_id = moderatorId;
      existing.role_id = roleId;
      existing.previous_state = existing.previous_state ?? previousState;
      existing.attempt_count = 0;
      existing.last_attempt_at = null;
      existing.last_error = null;
      existing.last_logged_error = null;
      existing.next_retry_at = null;
      return existing.id;
    }

    const id = nextId(data, 'timed_actions');
    data.timed_actions.push({
      id,
      guild_id: guildId,
      channel_id: channelId,
      role_id: roleId,
      user_id: null,
      action,
      permission,
      previous_state: previousState,
      applied_state: appliedState,
      ends_at: endsAt,
      moderator_id: moderatorId,
      status: 'pending',
      attempt_count: 0,
      last_attempt_at: null,
      last_error: null,
      last_logged_error: null,
      next_retry_at: null,
    });
    return id;
  });
}

export async function cancelChannelTimedActions(guildId, channelId, action, permission) {
  return mutateDatabase((data) => {
    const before = data.timed_actions.length;
    data.timed_actions = data.timed_actions.filter((a) => !(
      a.guild_id === guildId
      && a.channel_id === channelId
      && a.action === action
      && a.permission === permission
      && (a.status ?? 'pending') === 'pending'
    ));
    return { removed: before - data.timed_actions.length };
  });
}

export async function getPendingChannelTimedActions(guildId, channelId, action, permission) {
  const data = await readDatabase();
  return data.timed_actions.filter((a) =>
    a.guild_id === guildId
    && a.channel_id === channelId
    && a.action === action
    && a.permission === permission
    && (a.status ?? 'pending') === 'pending'
  );
}

export async function getTimedAction(id) {
  const data = await readDatabase();
  return data.timed_actions.find((a) => a.id === id) ?? null;
}

function isTimedActionDue(action, now) {
  if ((action.status ?? 'pending') !== 'pending') return false;
  if (action.next_retry_at) return action.next_retry_at <= now;
  return action.ends_at <= now;
}

export async function getDueTimedActions() {
  const data = await readDatabase();
  const now = Date.now();
  return data.timed_actions.filter((a) => isTimedActionDue(a, now));
}

export async function deleteTimedAction(id) {
  return mutateDatabase((data) => {
    data.timed_actions = data.timed_actions.filter((a) => a.id !== id);
  });
}

export async function completeTimedAction(id) {
  const maxTries = 3;
  for (let i = 0; i < maxTries; i++) {
    try {
      await deleteTimedAction(id);
      return true;
    } catch (err) {
      if (i === maxTries - 1) {
        console.error(`[database] Failed to remove completed timed action ${id}:`, err.message);
        return false;
      }
    }
  }
  return false;
}

export async function recordTimedActionRetry(id, { attemptCount, lastError, nextRetryAt, lastLoggedError }) {
  return mutateDatabase((data) => {
    const action = data.timed_actions.find((a) => a.id === id);
    if (!action) return;
    action.attempt_count = attemptCount;
    action.last_attempt_at = Date.now();
    action.last_error = lastError;
    action.next_retry_at = nextRetryAt;
    if (lastLoggedError !== undefined) {
      action.last_logged_error = lastLoggedError;
    }
  });
}

export async function markTimedActionFailed(id, { lastError, attemptCount }) {
  return mutateDatabase((data) => {
    const action = data.timed_actions.find((a) => a.id === id);
    if (!action) return;
    action.status = 'failed';
    action.attempt_count = attemptCount ?? action.attempt_count ?? 0;
    action.last_attempt_at = Date.now();
    action.last_error = lastError;
    action.next_retry_at = null;
  });
}

export async function getChannelRestoreDiagnostics(guildId = null) {
  const data = await readDatabase();
  const now = Date.now();
  const channelActions = data.timed_actions.filter((a) =>
    a.action === 'channel_unlock'
    && (!guildId || a.guild_id === guildId)
  );

  return {
    pending: channelActions
      .filter((a) => (a.status ?? 'pending') === 'pending')
      .map((a) => ({
        id: a.id,
        guild_id: a.guild_id,
        channel_id: a.channel_id,
        permission: a.permission,
        previous_state: a.previous_state,
        applied_state: a.applied_state,
        ends_at: a.ends_at,
        next_retry_at: a.next_retry_at ?? null,
        attempt_count: a.attempt_count ?? 0,
        last_error: a.last_error ?? null,
        due: isTimedActionDue(a, now),
      })),
    failed: channelActions
      .filter((a) => a.status === 'failed')
      .map((a) => ({
        id: a.id,
        guild_id: a.guild_id,
        channel_id: a.channel_id,
        permission: a.permission,
        previous_state: a.previous_state,
        attempt_count: a.attempt_count ?? 0,
        last_error: a.last_error ?? null,
        last_attempt_at: a.last_attempt_at ?? null,
      })),
  };
}

export async function isModuleDisabled(guildId, moduleName) {
  const data = await readDatabase();
  const settings = guildSettingsFromData(data, guildId);
  const disabled = parseDisabledModules(settings.disabled_modules);
  return disabled.includes(moduleName);
}

export async function isAutomodModuleEnabled(guildId) {
  return !(await isModuleDisabled(guildId, 'Automod'));
}

export async function toggleModule(guildId, moduleName) {
  return mutateDatabase((data) => {
    ensureGuildSettings(data, guildId);
    const settings = data.guild_settings[guildId];
    const disabled = parseDisabledModules(settings.disabled_modules);
    const index = disabled.indexOf(moduleName);
    if (index === -1) disabled.push(moduleName);
    else disabled.splice(index, 1);
    settings.disabled_modules = JSON.stringify(disabled);
    settings._automod_module_migrated = 1;
    return index === -1;
  });
}
