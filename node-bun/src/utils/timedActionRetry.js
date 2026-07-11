export const MAX_CHANNEL_UNLOCK_ATTEMPTS = 10;
export const SCHEDULER_POLL_INTERVAL_MS = 15000;
export const RETRY_DELAYS_MS = [30_000, 60_000, 120_000, 300_000];

export function getRetryDelayMs(attemptCount) {
  const index = Math.min(Math.max(attemptCount - 1, 0), RETRY_DELAYS_MS.length - 1);
  return Math.max(RETRY_DELAYS_MS[index], SCHEDULER_POLL_INTERVAL_MS);
}

export function sanitizeTimedActionError(err) {
  if (!err) return 'unknown_error';
  if (typeof err === 'string') return err.slice(0, 200);
  const code = err.code ?? err.status;
  const message = (err.message ?? 'unknown_error').slice(0, 200);
  return code ? `${code}: ${message}` : message;
}
