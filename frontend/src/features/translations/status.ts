import { TONE_CLASSES } from '@/features/migrations/status';
import type { StepState } from '@/features/migrations/status';
import type { GlossaryStatus, LanguageTemplateStatus, TranslationArtifactKind, TranslationJob, TranslationStatus } from './types';

export type { StepState };

/** The four steps of a translation job, in order. */
export type TranslationStep = 'prepare' | 'translate' | 'review' | 'final';

export const TRANSLATION_STEPS: { id: TranslationStep; label: string; short: string }[] = [
  { id: 'prepare', label: 'Preparing', short: 'Prepare' },
  { id: 'translate', label: 'Translating', short: 'Translate' },
  { id: 'review', label: 'Review', short: 'Review' },
  { id: 'final', label: 'Final document', short: 'Final' },
];

type Tone = keyof typeof TONE_CLASSES;

const STATUS: Record<TranslationStatus, { label: string; tone: Tone; step: TranslationStep | null }> = {
  PENDING: { label: 'Queued', tone: 'working', step: null },
  PREPARING: { label: 'Preparing', tone: 'working', step: 'prepare' },
  TRANSLATING: { label: 'Translating', tone: 'working', step: 'translate' },
  CHECKING: { label: 'Checking', tone: 'working', step: 'translate' },
  REPAIRING: { label: 'Repairing', tone: 'working', step: 'translate' },
  RENDERING: { label: 'Rendering', tone: 'working', step: 'review' },
  REVIEW_PENDING: { label: 'To review', tone: 'review', step: 'review' },
  APPROVED: { label: 'Approved', tone: 'success', step: 'final' },
  FAILED_TECHNICAL: { label: 'Failed', tone: 'danger', step: null },
  CANCELLED: { label: 'Cancelled', tone: 'neutral', step: null },
};

/** The pipeline stages in order, for the progress timeline. */
export const TRANSLATION_PIPELINE: TranslationStatus[] = ['PREPARING', 'TRANSLATING', 'CHECKING', 'REPAIRING', 'RENDERING'];

export const ALL_STATUSES = Object.keys(STATUS) as TranslationStatus[];

export function translationStatusInfo(status: TranslationStatus) {
  const info = STATUS[status] ?? { label: status, tone: 'neutral' as Tone, step: null };
  return { ...info, classes: TONE_CLASSES[info.tone] };
}

const TERMINAL: TranslationStatus[] = ['APPROVED', 'FAILED_TECHNICAL', 'CANCELLED'];
const PAUSED: TranslationStatus[] = ['REVIEW_PENDING', ...TERMINAL];

/** The pipeline is working on the job (poll it): not waiting for review, not finished. */
export function isTranslationWorking(job: Pick<TranslationJob, 'status' | 'running'>): boolean {
  return job.running || !PAUSED.includes(job.status);
}

export const isTranslationTerminal = (status: TranslationStatus) => TERMINAL.includes(status);

/** What the reviewer may do right now (the server enforces the same rules). */
export function translationPermissions(job: TranslationJob) {
  const idle = !job.running;
  const inReview = idle && job.status === 'REVIEW_PENDING';
  return {
    edit: inReview,
    render: inReview && !!job.review && !job.review.render_current,
    approve: inReview && !!job.review?.can_approve,
    cancel: !isTranslationTerminal(job.status),
    retry: idle && (job.status === 'FAILED_TECHNICAL' || job.status === 'CANCELLED'),
    download: idle && job.status === 'APPROVED',
  };
}

const STEP_ARTIFACT: Record<TranslationStep, [TranslationArtifactKind, string | undefined]> = {
  prepare: ['segments', undefined],
  translate: ['translation', '*'],
  review: ['quality_report', 'translation'],
  final: ['docx', 'translated'],
};

const hasArtifact = (job: TranslationJob, kind: TranslationArtifactKind, scope: string | undefined) =>
  job.artifacts.some((a) => a.kind === kind && (scope === '*' || a.scope === scope));

/** Each step's state: reachable once its artifact exists; current where the job waits for the reviewer. */
export function translationStepStates(job: TranslationJob): Record<TranslationStep, StepState> {
  const at = translationStatusInfo(job.status).step;
  const atIndex = at ? TRANSLATION_STEPS.findIndex((s) => s.id === at) : -1;
  const working = isTranslationWorking(job);
  const states = {} as Record<TranslationStep, StepState>;
  TRANSLATION_STEPS.forEach((step, index) => {
    if (step.id === at) {
      states[step.id] = working ? 'working' : job.status === 'APPROVED' ? 'done' : 'current';
    } else if (!hasArtifact(job, ...STEP_ARTIFACT[step.id])) {
      states[step.id] = 'locked';
    } else {
      states[step.id] = index < atIndex || atIndex < 0 ? 'done' : 'available';
    }
  });
  return states;
}

/** The step to open by default: where the job waits or works, else the latest reachable one. */
export function defaultTranslationStep(job: TranslationJob): TranslationStep {
  const states = translationStepStates(job);
  const at = translationStatusInfo(job.status).step;
  if (at && states[at] !== 'locked') return at;
  const reachable = TRANSLATION_STEPS.filter((s) => states[s.id] !== 'locked');
  return reachable.length ? reachable[reachable.length - 1].id : 'prepare';
}

// ── Resources ─────────────────────────────────────────────────────────

export const GLOSSARY_STATUS: Record<GlossaryStatus, { label: string; tone: Tone }> = {
  uploaded: { label: 'Uploaded', tone: 'neutral' },
  in_review: { label: 'In review', tone: 'review' },
  approved: { label: 'Approved', tone: 'success' },
  failed: { label: 'Failed', tone: 'danger' },
};

export const TEMPLATE_STATUS: Record<LanguageTemplateStatus, { label: string; tone: Tone }> = {
  uploaded: { label: 'Uploaded', tone: 'neutral' },
  extracted: { label: 'To check', tone: 'review' },
  ready: { label: 'Ready', tone: 'success' },
  failed: { label: 'Failed', tone: 'danger' },
};

/** Records grouped by their id, newest version first in each group; groups by their newest record. */
export function groupVersions<T extends { version: number; updated_at: string }>(records: T[], idOf: (r: T) => string): T[][] {
  const groups = new Map<string, T[]>();
  records.forEach((r) => groups.set(idOf(r), [...(groups.get(idOf(r)) ?? []), r]));
  return [...groups.values()]
    .map((g) => [...g].sort((a, b) => b.version - a.version))
    .sort((a, b) => b[0].updated_at.localeCompare(a[0].updated_at));
}
