import { useAuthStore } from '@/lib/authStore';
import { SEVERITY_ORDER } from './status';
import type { QualityReport, SourceUnit, ValidationIssue } from './types';

export const openIssues = (report?: QualityReport | null) => (report?.issues ?? []).filter((i) => !i.resolved);
export const blockingIssues = (report?: QualityReport | null) => openIssues(report).filter((i) => i.gate);

/** Gate issues first, then by severity. */
export function sortIssues(issues: ValidationIssue[]): ValidationIssue[] {
  return [...issues].sort(
    (a, b) =>
      Number(!!b.gate) - Number(!!a.gate) ||
      SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity) ||
      a.issue_id.localeCompare(b.issue_id),
  );
}

/** A source unit as one line of text (table rows as their cells, figures by their caption). */
export function unitText(unit: SourceUnit): string {
  if (unit.unit_type === 'figure') return unit.text ? `Figure: ${unit.text}` : 'Figure';
  if (unit.table_ref?.cells?.length) return unit.table_ref.cells.map((c) => c.text).join(' | ');
  return unit.text;
}

/** A readable actor: "You" for the signed-in reviewer, "System" for the pipeline, else a short user ID. */
export function actorName(actor?: string | null): string {
  if (!actor || actor === 'system') return 'System';
  if (actor === useAuthStore.getState().user?.userId) return 'You';
  return /^[0-9a-f-]{20,}$/i.test(actor) ? `User ${actor.slice(0, 8)}` : actor;
}

/** A resolution note as saved ("<actor>: <note>"), split into who and what. */
export function splitNote(note?: string): { actor?: string; text: string } {
  const match = note?.match(/^([\w-]{6,}): ([\s\S]*)$/);
  return match ? { actor: actorName(match[1]), text: match[2] } : { text: note ?? '' };
}
