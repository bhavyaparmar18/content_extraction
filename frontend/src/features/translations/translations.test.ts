import { describe, expect, it } from 'vitest';
import { TRANSLATION_LABELS } from './activity';
import { fromEditorDoc, toEditorDoc } from './editorDoc';
import { emptyRow, rowProblems, rowsChanged, toEntries, toRows } from './glossaryEdit';
import { cleanTyped, formattedRuns, markerKey, partsToText, structuralProblems, tokenize } from './markers';
import {
  filterSegments,
  groupByScope,
  issuesBySegment,
  keptInEnglish,
  locatorLabel,
  sameTextSegments,
  sectionOrder,
  worstSeverity,
} from './segments';
import { defaultPicks, jobSopTitles, jobsByMigration, languageChoice, usableGlossaries } from './jobs';
import {
  defaultTranslationStep,
  groupVersions,
  isTranslationWorking,
  translationPermissions,
  translationStepStates,
} from './status';
import type {
  GlossaryRecord,
  LanguageTemplateRecord,
  RenderReport,
  Segment,
  TranslationArtifactKind,
  TranslationJob,
  TranslationJobRow,
  TranslationStatus,
  ValidationIssue,
} from './types';

// ── Fixtures ──────────────────────────────────────────────────────────

const ref = (kind: TranslationArtifactKind, scope?: string, version = 1) => ({ kind, scope, version, path: `${kind}.json`, sha256: '0' });

const PREPARED = [ref('segments')];
const TRANSLATED = [...PREPARED, ref('translation', 'TGT-1'), ref('translation', 'template')];
const CHECKED = [...TRANSLATED, ref('quality_report', 'translation')];
const RENDERED = [...CHECKED, ref('docx', 'translated'), ref('render_report', 'translated')];

function job(status: TranslationStatus, artifacts = RENDERED, extra: Partial<TranslationJob> = {}): TranslationJob {
  return { job_id: 'TRN-1', migration_job_id: 'MIG-1', language: 'de-DE', status, artifacts, running: false, ...extra };
}

const review = (render_current: boolean, can_approve: boolean) => ({ render_current, docx_version: 1, blockers: [], can_approve });

// ── Status, steps, permissions ────────────────────────────────────────

describe('translation status', () => {
  it('works until review, unless running', () => {
    expect(isTranslationWorking(job('TRANSLATING', TRANSLATED))).toBe(true);
    expect(isTranslationWorking(job('REVIEW_PENDING'))).toBe(false);
    expect(isTranslationWorking(job('REVIEW_PENDING', RENDERED, { running: true }))).toBe(true);
    expect(isTranslationWorking(job('APPROVED'))).toBe(false);
    expect(isTranslationWorking(job('FAILED_TECHNICAL', PREPARED))).toBe(false);
  });

  it('unlocks a step once its artifact exists and marks where the job is', () => {
    expect(translationStepStates(job('TRANSLATING', PREPARED))).toEqual({ prepare: 'done', translate: 'working', review: 'locked', final: 'locked' });
    expect(translationStepStates(job('REVIEW_PENDING'))).toEqual({ prepare: 'done', translate: 'done', review: 'current', final: 'available' });
    expect(translationStepStates(job('APPROVED'))).toEqual({ prepare: 'done', translate: 'done', review: 'done', final: 'done' });
  });

  it('shows review as working during a re-render, with the previous render still open', () => {
    const states = translationStepStates(job('RENDERING'));
    expect(states.review).toBe('working');
    expect(states.final).toBe('available');
  });

  it('opens where the job waits, else the latest reachable step', () => {
    expect(defaultTranslationStep(job('REVIEW_PENDING'))).toBe('review');
    expect(defaultTranslationStep(job('APPROVED'))).toBe('final');
    expect(defaultTranslationStep(job('PENDING', []))).toBe('prepare');
    expect(defaultTranslationStep(job('FAILED_TECHNICAL', TRANSLATED))).toBe('translate');
  });

  it('allows edits only in review, rendering only when out of date, approval only when the server says so', () => {
    const fresh = translationPermissions(job('REVIEW_PENDING', RENDERED, { review: review(true, true) }));
    expect(fresh).toMatchObject({ edit: true, render: false, approve: true, download: false, cancel: true, retry: false });
    const stale = translationPermissions(job('REVIEW_PENDING', RENDERED, { review: review(false, false) }));
    expect(stale).toMatchObject({ edit: true, render: true, approve: false });
    const busy = translationPermissions(job('REVIEW_PENDING', RENDERED, { running: true, review: review(false, false) }));
    expect(busy).toMatchObject({ edit: false, render: false, approve: false });
    expect(translationPermissions(job('APPROVED'))).toMatchObject({ edit: false, download: true, cancel: false });
    expect(translationPermissions(job('CANCELLED', PREPARED))).toMatchObject({ retry: true, cancel: false });
  });
});

// ── Versioned records ─────────────────────────────────────────────────

describe('groupVersions', () => {
  it('groups by id, newest version first, groups by their latest change', () => {
    const rec = (id: string, version: number, updated_at: string) => ({ id, version, updated_at });
    const groups = groupVersions(
      [rec('a', 1, '2026-10-01'), rec('b', 1, '2026-10-03'), rec('a', 2, '2026-10-05')],
      (r) => r.id,
    );
    expect(groups.map((g) => g.map((r) => `${r.id}${r.version}`))).toEqual([['a2', 'a1'], ['b1']]);
  });
});

// ── Glossary editor rows ──────────────────────────────────────────────

describe('glossary rows', () => {
  it('needs a source and a target unless kept in English; blank rows are ignored', () => {
    const rows = [...toRows([{ source_term: 'deviation', target_term: 'Abweichung' }]), emptyRow(), emptyRow()];
    rows[1].source_term = 'CAPA';
    rows[2].do_not_translate = false; // completely blank: dropped, not a problem
    const problems = rowProblems(rows);
    expect([...problems.keys()]).toEqual([rows[1].key]);
    rows[1].do_not_translate = true;
    expect(rowProblems(rows).size).toBe(0);
    expect(toEntries(rows)).toEqual([
      { source_term: 'deviation', target_term: 'Abweichung', case_sensitive: false, do_not_translate: false },
      { source_term: 'CAPA', target_term: 'CAPA', case_sensitive: false, do_not_translate: true },
    ]);
  });

  it('finds duplicates ignoring case unless case-sensitive, and collapses whitespace', () => {
    const rows = toRows([
      { source_term: 'Change  control', target_term: 'Änderungskontrolle' },
      { source_term: 'change control', target_term: 'Änderungssteuerung' },
    ]);
    expect(rowProblems(rows).get(rows[1].key)).toEqual(['"change control" is listed more than once']);
    rows[1].case_sensitive = true;
    rows[0].case_sensitive = true;
    expect(rowProblems(rows).size).toBe(0);
    expect(toEntries(rows)[0].source_term).toBe('Change control');
  });

  it('sees a change only when the saved entries would differ', () => {
    const saved = [{ source_term: 'deviation', target_term: 'Abweichung', note: 'QA' }];
    const rows = toRows(saved);
    expect(rowsChanged(rows, saved)).toBe(false);
    expect(rowsChanged([...rows, emptyRow()], saved)).toBe(false);
    rows[0].target_term = 'Abweichungen';
    expect(rowsChanged(rows, saved)).toBe(true);
  });
});

// ── Job lists ─────────────────────────────────────────────────────────

describe('job lists', () => {
  it('names a translation by its migration\'s SOP', () => {
    const titles = jobSopTitles([{ job_id: 'MIG-1', sop_record_id: 7 }, { job_id: 'MIG-2', sop_record_id: 8 }], new Map([[7, 'RPAS SOP']]));
    expect(titles.get('MIG-1')).toBe('RPAS SOP');
    expect(titles.get('MIG-2')).toBe('SOP #8');
  });

  it('preselects the newest approved glossary and ready template of the language, else none', () => {
    const g = (glossary_id: string, version: number, language: string, status: string, updated_at: string) =>
      ({ glossary_id, version, language, status, updated_at }) as GlossaryRecord;
    const t = (template_id: string, version: number, language: string, status: string, updated_at: string) =>
      ({ template_id, version, language, status, updated_at }) as LanguageTemplateRecord;
    const glossaries = [
      g('gx', 1, 'fr-FR', 'approved', '2026-10-01'),
      g('gx', 2, 'fr-FR', 'in_review', '2026-10-05'), // not approved: never offered
      g('gy', 1, 'fr-FR', 'approved', '2026-10-03'),
      g('gz', 1, 'de-DE', 'approved', '2026-10-09'),
    ];
    const templates = [t('tde', 1, 'de-DE', 'ready', '2026-10-02'), t('tde', 2, 'de-DE', 'extracted', '2026-10-04')];
    expect(defaultPicks('fr-FR', glossaries, templates)).toEqual({ glossary: 'gy@1', template: '' });
    expect(defaultPicks('de-DE', glossaries, templates)).toEqual({ glossary: 'gz@1', template: 'tde@1' });
    expect(defaultPicks('ja-JP', glossaries, templates)).toEqual({ glossary: '', template: '' });
    expect(usableGlossaries(glossaries, 'fr-FR').map((r) => `${r.glossary_id}@${r.version}`)).toEqual(['gy@1', 'gx@1']);
  });

  it('builds a request choice without the resources left at none', () => {
    expect(languageChoice('de-DE', { glossary: '', template: 'Template_Main@2' })).toEqual({
      language: 'de-DE', language_template_id: 'Template_Main', language_template_version: 2,
    });
    expect(languageChoice('fr-FR', { glossary: 'a@b@3', template: '' })).toEqual({ language: 'fr-FR', glossary_id: 'a@b', glossary_version: 3 });
  });

  it('groups jobs by migration, keeping their order', () => {
    const row = (job_id: string, migration_job_id: string) => ({ job_id, migration_job_id }) as TranslationJobRow;
    const grouped = jobsByMigration([row('T3', 'M1'), row('T2', 'M2'), row('T1', 'M1')]);
    expect(grouped.get('M1')!.map((j) => j.job_id)).toEqual(['T3', 'T1']);
  });
});

// ── Markers ───────────────────────────────────────────────────────────

describe('markers', () => {
  it('tokenizes pairs, objects, reference tokens, cells and line breaks', () => {
    const parts = tokenize('⟦1⟧Note:⟦/1⟧ see {{ref:SRC-5.2}}⟦2⟧a | b\nc', true);
    expect(parts.map((p) => p.type)).toEqual(['open', 'text', 'close', 'text', 'ref', 'object', 'text', 'cell', 'text', 'break', 'text']);
    expect(partsToText(parts)).toBe('⟦1⟧Note:⟦/1⟧ see {{ref:SRC-5.2}}⟦2⟧a | b\nc');
    expect(tokenize('a | b', false).map((p) => p.type)).toEqual(['text']); // a "|" is text unless the English has cells
    expect(tokenize('Chapter ⟦1⟧', false)[1]).toMatchObject({ type: 'object', k: 1 });
  });

  it('finds the problems the server would refuse, as its checks word them', () => {
    expect(structuralProblems('see {{ref:A}}', 'siehe {{ref:A}}')).toEqual([]);
    expect(structuralProblems('see {{ref:A}}', '⟦1⟧')).toEqual(['no translation']);
    expect(structuralProblems('see {{ref:A}}', 'siehe A')).toEqual(['reference tokens changed: lost {{ref:A}}']);
    expect(structuralProblems('⟦1⟧Bold⟦/1⟧ text', 'Text ⟦1⟧fett⟦/1⟧')).toEqual([]); // pairs may move
    expect(structuralProblems('⟦1⟧Bold⟦/1⟧ text', 'fett Text')).toEqual(['lost the marker(s) ⟦1⟧ ⟦/1⟧']);
    expect(structuralProblems('⟦1⟧a⟦/1⟧⟦2⟧b⟦/2⟧', '⟦1⟧a⟦2⟧b⟦/1⟧⟦/2⟧')).toEqual(['the pair ⟦1⟧…⟦/1⟧ is out of order or crosses another pair']);
    expect(structuralProblems('a | b | c', 'x | y')).toEqual(["2 table cell separator(s) '|' in the English, 1 in the translation"]);
  });

  it('keys the markers as a multiset, so moving one keeps the key and dropping one changes it', () => {
    const key = (t: string) => markerKey(tokenize(t, false));
    expect(key('⟦1⟧a⟦/1⟧ {{ref:X}}')).toBe(key('{{ref:X}} b ⟦1⟧c⟦/1⟧'));
    expect(key('⟦1⟧a⟦/1⟧ {{ref:X}}')).not.toBe(key('⟦1⟧a⟦/1⟧'));
  });

  it('cleans typed or pasted marker characters', () => {
    expect(cleanTyped('a ⟦3⟧ {{ref:Y}} b')).toBe('a 3 ref:Y b');
  });

  it('round-trips a text through the editor document, line breaks and markers included', () => {
    const text = '⟦1⟧Hinweis:⟦/1⟧ siehe {{ref:SRC-5.2}}\nzweite Zeile | Zelle';
    const doc = toEditorDoc(text, true);
    expect(doc.content?.[0].content?.filter((n) => n.type === 'marker')).toHaveLength(4);
    expect(fromEditorDoc(doc)).toBe(text);
    const typed = { ...doc, content: [{ type: 'paragraph', content: [...(doc.content?.[0].content ?? []), { type: 'text', text: ' ⟦9⟧' }] }] };
    expect(fromEditorDoc(typed)).toBe(`${text} 9`);
  });

  it('marks the words inside a formatting pair', () => {
    const parts = tokenize('a ⟦2⟧b⟦/2⟧ c', false);
    expect([...formattedRuns(parts)]).toEqual([[2, 2]]);
  });
});

// ── Segments ──────────────────────────────────────────────────────────

describe('segments', () => {
  const seg = (segment_id: string, kind: Segment['kind'], source_text: string, extra: Partial<Segment> = {}): Segment => ({
    segment_id, kind, source_text, target_text: `DE ${source_text}`, origin: 'llm', locator: { section_id: 'TGT-2' }, ...extra,
  });
  const all = [
    seg('SEG-0001', 'claim', 'Purpose', { locator: { section_id: 'TGT-1' } }),
    seg('SEG-0002', 'table_cell', 'Owner', { locator: { section_id: 'TGT-2', row: 0, col: 1 } }),
    seg('SEG-0003', 'table_cell', 'Owner', { locator: { section_id: 'TGT-2', row: 1, col: 1 }, origin: 'human' }),
    seg('SEG-0004', 'claim', 'Owner'),
    seg('SEG-0005', 'xref', 'Chapter ⟦1⟧', { locator: { ref_index: 0 } }),
    seg('SEG-0006', 'template_text', 'PURPOSE', { locator: { block_path: 'body/p[2]' } }),
  ];

  it('orders sections as the template, then headings and labels, then cross-references', () => {
    const scopes = [...groupByScope(all).keys()];
    expect(scopes).toEqual(['TGT-1', 'TGT-2', 'xrefs', 'template']);
    const order = sectionOrder(scopes, [{ section_id: 'TGT-2', number: '2', heading: 'Scope' }, { section_id: 'TGT-1', number: '1', heading: 'Purpose' }]);
    expect(order.map((s) => s.scope)).toEqual(['TGT-2', 'TGT-1', 'template', 'xrefs']);
  });

  it('labels where a segment sits', () => {
    expect(locatorLabel(all[1])).toBe('Table r1 c2');
    expect(locatorLabel(seg('S', 'claim', 'a | b'))).toBe('Table row');
    expect(locatorLabel(all[5])).toBe('Heading or label');
  });

  it('finds the other segments a same-English edit changes, leaving human edits alone', () => {
    expect(sameTextSegments(all[1], all).map((s) => s.segment_id)).toEqual(['SEG-0004']);
  });

  it('maps issues to segments and finds the worst', () => {
    const issue = (issue_id: string, severity: ValidationIssue['severity'], segment_ids: string[], gate?: ValidationIssue['gate']) =>
      ({ issue_id, severity, category: 'language', message: issue_id, segment_ids, gate }) as ValidationIssue;
    const map = issuesBySegment([issue('A', 'low', ['SEG-0002']), issue('B', 'medium', ['SEG-0002', 'SEG-0004'])]);
    expect(map.get('SEG-0002')?.map((i) => i.issue_id)).toEqual(['A', 'B']);
    expect(worstSeverity(map.get('SEG-0002')!)).toBe('medium');
    expect(worstSeverity([issue('C', 'low', [], 'numerical_change')])).toBe('critical');
  });

  it('reads the segments a render showed in English from its warnings', () => {
    const report = { warnings: ['SEG-0012: no translation; shown in English', 'TGT-5-RACI: source table … written with its own columns'] } as RenderReport;
    expect([...keptInEnglish(report)]).toEqual(['SEG-0012']);
  });

  it('filters by issues, edits and text', () => {
    const open = new Map([['SEG-0004', [{ issue_id: 'X' } as ValidationIssue]]]);
    const context = { open, english: new Set<string>() };
    expect(filterSegments(all, 'issues', context).map((s) => s.segment_id)).toEqual(['SEG-0004']);
    expect(filterSegments(all, 'edited', context).map((s) => s.segment_id)).toEqual(['SEG-0003']);
    expect(filterSegments(all, 'all', context, 'chapter').map((s) => s.segment_id)).toEqual(['SEG-0005']);
  });
});

// ── Activity ──────────────────────────────────────────────────────────

describe('activity labels', () => {
  it('summarizes the translator once, without counting tokens twice', () => {
    const event = {
      id: 1, job_id: 'TRN-1', at: '', actor: null, event: 'translator', from_status: null, to_status: null,
      detail: {
        translated: 318, groups: 325, copied: 7, calls: 8, failed_calls: 0, terms: 44, terms_translated: 44,
        usage: { calls: 9, input_tokens: 18210, output_tokens: 9893, total_tokens: 28103 },
      },
    };
    expect(TRANSLATION_LABELS.summary?.(event)).toBe('318 of 325 distinct texts translated, 7 copied · 8 calls · 44/44 document terms · 28,103 tokens');
  });
});
