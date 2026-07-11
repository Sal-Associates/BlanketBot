import { isModerator, isAdmin } from '../utils/permissions.js';
import { error } from '../utils/helpers.js';

export async function checkMod(message) {
  if (!(await isModerator(message.member))) {
    return error('You need moderator permissions to use this command.');
  }
  return null;
}

export async function checkAdmin(message) {
  if (!(await isAdmin(message.member)) && !message.member.permissions.has('Administrator')) {
    return error('You need admin permissions to use this command.');
  }
  return null;
}
