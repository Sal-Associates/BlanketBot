import { getModerationDenied } from '../../utils/permissions.js';
import { resolveMember, success, error, basicEmbed } from '../../utils/helpers.js';
import { checkMod } from '../../utils/checks.js';
import { sendModLog } from '../../utils/modLog.js';
import { createWarningWithCase, getWarnings, deleteWarning, clearWarnings } from '../../database/db.js';
import { checkStrikeEscalation } from '../../utils/strikes.js';
import { formatDate } from '../../utils/time.js';

export default {
  name: 'warn',
  description: 'Warning system: add, list, del, clear',
  category: 'Moderation',
  usage: '?warn add|list|del|clear [args]',
  async execute(message, args, subcommand, subargs) {
    const denied = await checkMod(message);
    if (denied) return message.reply(denied);

    const action = subcommand?.toLowerCase() || 'add';
    const rest = subargs || args.trim();

    switch (action) {
      case 'add': {
        const parts = rest.split(/\s+/);
        const target = resolveMember(message, parts[0]);
        if (!target) return message.reply(error('That user is not currently a member of this server.'));
        const hierarchyDenied = getModerationDenied(message.guild, message.member, target);
        if (hierarchyDenied) return message.reply(hierarchyDenied);
        const reason = parts.slice(1).join(' ') || 'No reason provided';

        let records;
        try {
          records = await createWarningWithCase({
            guildId: message.guild.id,
            userId: target.id,
            moderatorId: message.author.id,
            reason,
            source: 'warn_command',
          });
        } catch (err) {
          console.error('[warn] Database write failed:', err.message);
          return message.reply(error('Could not save that warning.'));
        }

        const { warningId, caseNumber } = records;
        const notified = await sendModLog(message.guild, {
          action: 'warn',
          target,
          moderator: message.author,
          reason,
          caseNumber,
        });
        if (!notified) {
          console.error(`[warn] Mod-log channel notification failed for case #${caseNumber}`);
        }

        let reply = success(`Warned **${target.user.tag}** — Warning #${warningId}, Case #${caseNumber}. Reason: ${reason}`);
        const escalation = await checkStrikeEscalation(message.guild, target, message.author);
        if (escalation) reply += `\n${escalation}`;
        return message.reply(reply);
      }
      case 'list': {
        const target = resolveMember(message, rest.trim()) ?? message.member;
        const warnings = await getWarnings(message.guild.id, target.id);
        if (!warnings.length) return message.reply(error(`**${target.user.tag}** has no warnings.`));
        const lines = warnings.map((w) => `**#${w.id}** — ${w.reason || 'No reason'} (${formatDate(w.created_at)})`);
        return message.reply({ embeds: [basicEmbed(`Warnings: ${target.user.tag}`, lines.join('\n'), 0xfee75c)] });
      }
      case 'del': {
        const id = parseInt(rest.trim().replace('#', ''), 10);
        if (!id) return message.reply(error('Usage: `?warn del <warning ID>`'));
        const result = await deleteWarning(id);
        if (!result.changes) return message.reply(error('Warning not found.'));
        return message.reply(success(`Deleted warning #${id}.`));
      }
      case 'clear': {
        const target = resolveMember(message, rest.trim());
        if (!target) return message.reply(error('Usage: `?warn clear <user>`'));
        await clearWarnings(message.guild.id, target.id);
        return message.reply(success(`Cleared all warnings for **${target.user.tag}**.`));
      }
      default:
        return message.reply(error('Usage: `?warn add|list|del|clear`'));
    }
  },
};
