const VALID_MODES = new Set(['contains', 'exact']);

export function normalizeMatchMode(mode) {
  const normalized = String(mode ?? '').toLowerCase();
  if (normalized === 'exact') return 'exact';
  if (normalized === 'contains') return 'contains';
  return null;
}

export function normalizeBannedValue(value) {
  if (value == null) return '';
  return String(value).trim().toLowerCase();
}

export function matchBannedWordEntry(content, entry) {
  if (!entry || typeof content !== 'string') return null;

  const value = normalizeBannedValue(entry.value ?? entry.word);
  if (!value) {
    console.warn('[bannedWords] Skipping malformed entry without value:', entry.id ?? '(no id)');
    return null;
  }

  const matchMode = entry.match_mode != null
    ? normalizeMatchMode(entry.match_mode)
    : (entry.exact === 1 || entry.exact === true ? 'exact' : 'contains');

  if (!matchMode) {
    console.warn('[bannedWords] Skipping malformed entry with invalid mode:', entry.id ?? '(no id)');
    return null;
  }

  if (matchMode === 'exact') {
    const regex = new RegExp(`\\b${value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`, 'i');
    if (regex.test(content)) {
      return { id: entry.id, value, match_mode: matchMode, source: 'banned_word' };
    }
    return null;
  }

  if (content.toLowerCase().includes(value)) {
    return { id: entry.id, value, match_mode: matchMode, source: 'banned_word' };
  }

  return null;
}

/** First stored entry wins when multiple match (preserves legacy iteration order). */
export function findBannedWordMatch(content, entries) {
  if (!Array.isArray(entries)) return null;
  for (const entry of entries) {
    const match = matchBannedWordEntry(content, entry);
    if (match) return match;
  }
  return null;
}

export function formatBannedWordReason(match) {
  if (!match) return 'Banned word';
  const label = match.match_mode === 'exact' ? 'exact' : 'contains';
  return `Banned word (${label}): ${match.value}`;
}

export function isValidMatchMode(mode) {
  return VALID_MODES.has(normalizeMatchMode(mode));
}
