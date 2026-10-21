import React from 'react';
import { AlertCircle, Check, Loader2, PauseCircle } from 'lucide-react';
import { clsx } from 'clsx';
import { PIPELINE, humanize, statusInfo } from '../status';
import type { MigrationJob, TemplateModel } from '../types';

const SECTION_DONE = new Set(['drafted', 'validated', 'approved']);

/** Where the pipeline is: the stage timeline and every template section's state. */
export const JobProgress: React.FC<{ job: MigrationJob; template?: TemplateModel; compact?: boolean }> = ({ job, template, compact }) => {
  const at = PIPELINE.indexOf(job.status);
  const headings = new Map(template?.sections.map((s) => [s.section_id, `${s.number ? `${s.number} ` : ''}${s.heading}`]) ?? []);
  const done = job.sections.filter((s) => SECTION_DONE.has(s.status)).length;

  return (
    <div className={clsx('space-y-5', compact ? '' : 'mx-auto max-w-3xl px-6 py-8')}>
      {!compact && (
        <div className="flex items-center gap-3">
          <Loader2 className="size-5 animate-spin text-info" />
          <div>
            <div className="text-sm font-semibold text-text-main">{statusInfo(job.status).label}…</div>
            <div className="text-xs text-text-muted">This page updates by itself. You can leave it and come back.</div>
          </div>
        </div>
      )}

      <ol className="grid grid-cols-2 gap-1.5 sm:grid-cols-3 lg:grid-cols-4">
        {PIPELINE.map((stage, index) => {
          const pause = stage.endsWith('_REVIEW_PENDING');
          if (pause && job.mode === 'auto') return null;
          const state = at < 0 ? (job.artifacts.length ? 'done' : 'todo') : index < at ? 'done' : index === at ? 'now' : 'todo';
          return (
            <li
              key={stage}
              className={clsx(
                'flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-[11px]',
                state === 'done' && 'border-primary/20 text-text-muted',
                state === 'now' && 'border-info/40 bg-info/10 text-text-main',
                state === 'todo' && 'border-border text-text-muted/60',
              )}
            >
              {state === 'done' ? (
                <Check className="size-3.5 text-primary" />
              ) : state === 'now' ? (
                pause ? <PauseCircle className="size-3.5 text-warning" /> : <Loader2 className="size-3.5 animate-spin text-info" />
              ) : (
                <span className="size-3.5 rounded-full border border-border" />
              )}
              {statusInfo(stage).label}
            </li>
          );
        })}
      </ol>

      {job.sections.length > 0 && (
        <div>
          <div className="mb-2 flex items-center justify-between text-xs">
            <span className="font-semibold text-text-main">Template sections</span>
            <span className="text-text-muted">{done} / {job.sections.length} drafted</span>
          </div>
          <div className="mb-3 h-1.5 overflow-hidden rounded-full bg-white/5">
            <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${(done / job.sections.length) * 100}%` }} />
          </div>
          <ul className="grid gap-1 sm:grid-cols-2">
            {job.sections.map((s) => (
              <li key={s.target_section_id} className="flex items-center gap-2 rounded border border-border px-2.5 py-1.5 text-[11px]">
                {s.last_error ? (
                  <AlertCircle className="size-3.5 shrink-0 text-danger" />
                ) : SECTION_DONE.has(s.status) ? (
                  <Check className="size-3.5 shrink-0 text-primary" />
                ) : s.status === 'pending' ? (
                  <span className="size-3.5 shrink-0 rounded-full border border-border" />
                ) : (
                  <Loader2 className="size-3.5 shrink-0 animate-spin text-info" />
                )}
                <span className="min-w-0 flex-1 truncate text-text-main" title={s.last_error}>
                  {headings.get(s.target_section_id) ?? s.target_section_id}
                </span>
                <span className="shrink-0 text-text-muted">
                  {humanize(s.status)}
                  {s.attempts > 1 && ` · ${s.attempts} tries`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};
