import { describe, expect, it } from 'vitest';
import { emptyRow, rowProblems, rowsChanged, toEntries, toRows } from './glossaryEdit';
import { jobSopTitles, jobsByMigration } from './jobs';
import {
  defaultTranslationStep,
  groupVersions,
  isTranslationWorking,
  translationPermissions,
  translationStepStates,
} from './status';
import type { TranslationArtifactKind, TranslationJob, TranslationJobRow, TranslationStatus } from './types';

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

  it('groups jobs by migration, keeping their order', () => {
    const row = (job_id: string, migration_job_id: string) => ({ job_id, migration_job_id }) as TranslationJobRow;
    const grouped = jobsByMigration([row('T3', 'M1'), row('T2', 'M2'), row('T1', 'M1')]);
    expect(grouped.get('M1')!.map((j) => j.job_id)).toEqual(['T3', 'T1']);
  });
});
