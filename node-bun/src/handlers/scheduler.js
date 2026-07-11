import { processDueTimedActions } from './timedActions.js';

const POLL_INTERVAL_MS = 15000;

export function startScheduler(client) {
  processDueTimedActions(client);
  setInterval(() => processDueTimedActions(client), POLL_INTERVAL_MS);
}
