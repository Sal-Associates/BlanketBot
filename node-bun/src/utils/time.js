import ms from 'ms';

export function parseDuration(input) {
  if (!input) return null;
  const duration = ms(input);
  if (!duration || duration < 1000) return null;
  return duration;
}

export function formatDuration(msValue) {
  const seconds = Math.floor(msValue / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (days > 0) return `${days}d ${hours % 24}h`;
  if (hours > 0) return `${hours}h ${minutes % 60}m`;
  if (minutes > 0) return `${minutes}m ${seconds % 60}s`;
  return `${seconds}s`;
}

export function formatTimestamp(ts) {
  return `<t:${Math.floor(ts / 1000)}:R>`;
}

export function formatDate(ts) {
  return `<t:${Math.floor(ts / 1000)}:f>`;
}
