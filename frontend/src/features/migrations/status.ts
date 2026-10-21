import type { ArtifactKind, JobStatus, MigrationJob, Severity } from './types';

/** The four review steps of a job, in order. */
export type Step = 'sections' | 'slots' | 'draft' | 'final';
export type StepState = 'done' | 'current' | 'working' | 'locked' | 'available';

export const STEPS: { id: Step; label: string; short: string }[] = [
  { id: 'sections', label: 'Section mapping', short: 'Sections' },
  { id: 'slots', label: 'Slot mapping', short: 'Slots' },
  { id: 'draft', label: 'Draft & issues', short: 'Draft' },
  { id: 'final', label: 'Final document', short: 'Final' },
];

type Tone = 'neutral' | 'working' | 'review' | 'success' | 'warning' | 'danger';

const STATUS: Record<JobStatus, { label: string; tone: Tone; step: Step | null }> = {
  PENDING: { label: 'Queued', tone: 'working', step: null },
  PARSING: { label: 'Loading inputs', tone: 'working', step: null },
  PLANNING_SECTIONS: { label: 'Planning sections', tone: 'working', step: 'sections' },
  SECTION_PLAN_REVIEW_PENDING: { label: 'Section plan to review', tone: 'review', step: 'sections' },
  PLANNING_SLOTS: { label: 'Planning slots', tone: 'working', step: 'slots' },
  SLOT_PLAN_REVIEW_PENDING: { label: 'Slot plan to review', tone: 'review', step: 'slots' },
  DRAFTING: { label: 'Drafting', tone: 'working', step: 'draft' },
  VALIDATING: { label: 'Validating', tone: 'working', step: 'draft' },
  REPAIRING: { label: 'Repairing', tone: 'working', step: 'draft' },
  ASSEMBLING: { label: 'Assembling', tone: 'working', step: 'draft' },
  RECONCILING: { label: 'Reconciling', tone: 'working', step: 'draft' },
  RENDERING: { label: 'Rendering', tone: 'working', step: 'draft' },
  QUALITY_REVIEW: { label: 'Quality review', tone: 'working', step: 'draft' },
  HUMAN_REVIEW_REQUIRED: { label: 'Needs review', tone: 'review', step: 'draft' },
  MANUALLY_EDITED: { label: 'Edited, re-check needed', tone: 'review', step: 'draft' },
  COMPLETED: { label: 'Completed', tone: 'success', step: 'final' },
  COMPLETED_WITH_WARNINGS: { label: 'Completed with warnings', tone: 'warning', step: 'final' },
  FAILED_TECHNICAL: { label: 'Failed', tone: 'danger', step: null },
  CANCELLED: { label: 'Cancelled', tone: 'neutral', step: null },
};

/** The pipeline stages in order, for the progress timeline. */
export const PIPELINE: JobStatus[] = [
  'PARSING', 'PLANNING_SECTIONS', 'SECTION_PLAN_REVIEW_PENDING', 'PLANNING_SLOTS', 'SLOT_PLAN_REVIEW_PENDING',
  'DRAFTING', 'VALIDATING', 'REPAIRING', 'ASSEMBLING', 'RECONCILING', 'RENDERING', 'QUALITY_REVIEW',
];

export const TONE_CLASSES: Record<Tone, string> = {
  neutral: 'border-border bg-white/5 text-text-muted',
  working: 'border-info/30 bg-info/10 text-info',
  review: 'border-warning/30 bg-warning/10 text-warning',
  success: 'border-primary/30 bg-primary/10 text-primary',
  warning: 'border-warning/30 bg-warning/10 text-warning',
  danger: 'border-danger/30 bg-danger/10 text-danger',
};

export function statusInfo(status: JobStatus) {
  const info = STATUS[status] ?? { label: status, tone: 'neutral' as Tone, step: null };
  return { ...info, classes: TONE_CLASSES[info.tone] };
}

const REVIEW_PENDING: JobStatus[] = ['SECTION_PLAN_REVIEW_PENDING', 'SLOT_PLAN_REVIEW_PENDING'];
const TERMINAL: JobStatus[] = ['COMPLETED', 'COMPLETED_WITH_WARNINGS', 'FAILED_TECHNICAL', 'CANCELLED'];
const FINISHED: JobStatus[] = ['HUMAN_REVIEW_REQUIRED', 'MANUALLY_EDITED', 'COMPLETED', 'COMPLETED_WITH_WARNINGS'];

/** The pipeline is working on the job (poll it): not paused for review, not finished. */
export function isWorking(job: Pick<MigrationJob, 'status' | 'running'>): boolean {
  if (job.running) return true;
  return !REVIEW_PENDING.includes(job.status) && !TERMINAL.includes(job.status) && !FINISHED.includes(job.status);
}

export const isTerminal = (status: JobStatus) => TERMINAL.includes(status);
export const isExportable = (status: JobStatus) => status === 'COMPLETED' || status === 'COMPLETED_WITH_WARNINGS';

/** What the reviewer may change right now (the server enforces the same rules). */
export function permissions(job: MigrationJob) {
  const idle = !job.running;
  return {
    editSectionPlan: idle && job.status === 'SECTION_PLAN_REVIEW_PENDING',
    editSlotPlan: idle && job.status === 'SLOT_PLAN_REVIEW_PENDING',
    editDrafts: idle && ['HUMAN_REVIEW_REQUIRED', 'COMPLETED_WITH_WARNINGS', 'MANUALLY_EDITED'].includes(job.status),
    resolveIssues: idle && ['HUMAN_REVIEW_REQUIRED', 'COMPLETED_WITH_WARNINGS', 'MANUALLY_EDITED'].includes(job.status),
    recheck: idle && job.status === 'MANUALLY_EDITED',
    cancel: !isTerminal(job.status),
    retry: idle && ['FAILED_TECHNICAL', 'CANCELLED'].includes(job.status),
    export: idle && isExportable(job.status),
  };
}

const STEP_ARTIFACT: Record<Step, ArtifactKind> = {
  sections: 'section_plan',
  slots: 'slot_plan',
  draft: 'section_draft',
  final: 'docx',
};

/** Each step's state: reachable once its artifact exists; current where the job waits for the reviewer. */
export function stepStates(job: MigrationJob): Record<Step, StepState> {
  const has = (kind: ArtifactKind) => job.artifacts.some((a) => a.kind === kind);
  const at = statusInfo(job.status).step;
  const atIndex = at ? STEPS.findIndex((s) => s.id === at) : -1;
  const working = isWorking(job);
  const states = {} as Record<Step, StepState>;
  STEPS.forEach((step, index) => {
    if (step.id === at) {
      states[step.id] = working ? 'working' : 'current';
    } else if (!has(STEP_ARTIFACT[step.id])) {
      states[step.id] = 'locked';
    } else {
      states[step.id] = index < atIndex ? 'done' : 'available';
    }
  });
  return states;
}

/** The step to open by default: where the job waits for the reviewer, else the latest reachable one. */
export function defaultStep(job: MigrationJob): Step {
  const states = stepStates(job);
  const current = STEPS.find((s) => states[s.id] === 'current' || states[s.id] === 'working');
  if (current) return current.id;
  const reachable = STEPS.filter((s) => states[s.id] !== 'locked');
  return reachable.length ? reachable[reachable.length - 1].id : 'sections';
}

export const SEVERITY_ORDER: Severity[] = ['critical', 'high', 'medium', 'low', 'info'];

export const SEVERITY_CLASSES: Record<Severity, string> = {
  critical: 'border-danger/40 bg-danger/15 text-danger',
  high: 'border-danger/30 bg-danger/10 text-danger',
  medium: 'border-warning/30 bg-warning/10 text-warning',
  low: 'border-info/30 bg-info/10 text-info',
  info: 'border-border bg-white/5 text-text-muted',
};

/** "missing_slot" → "Missing slot". */
export const humanize = (value: string) => {
  const text = value.replace(/_/g, ' ').toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
};
