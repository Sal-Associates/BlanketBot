import { resolveMember, basicEmbed, error } from '../../utils/helpers.js';
import { checkMod } from '../../utils/checks.js';
import { getCase, getCasesForUser, getRecentCases } from '../../database/db.js';
import { formatDate } from '../../utils/time.js';

function formatCaseExtra(extra = {}) {
  const lines = [];
  if (extra.source) lines.push(`**Source:** ${extra.source}`);
  if (extra.status) lines.push(`**Status:** ${extra.status}`);
  if (extra.warning_id) lines.push(`**Warning ID:** ${extra.warning_id}`);
  if (extra.queue_id) lines.push(`**Queue ID:** ${extra.queue_id}`);
  if (extra.timed_action_id) lines.push(`**Timed action ID:** ${extra.timed_action_id}`);
  if (extra.timed_action) lines.push(`**Timed action:** ${extra.timed_action}`);
  if (extra.ends_at) lines.push(`**Expires:** ${formatDate(extra.ends_at)}`);
  return lines;
}

export default {
  name: 'case',
  description: 'View moderation cases by number or user',
  category: 'Moderation',
  usage: '?case <number> or ?case list [user]',
  async execute(message, args, subcommand, subargs) {
    const denied = await checkMod(message);
    if (denied) return message.reply(denied);

    const action = subcommand?.toLowerCase();
    const rest = subargs || args.trim();

    if (action === 'list') {
      const target = resolveMember(message, rest.trim());
      const cases = target
        ? await getCasesForUser(message.guild.id, target.id)
        : await getRecentCases(message.guild.id);

      if (!cases.length) return message.reply(error('No cases found.'));

      const title = target ? `Cases: ${target.user.tag}` : 'Recent Cases';
      const lines = cases.map((c) =>
        `**#${c.case_number}** ${c.action} — ${c.reason} by <@${c.moderator_id}> (${formatDate(c.created_at)})`
      );
      return message.reply({ embeds: [basicEmbed(title, lines.join('\n'))] });
    }

    const caseNum = parseInt(action && /^\d+$/.test(action) ? action : rest.trim(), 10);
    if (!caseNum) return message.reply(error('Usage: `?case <number>` or `?case list [user]`'));

    const caseData = await getCase(message.guild.id, caseNum);
    if (!caseData) return message.reply(error(`Case #${caseNum} not found.`));

    const embed = basicEmbed(`Case #${caseData.case_number}`, [
      `**Action:** ${caseData.action}`,
      `**User:** <@${caseData.user_id}> (\`${caseData.user_id}\`)`,
      `**Moderator:** <@${caseData.moderator_id}>`,
      `**Reason:** ${caseData.reason || 'None'}`,
      `**Date:** ${formatDate(caseData.created_at)}`,
      ...formatCaseExtra(caseData.extra),
    ].join('\n'));

    return message.reply({ embeds: [embed] });
  },
};
