import React from 'react';
import { AlertCircle, Check, Circle, Loader2 } from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/ui/Button';
import { formatDate } from '@/lib/format';
import { TRANSLATION_LABELS } from '../activity';
import { useSegments, useTranslationAudit, useTranslationMutations } from '../hooks';
import { TRANSLATION_PIPELINE } from '../status';
import type { JobEvent, TranslationJob, TranslationStatus } from '../types';

const STAGE: Record<string, { label: string; hint: string; event: string }> = {
  PREPARING: { label: 'Preparing', hint: 'Snapshot the final English document and cut it into segments', event: 'segments' },
  TRANSLATING: { label: 'Translating', hint: 'Document terms first, then headings and labels, then the section texts', event: 'translator' },
  CHECKING: { label: 'Checking', hint: 'Markers, references, numbers, IDs, glossary and document terms', event: 'checks' },
  REPAIRING: { label: 'Repairing', hint: 'One retranslation of each segment with a problem', event: 'repair' },
  RENDERING: { label: 'Rendering', hint: 'The translated document, its first page, headers, footers and table of contents', event: 'render' },
};

const last = (events: JobEvent[], name: string) => [...events].reverse().find((e) => e.event === name);

/** Where the pipeline is: each stage with what it did, while the job works. */
export const TranslationProgress: React.FC<{ job: TranslationJob }> = ({ job }) => {
  const audit = useTranslationAudit(job);
  const events = audit.data ?? [];
  const at = TRANSLATION_PIPELINE.indexOf(job.status);
  const reached = new Set(events.map((e) => e.to_status).filter(Boolean) as TranslationStatus[]);
  return (
    <div className="mx-auto max-w-2xl px-6 py-8">
      <h2 className="text-sm font-semibold text-text-main">{job.status === 'PENDING' ? 'Queued' : 'The translation is running'}</h2>
      <p className="mt-1 text-xs text-text-muted">This page follows the job; you can leave and come back. The review opens once the document is rendered.</p>
      <ol className="mt-5 space-y-3">
        {TRANSLATION_PIPELINE.map((stage, index) => {
          const info = STAGE[stage];
          const state = index < at || (at < 0 && reached.has(stage)) ? 'done' : index === at ? 'now' : reached.has(stage) ? 'done' : 'todo';
          const event = last(events, info.event);
          const line = event ? TRANSLATION_LABELS.summary?.(event) : null;
          return (
            <li key={stage} className="flex gap-3">
              <span className={clsx('mt-0.5 grid size-5 shrink-0 place-items-center rounded-full border',
                state === 'done' && 'border-primary/50 bg-primary/15 text-primary',
                state === 'now' && 'border-info/50 bg-info/10 text-info',
                state === 'todo' && 'border-border text-text-muted')}>
                {state === 'done' ? <Check className="size-3" /> : state === 'now' ? <Loader2 className="size-3 animate-spin" /> : <Circle className="size-2" />}
              </span>
              <div className="min-w-0 text-xs">
                <div className={clsx('font-medium', state === 'todo' ? 'text-text-muted' : 'text-text-main')}>{info.label}</div>
                <div className="text-[11px] text-text-muted">{line && state !== 'todo' ? line : info.hint}</div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
};

/** The job stopped on a technical error. */
export const TranslationFailed: React.FC<{ job: TranslationJob }> = ({ job }) => {
  const { retry } = useTranslationMutations(job.job_id);
  return (
    <div className="mx-auto max-w-lg px-6 py-12 text-center">
      <AlertCircle className="mx-auto size-8 text-danger" />
      <h3 className="mt-3 text-sm font-semibold text-text-main">{job.status === 'CANCELLED' ? 'The translation was cancelled' : 'The translation stopped on a technical error'}</h3>
      {job.error && <p className="mt-2 rounded-md border border-danger/30 bg-danger/[0.05] px-3 py-2 text-left font-mono text-[11px] text-text-muted">{job.error}</p>}
      <Button size="sm" variant="primary" className="mt-4" isLoading={retry.isPending} onClick={() => retry.mutate(undefined)}>Retry from the stage that stopped</Button>
    </div>
  );
};

/** ① and ② once done: what preparing and translating produced. */
export const StepSummary: React.FC<{ job: TranslationJob; step: 'prepare' | 'translate' }> = ({ job, step }) => {
  const segments = useSegments(job);
  const audit = useTranslationAudit(job);
  const events = audit.data ?? [];
  const shown = step === 'prepare'
    ? ['segments', 'glossary', 'no_glossary', 'front_matter', 'no_language_template', 'english_render_problems']
    : ['translator', 'checks', 'repair'];
  const items = events.filter((e) => shown.includes(e.event));
  const counts = segments.data?.counts ?? {};
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-2xl space-y-5 px-6 py-8 text-xs">
        <div>
          <h2 className="text-sm font-semibold text-text-main">{step === 'prepare' ? 'Preparing' : 'Translating'}</h2>
          <p className="mt-1 text-text-muted">
            {step === 'prepare'
              ? 'The final English document of the migration, cut into the pieces that are translated.'
              : 'Each distinct English text is translated once, checked, and repaired once when a check fails.'}
          </p>
        </div>
        {step === 'prepare' && segments.data && (
          <div className="dashboard-card grid grid-cols-2 gap-3 p-4 sm:grid-cols-5">
            {([['claim', 'Texts'], ['table_cell', 'Table cells'], ['table_header', 'Table headers'], ['template_text', 'Headings, labels'], ['xref', 'References']] as const).map(([k, label]) => (
              <div key={k}>
                <div className="text-lg font-semibold text-text-main">{counts[k] ?? 0}</div>
                <div className="text-[11px] text-text-muted">{label}</div>
              </div>
            ))}
          </div>
        )}
        {step === 'prepare' && (segments.data?.notes.length ?? 0) > 0 && (
          <ul className="space-y-1">
            {segments.data!.notes.map((n) => <li key={n} className="rounded-md border border-border bg-black/10 px-3 py-2 text-text-muted">{n}</li>)}
          </ul>
        )}
        <ol className="space-y-2">
          {items.map((e) => (
            <li key={e.id} className="rounded-md border border-border px-3 py-2">
              <div className="flex items-baseline justify-between gap-2">
                <span className="font-medium text-text-main">{TRANSLATION_LABELS.title?.(e)}</span>
                <span className="text-[11px] text-text-muted">{formatDate(e.at)}</span>
              </div>
              {TRANSLATION_LABELS.summary?.(e) && <p className="mt-0.5 text-[11px] text-text-muted">{TRANSLATION_LABELS.summary(e)}</p>}
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
};
