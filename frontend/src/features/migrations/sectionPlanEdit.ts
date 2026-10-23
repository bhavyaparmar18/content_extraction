/**
 * Reviewer edits of a section plan, as pure functions: move a source section (or the part of it a split
 * mapping holds) from one place to another, omit it with a justification, or mark a mapping reviewed.
 * The server validates the result and marks every changed mapping ``origin: human``.
 */
import type { SectionMapping, SectionPlan, SourceDocument, TemplateModel } from './types';

/** Where a source section sits: a template section, the omitted list, or nowhere yet. */
export type Place = { kind: 'target'; id: string } | { kind: 'omitted' } | { kind: 'unplaced' };

/** One source section (or a split part of it) placed somewhere. */
export interface Placement {
  sectionId: string;
  /** Set for split mappings: the units of the section that go here. */
  unitIds?: string[];
}

export const REVIEWER_REASON = 'Changed by the reviewer';

export function unplacedSections(plan: SectionPlan, source: SourceDocument): string[] {
  const placed = new Set(plan.mappings.flatMap((m) => m.source_section_ids));
  return source.sections.map((s) => s.section_id).filter((id) => !placed.has(id));
}

export function placementsAt(plan: SectionPlan, place: Place, source: SourceDocument): Placement[] {
  if (place.kind === 'unplaced') return unplacedSections(plan, source).map((sectionId) => ({ sectionId }));
  const unitsOf = unitsBySection(source);
  return plan.mappings.filter((m) => matches(m, place)).flatMap((m) =>
    m.source_section_ids.map((sectionId) => {
      const units = m.mapping_type === 'split' ? m.unit_ids.filter((u) => unitsOf.get(sectionId)?.has(u)) : [];
      return units.length ? { sectionId, unitIds: units } : { sectionId };
    }),
  );
}

/** Move one placement. ``justification`` is required when moving to ``omitted``. */
export function movePlacement(
  plan: SectionPlan,
  template: TemplateModel,
  source: SourceDocument,
  item: Placement,
  from: Place,
  to: Place,
  justification?: string,
): SectionPlan {
  if (samePlace(from, to)) return plan;
  const sectionUnits = unitsBySection(source).get(item.sectionId) ?? new Set<string>();
  let mappings = plan.mappings
    .map((m) => (matches(m, from) && m.source_section_ids.includes(item.sectionId) ? tidy(removeFrom(m, item, sectionUnits), template) : m))
    .filter((m) => m.mapping_type !== 'omit' || m.source_section_ids.length > 0);

  if (to.kind === 'omitted') {
    mappings.push({
      source_section_ids: [item.sectionId],
      unit_ids: [],
      mapping_type: 'omit',
      status: 'not_applicable',
      reason: REVIEWER_REASON,
      justification: justification?.trim() || REVIEWER_REASON,
      origin: 'human',
    });
  } else if (to.kind === 'target') {
    mappings = addTo(mappings, to.id, item, template);
  }
  return { ...plan, mappings: sortMappings(mappings, template) };
}

/** Accept a mapping the planner flagged (``needs_review`` → ``mapped``). */
export function markReviewed(plan: SectionPlan, targetId: string): SectionPlan {
  return {
    ...plan,
    mappings: plan.mappings.map((m) =>
      m.target_section_id === targetId && m.status === 'needs_review' ? { ...m, status: 'mapped', reason: m.reason || REVIEWER_REASON } : m,
    ),
  };
}

export function setJustification(plan: SectionPlan, sectionId: string, justification: string): SectionPlan {
  return {
    ...plan,
    mappings: plan.mappings.map((m) =>
      m.mapping_type === 'omit' && m.source_section_ids.includes(sectionId) ? { ...m, justification } : m,
    ),
  };
}

/** Comparable form of a plan's mappings (to tell whether the reviewer changed anything). */
export function planSignature(plan: SectionPlan): string {
  return JSON.stringify(
    plan.mappings.map((m) => [m.target_section_id ?? null, m.source_section_ids, m.unit_ids, m.mapping_type, m.status, m.justification ?? null]),
  );
}

// ── Internals ─────────────────────────────────────────────────────────

function matches(m: SectionMapping, place: Place): boolean {
  if (place.kind === 'target') return m.target_section_id === place.id;
  if (place.kind === 'omitted') return m.mapping_type === 'omit';
  return false;
}

function samePlace(a: Place, b: Place): boolean {
  return a.kind === b.kind && (a.kind !== 'target' || a.id === (b as { id: string }).id);
}

function removeFrom(m: SectionMapping, item: Placement, sectionUnits: Set<string>): SectionMapping {
  if (m.mapping_type === 'split' && item.unitIds?.length) {
    const moved = new Set(item.unitIds);
    const unit_ids = m.unit_ids.filter((u) => !moved.has(u));
    const stillHere = unit_ids.some((u) => sectionUnits.has(u));
    return {
      ...m,
      unit_ids,
      source_section_ids: stillHere ? m.source_section_ids : m.source_section_ids.filter((s) => s !== item.sectionId),
      reason: REVIEWER_REASON,
    };
  }
  return {
    ...m,
    source_section_ids: m.source_section_ids.filter((s) => s !== item.sectionId),
    unit_ids: m.unit_ids.filter((u) => !sectionUnits.has(u)),
    reason: REVIEWER_REASON,
  };
}

function addTo(mappings: SectionMapping[], targetId: string, item: Placement, template: TemplateModel): SectionMapping[] {
  if (item.unitIds?.length) {
    // A split part keeps its units: it becomes (or joins) this target's split mapping.
    const split = mappings.findIndex((m) => m.target_section_id === targetId && m.mapping_type === 'split');
    if (split >= 0) {
      const m = mappings[split];
      const updated: SectionMapping = {
        ...m,
        source_section_ids: m.source_section_ids.includes(item.sectionId) ? m.source_section_ids : [...m.source_section_ids, item.sectionId],
        unit_ids: [...m.unit_ids, ...item.unitIds.filter((u) => !m.unit_ids.includes(u))],
        status: 'mapped',
        reason: REVIEWER_REASON,
      };
      return mappings.map((x, i) => (i === split ? updated : x));
    }
    const rest = mappings.filter((m) => !(m.target_section_id === targetId && m.source_section_ids.length === 0));
    return [...rest, mapping(targetId, [item.sectionId], 'split', item.unitIds)];
  }

  const index = mappings.findIndex((m) => m.target_section_id === targetId && m.mapping_type !== 'split');
  if (index < 0) return [...mappings, mapping(targetId, [item.sectionId], 'one_to_one')];
  const m = mappings[index];
  const sources = m.source_section_ids.includes(item.sectionId) ? m.source_section_ids : [...m.source_section_ids, item.sectionId];
  const updated = tidy({ ...m, source_section_ids: sources, status: 'mapped', reason: REVIEWER_REASON }, template);
  return mappings.map((x, i) => (i === index ? updated : x));
}

function mapping(targetId: string, sources: string[], type: SectionMapping['mapping_type'], unitIds: string[] = []): SectionMapping {
  return {
    target_section_id: targetId,
    source_section_ids: sources,
    unit_ids: unitIds,
    mapping_type: type,
    ordering_rule: 'preserve_source_order',
    status: 'mapped',
    reason: REVIEWER_REASON,
    origin: 'human',
  };
}

/** Keep type and status consistent with the sources a mapping has left. */
function tidy(m: SectionMapping, template: TemplateModel): SectionMapping {
  if (m.mapping_type === 'omit' || !m.target_section_id) return m;
  const count = m.source_section_ids.length;
  if (count === 0) {
    const required = template.sections.find((s) => s.section_id === m.target_section_id)?.required;
    return { ...m, unit_ids: [], mapping_type: 'unresolved', status: required ? 'source_content_not_found' : 'not_applicable', confidence: undefined };
  }
  if (m.mapping_type === 'split') return m.unit_ids.length ? m : { ...m, mapping_type: count > 1 ? 'merge' : 'one_to_one' };
  const type = count > 1 ? 'merge' : m.mapping_type === 'merge' || m.mapping_type === 'unresolved' ? 'one_to_one' : m.mapping_type;
  const status = m.status === 'source_content_not_found' || m.status === 'not_applicable' ? 'mapped' : m.status;
  return { ...m, mapping_type: type, status };
}

/** Template order, omitted mappings last; empty mappings of the same target collapse into one. */
function sortMappings(mappings: SectionMapping[], template: TemplateModel): SectionMapping[] {
  const order = new Map(template.sections.map((s) => [s.section_id, s.display_order]));
  const kept = mappings.filter(
    (m, i) =>
      m.source_section_ids.length > 0 ||
      !m.target_section_id ||
      !mappings.some((o, j) => j !== i && o.target_section_id === m.target_section_id && (o.source_section_ids.length > 0 || j < i)),
  );
  return [...kept].sort((a, b) => rank(a, order) - rank(b, order));
}

const rank = (m: SectionMapping, order: Map<string, number>) =>
  m.target_section_id ? (order.get(m.target_section_id) ?? 1e6) : 2e6;

function unitsBySection(source: SourceDocument): Map<string, Set<string>> {
  return new Map(source.sections.map((s) => [s.section_id, new Set(s.units.map((u) => u.unit_id))]));
}
