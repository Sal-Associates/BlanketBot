import { EmbedBuilder } from 'discord.js';
import { getModQueueEntry, processModQueueDecision } from '../database/db.js';
import { sendModLog } from '../utils/modLog.js';
import { checkStrikeEscalation } from '../utils/strikes.js';
import { isModerator, getModerationDenied } from '../utils/permissions.js';
import { success, error } from '../utils/helpers.js';
import { isConfiguredGuild } from '../utils/guild.js';

function queueAlreadyHandled(result) {
  if (result.status === 'already_processed') {
    return error('This queue item was already reviewed.');
  }
  if (result.status === 'not_found') {
    return error('This queue item was not found.');
  }
  return null;
}

export async function handleInteraction(interaction) {
  if (!interaction.guild || !isConfiguredGuild(interaction.guild.id)) {
    if (interaction.isRepliable() && !interaction.replied && !interaction.deferred) {
      await interaction.reply({ ephemeral: true }).catch(() => {});
    }
    return;
  }

  if (!interaction.isButton()) return;
  if (!interaction.customId.startsWith('queue_approve_') && !interaction.customId.startsWith('queue_deny_')) return;

  if (!(await isModerator(interaction.member))) {
    return interaction.reply({ content: error('Only moderators can review queue items.'), ephemeral: true });
  }

  const isApprove = interaction.customId.startsWith('queue_approve_');
  const entryId = parseInt(interaction.customId.replace(/queue_(approve|deny)_/, ''), 10);

  let entry;
  try {
    entry = await getModQueueEntry(entryId);
  } catch (err) {
    console.error('[interaction] Database read failed:', err.message);
    return interaction.reply({ content: error('Could not load that queue item.'), ephemeral: true });
  }

  if (!entry) {
    return interaction.reply({ content: error('This queue item was not found.'), ephemeral: true });
  }

  const target = await interaction.guild.members.fetch(entry.author_id).catch(() => null);

  if (!isApprove && target) {
    const hierarchyDenied = getModerationDenied(interaction.guild, interaction.member, target);
    if (hierarchyDenied) {
      return interaction.reply({ content: hierarchyDenied, ephemeral: true });
    }
  }

  try {
    if (isApprove) {
      const result = await processModQueueDecision({
        entryId,
        moderatorId: interaction.user.id,
        decision: 'approve',
        caseAction: 'queue_approve',
        caseReason: `False positive: ${entry.reason}`,
      });

      const handled = queueAlreadyHandled(result);
      if (handled) return interaction.reply({ content: handled, ephemeral: true });

      await sendModLog(interaction.guild, {
        action: 'queue_approve',
        target: target ?? { id: entry.author_id, toString: () => `<@${entry.author_id}>` },
        moderator: interaction.user,
        reason: `Approved (false positive): ${entry.reason}`,
        caseNumber: result.caseNumber,
      });

      await interaction.message.edit({
        embeds: [
          EmbedBuilder.from(interaction.message.embeds[0])
            .setTitle('Approved — False Positive')
            .setColor(0x57f287)
            .setFooter({ text: `Reviewed by ${interaction.user.tag} · Case #${result.caseNumber}` }),
        ],
        components: [],
      });

      return interaction.reply({ content: success(`Approved — Case #${result.caseNumber} logged.`), ephemeral: true });
    }

    if (!target) {
      const result = await processModQueueDecision({
        entryId,
        moderatorId: interaction.user.id,
        decision: 'deny',
        caseAction: 'queue_deny',
        caseReason: `Automod violation: ${entry.reason} (user left)`,
      });

      const handled = queueAlreadyHandled(result);
      if (handled) return interaction.reply({ content: handled, ephemeral: true });

      await interaction.message.edit({ components: [] });
      return interaction.reply({ content: success('Denied — user has left the server.'), ephemeral: true });
    }

    const result = await processModQueueDecision({
      entryId,
      moderatorId: interaction.user.id,
      decision: 'deny',
      warnReason: `Automod: ${entry.reason}`,
      caseAction: 'queue_deny',
      caseReason: `Automod violation: ${entry.reason}`,
    });

    const handled = queueAlreadyHandled(result);
    if (handled) return interaction.reply({ content: handled, ephemeral: true });

    await sendModLog(interaction.guild, {
      action: 'queue_deny',
      target,
      moderator: interaction.user,
      reason: `Denied & warned: ${entry.reason}`,
      caseNumber: result.caseNumber,
    });

    const escalation = await checkStrikeEscalation(interaction.guild, target, interaction.user);

    await interaction.message.edit({
      embeds: [
        EmbedBuilder.from(interaction.message.embeds[0])
          .setTitle('Denied — User Warned')
          .setColor(0xed4245)
          .setFooter({ text: `Reviewed by ${interaction.user.tag} · Case #${result.caseNumber}` }),
      ],
      components: [],
    });

    let reply = success(`Denied — warned user. Case #${result.caseNumber}.`);
    if (escalation) reply += `\n${escalation}`;
    return interaction.reply({ content: reply, ephemeral: true });
  } catch (err) {
    console.error('[interaction] Database write failed:', err.message);
    return interaction.reply({ content: error('Could not save the queue review.'), ephemeral: true });
  }
}
