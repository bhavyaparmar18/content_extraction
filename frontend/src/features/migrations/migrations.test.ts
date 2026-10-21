import { describe, expect, it } from 'vitest';
import { diffWords } from '@/lib/diff';
import { findBlocks, needleOf, normalizeText } from './docxHighlight';
import { movePlacement, markReviewed, placementsAt, planSignature, unplacedSections } from './sectionPlanEdit';
import { assignUnit, removeUnit } from './slotPlanEdit';
import { defaultStep, isWorking, permissions, stepStates } from './status';
import type { ArtifactKind, MigrationJob, SectionPlan, SlotPlan, SourceDocument, TemplateModel } from './types';

// ── Fixtures ──────────────────────────────────────────────────────────

const unit = (section: string, n: number, text = `${section} unit ${n}`) => ({
  unit_id: `${section}-U00${n}`,
  content_hash: `${section}${n}`,
  section_id: section,
  seq: Number(section.replace(/\D/g, '')) * 10 + n,
  unit_type: 'paragraph' as const,
  text,
});

const source: SourceDocument = {
  schema_version: 'v2.0',
  document_id: 'SOP-1',
  source_file: 'sop.docx',
  file_type: 'docx',
  language: 'en',
  sections: ['SRC-1', 'SRC-2', 'SRC-3'].map((id, i) => ({
    section_id: id,
    number: String(i + 1),
    heading: `Heading ${i + 1}`,
    level: 1,
    section_order: i,
    units: [unit(id, 1), unit(id, 2)],
  })),
};

const template: TemplateModel = {
  schema_version: 'v2.0',
  template_id: 'TPL',
  template_version: 1,
  source_file: 'tpl.docx',
  callout_palette: [],
  readiness: 'ready',
  sections: [
    { section_id: 'TGT-1', heading: 'Purpose', level: 1, display_order: 0, required: true, slots: [
      { slot_id: 'TGT-1-WHAT', section_id: 'TGT-1', key: 'what', instruction: 'What', content_type: 'purpose', display_order: 0, required: true },
    ] },
    { section_id: 'TGT-2', heading: 'Scope', level: 1, display_order: 1, slots: [
      { slot_id: 'TGT-2-ROLES', section_id: 'TGT-2', key: 'roles', instruction: 'Roles', content_type: 'scope', display_order: 0 },
      { slot_id: 'TGT-2-UNITS', section_id: 'TGT-2', key: 'units', instruction: 'Units', content_type: 'scope', display_order: 1, required: true },
    ] },
  ],
};

const sectionPlan: SectionPlan = {
  job_id: 'J',
  version: 1,
  origin: 'rule',
  mappings: [
    { target_section_id: 'TGT-1', source_section_ids: ['SRC-1'], unit_ids: [], mapping_type: 'one_to_one', status: 'mapped', origin: 'rule' },
    { target_section_id: 'TGT-2', source_section_ids: ['SRC-2'], unit_ids: [], mapping_type: 'one_to_one', status: 'needs_review', origin: 'rule' },
  ],
};

function job(status: MigrationJob['status'], kinds: ArtifactKind[], running = false): MigrationJob {
  return {
    job_id: 'J', sop_record_id: 1, template_id: 'TPL', template_version: 1, mode: 'review', status, sections: [], running,
    artifacts: kinds.map((kind) => ({ kind, version: 1, path: '', sha256: '' })),
  };
}

// ── Tests ─────────────────────────────────────────────────────────────

describe('diffWords', () => {
  it('marks removed and added words and keeps the shared ones', () => {
    const parts = diffWords('The owner must close it within 5 days.', 'The owner must close it within 10 days.');
    expect(parts.filter((p) => p.type === 'removed').map((p) => p.text.trim())).toEqual(['5']);
    expect(parts.filter((p) => p.type === 'added').map((p) => p.text.trim())).toEqual(['10']);
    expect(parts.map((p) => (p.type === 'removed' ? '' : p.text)).join('')).toBe('The owner must close it within 10 days.');
  });

  it('returns one same part for identical text and handles empty sides', () => {
    expect(diffWords('a b', 'a b')).toEqual([{ type: 'same', text: 'a b' }]);
    expect(diffWords('', 'new')).toEqual([{ type: 'added', text: 'new' }]);
  });
});

describe('docx highlight matching', () => {
  it('normalizes quotes, punctuation and spacing', () => {
    expect(normalizeText('  “GBS”  Solution:\tthe  BI’s ')).toBe('gbs solution the bi s');
  });

  it('finds the paragraph that holds a passage, and a short cell inside a longer row', () => {
    const blocks = ['1. Introduction', 'The Process Owner submits the deviation within five business days.', 'Minor30 calendar days'];
    expect(findBlocks(blocks, [needleOf('The Process Owner submits the deviation within five business days.')])).toEqual([1]);
    expect(findBlocks(blocks, [needleOf('30 calendar days')])).toEqual([2]); // a row's text runs its cells together
    expect(findBlocks(blocks, [needleOf('Something the document does not say')])).toEqual([]);
  });

  it('cuts long passages to a specific prefix', () => {
    const long = 'word '.repeat(60);
    expect(needleOf(long).length).toBeLessThanOrEqual(80);
  });
});

describe('job status', () => {
  it('polls only while the pipeline works', () => {
    expect(isWorking(job('DRAFTING', []))).toBe(true);
    expect(isWorking(job('SECTION_PLAN_REVIEW_PENDING', ['section_plan']))).toBe(false);
    expect(isWorking(job('SECTION_PLAN_REVIEW_PENDING', ['section_plan'], true))).toBe(true);
    expect(isWorking(job('COMPLETED', []))).toBe(false);
  });

  it('opens the step that waits for the reviewer and locks steps without artifacts', () => {
    const j = job('SLOT_PLAN_REVIEW_PENDING', ['section_plan', 'slot_plan']);
    expect(stepStates(j)).toEqual({ sections: 'done', slots: 'current', draft: 'locked', final: 'locked' });
    expect(defaultStep(j)).toBe('slots');
    expect(defaultStep(job('COMPLETED', ['section_plan', 'slot_plan', 'section_draft', 'docx']))).toBe('final');
    expect(stepStates(job('DRAFTING', ['section_plan', 'slot_plan'])).draft).toBe('working');
  });

  it('allows edits only where the server does', () => {
    expect(permissions(job('SECTION_PLAN_REVIEW_PENDING', [])).editSectionPlan).toBe(true);
    expect(permissions(job('SECTION_PLAN_REVIEW_PENDING', [], true)).editSectionPlan).toBe(false);
    expect(permissions(job('HUMAN_REVIEW_REQUIRED', [])).editDrafts).toBe(true);
    expect(permissions(job('COMPLETED', [])).editDrafts).toBe(false);
    expect(permissions(job('MANUALLY_EDITED', [])).recheck).toBe(true);
    expect(permissions(job('COMPLETED_WITH_WARNINGS', [])).export).toBe(true);
  });
});

describe('section plan edits', () => {
  it('moves a section between template sections and keeps types and statuses consistent', () => {
    const moved = movePlacement(sectionPlan, template, source, { sectionId: 'SRC-2' }, { kind: 'target', id: 'TGT-2' }, { kind: 'target', id: 'TGT-1' });
    const tgt1 = moved.mappings.find((m) => m.target_section_id === 'TGT-1')!;
    const tgt2 = moved.mappings.find((m) => m.target_section_id === 'TGT-2')!;
    expect(tgt1.source_section_ids).toEqual(['SRC-1', 'SRC-2']);
    expect(tgt1.mapping_type).toBe('merge');
    expect(tgt2).toMatchObject({ source_section_ids: [], mapping_type: 'unresolved', status: 'not_applicable' });
    expect(planSignature(moved)).not.toBe(planSignature(sectionPlan));
  });

  it('places an unplaced section, omits one with a justification, and lists both', () => {
    expect(unplacedSections(sectionPlan, source)).toEqual(['SRC-3']);
    const placed = movePlacement(sectionPlan, template, source, { sectionId: 'SRC-3' }, { kind: 'unplaced' }, { kind: 'target', id: 'TGT-2' });
    expect(unplacedSections(placed, source)).toEqual([]);
    const omitted = movePlacement(placed, template, source, { sectionId: 'SRC-1' }, { kind: 'target', id: 'TGT-1' }, { kind: 'omitted' }, 'Revision history');
    expect(placementsAt(omitted, { kind: 'omitted' }, source)).toEqual([{ sectionId: 'SRC-1' }]);
    expect(omitted.mappings.find((m) => m.mapping_type === 'omit')).toMatchObject({ justification: 'Revision history', status: 'not_applicable' });
    // TGT-1 is required: emptied, it reports that its content was not found
    expect(omitted.mappings.find((m) => m.target_section_id === 'TGT-1')).toMatchObject({ status: 'source_content_not_found' });
  });

  it('moves a split part with its units only', () => {
    const split: SectionPlan = {
      ...sectionPlan,
      mappings: [
        { target_section_id: 'TGT-1', source_section_ids: ['SRC-1'], unit_ids: ['SRC-1-U001'], mapping_type: 'split', status: 'mapped' },
        { target_section_id: 'TGT-2', source_section_ids: ['SRC-1', 'SRC-2'], unit_ids: ['SRC-1-U002', 'SRC-2-U001', 'SRC-2-U002'], mapping_type: 'split', status: 'mapped' },
      ],
    };
    const part = placementsAt(split, { kind: 'target', id: 'TGT-2' }, source).find((p) => p.sectionId === 'SRC-1')!;
    expect(part.unitIds).toEqual(['SRC-1-U002']);
    const moved = movePlacement(split, template, source, part, { kind: 'target', id: 'TGT-2' }, { kind: 'target', id: 'TGT-1' });
    expect(moved.mappings.find((m) => m.target_section_id === 'TGT-1')!.unit_ids).toEqual(['SRC-1-U001', 'SRC-1-U002']);
    expect(moved.mappings.find((m) => m.target_section_id === 'TGT-2')).toMatchObject({ source_section_ids: ['SRC-2'], unit_ids: ['SRC-2-U001', 'SRC-2-U002'] });
  });

  it('marks a flagged mapping reviewed', () => {
    expect(markReviewed(sectionPlan, 'TGT-2').mappings[1].status).toBe('mapped');
  });
});

describe('slot plan edits', () => {
  const plan: SlotPlan = {
    job_id: 'J',
    version: 1,
    origin: 'rule',
    sections: [{
      target_section_id: 'TGT-2',
      source_section_ids: ['SRC-2'],
      unplaced_unit_ids: ['SRC-2-U002'],
      slot_mappings: [
        { slot_id: 'TGT-2-ROLES', source_unit_ids: ['SRC-2-U001'], migration_action: 'copy_verbatim', status: 'mapped', rule_ids: ['PRES-001'] },
      ],
    }],
  };
  const ctx = { template, seq: new Map(source.sections.flatMap((s) => s.units.map((u) => [u.unit_id, u.seq]))), defaultAction: 'copy_verbatim' as const };

  it('assigns an unplaced passage to a new slot with the preservation rules', () => {
    const next = assignUnit(plan, ctx, 'TGT-2', 'TGT-2-UNITS', 'SRC-2-U002');
    const section = next.sections[0];
    expect(section.unplaced_unit_ids).toEqual([]);
    expect(section.slot_mappings.find((m) => m.slot_id === 'TGT-2-UNITS')).toMatchObject({
      source_unit_ids: ['SRC-2-U002'], status: 'mapped', migration_action: 'copy_verbatim', rule_ids: ['PRES-001'],
    });
  });

  it('lets one passage feed two slots, and taking the last one out leaves a gap on a required slot', () => {
    const both = assignUnit(plan, ctx, 'TGT-2', 'TGT-2-UNITS', 'SRC-2-U001');
    expect(both.sections[0].slot_mappings.filter((m) => m.source_unit_ids.includes('SRC-2-U001'))).toHaveLength(2);
    const removed = removeUnit(both, ctx, 'TGT-2', 'TGT-2-UNITS', 'SRC-2-U001');
    expect(removed.sections[0].slot_mappings.find((m) => m.slot_id === 'TGT-2-UNITS')).toMatchObject({
      status: 'source_content_not_found', migration_action: 'none', requires_human_review: true,
    });
    expect(removed.sections[0].unplaced_unit_ids).toEqual(['SRC-2-U002']); // still used by ROLES: not unplaced
    const empty = removeUnit(plan, ctx, 'TGT-2', 'TGT-2-ROLES', 'SRC-2-U001');
    expect(empty.sections[0].slot_mappings[0].status).toBe('not_applicable'); // optional slot
    expect(empty.sections[0].unplaced_unit_ids).toEqual(['SRC-2-U001', 'SRC-2-U002']);
  });
});
