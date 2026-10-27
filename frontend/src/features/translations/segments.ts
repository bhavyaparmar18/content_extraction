import type { RenderReport, Segment, SegmentKind, Severity, ValidationIssue } from './types';
import { SEVERITY_ORDER } from '@/features/migrations/status';

export const TEMPLATE_SCOPE = 'template';
export const XREF_SCOPE = 'xrefs';

/** A segment's scope, as the server computes it (``Segment.scope``): its target section, ``xrefs`` or ``template``. */
export function scopeOf(segment: Segment): string {
  if (segment.kind === 'template_text') return TEMPLATE_SCOPE;
  if (segment.kind === 'xref') return XREF_SCOPE;
  return segment.locator.section_id ?? TEMPLATE_SCOPE;
}

/** The segments of each scope, in document order. */
export function groupByScope(segments: Segment[]): Map<string, Segment[]> {
  const out = new Map<string, Segment[]>();
  segments.forEach((s) => {
    const scope = scopeOf(s);
    out.set(scope, [...(out.get(scope) ?? []), s]);
  });
  return out;
}

export interface SectionEntry {
  scope: string;
  number?: string;
  heading: string;
}

/**
 * The review's sections: the template's sections in their order (only those with segments), then any other
 * section scope, then the template text and the cross-references.
 */
export function sectionOrder(
  scopes: string[],
  templateSections: { section_id: string; number?: string | null; heading: string }[] = [],
): SectionEntry[] {
  const present = new Set(scopes);
  const out: SectionEntry[] = templateSections
    .filter((s) => present.has(s.section_id))
    .map((s) => ({ scope: s.section_id, number: s.number ?? undefined, heading: s.heading }));
  const known = new Set(out.map((s) => s.scope));
  scopes
    .filter((s) => !known.has(s) && s !== TEMPLATE_SCOPE && s !== XREF_SCOPE)
    .forEach((s) => out.push({ scope: s, heading: s }));
  if (present.has(TEMPLATE_SCOPE)) out.push({ scope: TEMPLATE_SCOPE, heading: 'Headings and labels' });
  if (present.has(XREF_SCOPE)) out.push({ scope: XREF_SCOPE, heading: 'Cross-references' });
  return out;
}

const KIND_LABEL: Record<SegmentKind, string> = {
  claim: 'Text',
  table_cell: 'Table cell',
  table_header: 'Table header',
  xref: 'Reference',
  template_text: 'Heading or label',
};

/** "Table r3 c2", "Table header c1", "Text", … */
export function locatorLabel(segment: Segment): string {
  const { row, col, paragraph } = segment.locator;
  if (segment.kind === 'table_cell' && row !== undefined && col !== undefined) {
    return `Table r${row + 1} c${col + 1}${paragraph ? ` ¶${paragraph + 1}` : ''}`;
  }
  if (segment.kind === 'table_header' && col !== undefined) return `Table header c${col + 1}`;
  if (segment.kind === 'claim' && segment.source_text.includes(' | ')) return 'Table row';
  return KIND_LABEL[segment.kind];
}

/** Each segment's issues (an issue may name several segments). */
export function issuesBySegment(issues: ValidationIssue[]): Map<string, ValidationIssue[]> {
  const out = new Map<string, ValidationIssue[]>();
  issues.forEach((issue) => (issue.segment_ids ?? []).forEach((id) => out.set(id, [...(out.get(id) ?? []), issue])));
  return out;
}

/** The most severe of some issues (gate issues count as critical), or undefined. */
export function worstSeverity(issues: ValidationIssue[]): Severity | undefined {
  let worst: number | undefined;
  issues.forEach((i) => {
    const rank = i.gate ? 0 : SEVERITY_ORDER.indexOf(i.severity);
    if (worst === undefined || rank < worst) worst = rank;
  });
  return worst === undefined ? undefined : SEVERITY_ORDER[worst];
}

/** The other segments a "same English" edit also changes: same text, not edited by a person yet. */
export function sameTextSegments(segment: Segment, all: Segment[]): Segment[] {
  return all.filter((s) => s.segment_id !== segment.segment_id && s.source_text === segment.source_text && s.origin !== 'human');
}

/** The segments the latest render showed in English (its warnings name them: "SEG-0012: …; shown in English"). */
export function keptInEnglish(report?: RenderReport | null): Set<string> {
  const out = new Set<string>();
  report?.warnings.forEach((w) => {
    const match = w.match(/^(SEG-\d+): .*shown in English$/);
    if (match) out.add(match[1]);
  });
  return out;
}

export type SegmentFilter = 'all' | 'issues' | 'edited' | 'english' | 'copied';

export function filterSegments(
  segments: Segment[],
  filter: SegmentFilter,
  context: { open: Map<string, ValidationIssue[]>; english: Set<string> },
  search = '',
): Segment[] {
  const needle = search.trim().toLocaleLowerCase();
  return segments.filter((s) => {
    const keep =
      filter === 'all' ||
      (filter === 'issues' && !!context.open.get(s.segment_id)?.length) ||
      (filter === 'edited' && s.origin === 'human') ||
      (filter === 'english' && context.english.has(s.segment_id)) ||
      (filter === 'copied' && s.origin === 'copied');
    return keep && (!needle || `${s.source_text}\u0000${s.target_text ?? ''}`.toLocaleLowerCase().includes(needle));
  });
}
