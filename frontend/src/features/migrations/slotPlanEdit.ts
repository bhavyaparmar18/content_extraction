/**
 * Reviewer edits of a slot plan, as pure functions: assign a source unit to a slot (a unit may feed several
 * slots), take it out again, change a slot's migration action, or mark a flagged slot reviewed.
 */
import type { MigrationAction, SectionSlotPlan, SlotMapping, SlotPlan, TemplateModel, TargetSlot } from './types';

interface Context {
  template: TemplateModel;
  /** Reading order of every source unit (``seq``): slots keep their units in source order. */
  seq: Map<string, number>;
  /** The action a newly filled slot gets: rewrite with a GWP, copy as written without one. */
  defaultAction: MigrationAction;
}

export function assignUnit(plan: SlotPlan, ctx: Context, targetId: string, slotId: string, unitId: string): SlotPlan {
  return updateSection(plan, targetId, (section) => {
    const existing = section.slot_mappings.find((m) => m.slot_id === slotId);
    const base = existing ?? emptyMapping(slotId);
    if (base.source_unit_ids.includes(unitId)) return section;
    const filled: SlotMapping = {
      ...base,
      source_unit_ids: ordered([...base.source_unit_ids, unitId], ctx.seq),
      status: 'mapped',
      migration_action: base.migration_action === 'none' ? actionFor(slot(ctx.template, slotId), ctx.defaultAction) : base.migration_action,
      requires_human_review: false,
      rule_ids: base.rule_ids?.length ? base.rule_ids : rulesFor(plan, ctx.template, slotId),
      note: base.status === 'mapped' ? base.note : undefined,
    };
    return {
      ...section,
      slot_mappings: existing
        ? section.slot_mappings.map((m) => (m.slot_id === slotId ? filled : m))
        : [...section.slot_mappings, filled],
      unplaced_unit_ids: section.unplaced_unit_ids.filter((u) => u !== unitId),
    };
  });
}

export function removeUnit(plan: SlotPlan, ctx: Context, targetId: string, slotId: string, unitId: string): SlotPlan {
  return updateSection(plan, targetId, (section) => {
    const slot_mappings = section.slot_mappings.map((m) => {
      if (m.slot_id !== slotId) return m;
      const source_unit_ids = m.source_unit_ids.filter((u) => u !== unitId);
      const below_unit_ids = (m.below_unit_ids ?? []).filter((u) => u !== unitId);
      if (source_unit_ids.length) return { ...m, source_unit_ids, below_unit_ids };
      const required = !!slot(ctx.template, slotId)?.required;
      return {
        ...m,
        source_unit_ids,
        below_unit_ids,
        status: required ? 'source_content_not_found' : 'not_applicable',
        migration_action: 'none',
        requires_human_review: required,
        note: required ? 'The reviewer removed every passage: the draft shows a gap' : 'The reviewer removed every passage: the slot is removed',
      } satisfies SlotMapping;
    });
    const stillUsed = slot_mappings.some((m) => m.source_unit_ids.includes(unitId));
    return {
      ...section,
      slot_mappings,
      unplaced_unit_ids: stillUsed || section.unplaced_unit_ids.includes(unitId) ? section.unplaced_unit_ids : ordered([...section.unplaced_unit_ids, unitId], ctx.seq),
    };
  });
}

export function setAction(plan: SlotPlan, targetId: string, slotId: string, action: MigrationAction): SlotPlan {
  return updateSection(plan, targetId, (section) => ({
    ...section,
    slot_mappings: section.slot_mappings.map((m) => (m.slot_id === slotId && m.status === 'mapped' ? { ...m, migration_action: action } : m)),
  }));
}

export function markSlotReviewed(plan: SlotPlan, targetId: string, slotId: string): SlotPlan {
  return updateSection(plan, targetId, (section) => ({
    ...section,
    slot_mappings: section.slot_mappings.map((m) =>
      m.slot_id === slotId && m.status !== 'source_content_not_found'
        ? { ...m, requires_human_review: false, status: m.status === 'needs_review' ? 'mapped' : m.status }
        : m,
    ),
  }));
}

export function slotPlanSignature(plan: SlotPlan): string {
  return JSON.stringify(
    plan.sections.map((s) => [
      s.target_section_id,
      s.unplaced_unit_ids,
      s.slot_mappings.map((m) => [m.slot_id, m.source_unit_ids, m.below_unit_ids ?? [], m.status, m.migration_action, !!m.requires_human_review]),
    ]),
  );
}

// ── Internals ─────────────────────────────────────────────────────────

function updateSection(plan: SlotPlan, targetId: string, change: (s: SectionSlotPlan) => SectionSlotPlan): SlotPlan {
  return { ...plan, sections: plan.sections.map((s) => (s.target_section_id === targetId ? change(s) : s)) };
}

function emptyMapping(slotId: string): SlotMapping {
  return { slot_id: slotId, source_unit_ids: [], migration_action: 'none', status: 'not_applicable', origin: 'human' };
}

function slot(template: TemplateModel, slotId: string): TargetSlot | undefined {
  for (const section of template.sections) {
    const found = section.slots.find((s) => s.slot_id === slotId);
    if (found) return found;
  }
  return undefined;
}

function actionFor(target: TargetSlot | undefined, fallback: MigrationAction): MigrationAction {
  if (target?.formatting_profile === 'table') return 'copy_verbatim';
  if (fallback !== 'copy_verbatim' && target?.content_type === 'ordered_procedure') return 'rewrite_as_ordered_procedure';
  return fallback;
}

/** The rules a newly filled slot gets: those of a filled slot with the same content type, else the preservation rules. */
function rulesFor(plan: SlotPlan, template: TemplateModel, slotId: string): string[] {
  const type = slot(template, slotId)?.content_type;
  const filled = plan.sections.flatMap((s) => s.slot_mappings).filter((m) => m.status === 'mapped' && m.rule_ids?.length);
  const same = filled.find((m) => slot(template, m.slot_id)?.content_type === type);
  if (same) return [...(same.rule_ids ?? [])];
  return [...new Set(filled.flatMap((m) => m.rule_ids ?? []).filter((r) => r.startsWith('PRES-')))];
}

function ordered(ids: string[], seq: Map<string, number>): string[] {
  return [...new Set(ids)].sort((a, b) => (seq.get(a) ?? 0) - (seq.get(b) ?? 0));
}
