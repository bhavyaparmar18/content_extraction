import React, { useState } from 'react';
import { Bot, CheckCircle2, Download, Edit3, Flag, GitBranch, Loader2, RefreshCw, User } from 'lucide-react';
import { clsx } from 'clsx';
import { formatDate } from '@/lib/format';
import { useAudit } from '../hooks';
import { actorName, splitNote } from '../report';
import { humanize, statusInfo } from '../status';
import type { JobEvent, JobStatus, MigrationJob } from '../types';

/** The job's audit trail: status changes, reviewer edits with their before and after, LLM calls, exports. */
export const ActivityLog: React.FC<{ job: MigrationJob }> = ({ job }) => {
  const audit = useAudit(job.job_id, job);
  const [technical, setTechnical] = useState(false);
  const events = (audit.data ?? []).filter((e) => technical || !TECHNICAL.has(e.event)).reverse();
  const llmCalls = (audit.data ?? []).filter((e) => e.event === 'llm_call');
  const tokens = llmCalls.reduce((n, e) => n + (e.detail?.input_tokens ?? 0) + (e.detail?.output_tokens ?? 0), 0);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-5 py-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-sm font-semibold text-text-main">Activity</h2>
            <p className="text-xs text-text-muted">
              Everything recorded for this job, newest first. {llmCalls.length} LLM call(s){tokens ? `, ${tokens.toLocaleString()} tokens` : ''}.
            </p>
          </div>
          <label className="flex items-center gap-2 text-xs text-text-muted">
            <input type="checkbox" checked={technical} onChange={(e) => setTechnical(e.target.checked)} className="rounded border-border bg-transparent text-primary" />
            Show technical events (LLM calls, saved files, stages)
          </label>
        </div>
        {audit.isLoading && <Loader2 className="size-4 animate-spin text-text-muted" />}
        <ol className="relative space-y-2 border-l border-border pl-5">
          {events.map((e) => <EventItem key={e.id} event={e} />)}
        </ol>
      </div>
    </div>
  );
};

/** Pipeline bookkeeping, hidden unless asked for: the reviewer's history is the rest. */
const TECHNICAL = new Set(['llm_call', 'artifact', 'stage_started']);

const ICONS: Record<string, React.ReactNode> = {
  status: <RefreshCw className="size-3" />,
  slot_edited: <Edit3 className="size-3" />,
  plan_edited: <Edit3 className="size-3" />,
  issue_resolved: <CheckCircle2 className="size-3" />,
  export: <Download className="size-3" />,
  llm_call: <Bot className="size-3" />,
  gap_removed: <Flag className="size-3" />,
  reconcile: <GitBranch className="size-3" />,
};

const EventItem: React.FC<{ event: JobEvent }> = ({ event }) => {
  const [open, setOpen] = useState(false);
  const d = event.detail ?? {};
  const isStatus = !!event.to_status;
  return (
    <li className="relative text-xs">
      <span className={clsx('absolute -left-[27px] top-0.5 grid size-4 place-items-center rounded-full border bg-app', event.actor && event.actor !== 'system' ? 'border-info/50 text-info' : 'border-border text-text-muted')}>
        {ICONS[event.event] ?? (isStatus ? ICONS.status : <span className="size-1 rounded-full bg-current" />)}
      </span>
      <div className="flex flex-wrap items-baseline gap-x-2">
        <span className="font-medium text-text-main">{title(event)}</span>
        <span className="text-[11px] text-text-muted">{formatDate(event.at)}</span>
        <span className="flex items-center gap-1 text-[11px] text-text-muted">
          <User className="size-2.5" />
          {actorName(event.actor)}
        </span>
        {Object.keys(d).length > 0 && (
          <button type="button" onClick={() => setOpen((o) => !o)} className="text-[11px] text-primary hover:underline">
            {open ? 'less' : 'details'}
          </button>
        )}
      </div>
      {summary(event) && <p className="mt-0.5 text-[11px] text-text-muted">{summary(event)}</p>}
      {open && event.event === 'slot_edited' ? (
        <div className="mt-1.5 space-y-1">
          {(d.changed ?? []).map((c: { claim_id: string; before: string; after: string }) => (
            <div key={c.claim_id} className="rounded border border-border p-2 text-[11px]">
              <span className="unit-id">{c.claim_id}</span>
              <p className="text-text-muted line-through">{c.before}</p>
              <p className="text-text-main">{c.after}</p>
            </div>
          ))}
          {(d.added ?? []).map((c: { claim_id: string; text: string }) => <p key={c.claim_id} className="text-[11px] text-primary">+ {c.text}</p>)}
          {(d.removed ?? []).map((c: { claim_id: string; text: string }) => <p key={c.claim_id} className="text-[11px] text-danger line-through">{c.text}</p>)}
        </div>
      ) : open ? (
        <pre className="mt-1.5 max-h-60 overflow-auto rounded border border-border bg-black/10 p-2 text-[10px] text-text-muted">{JSON.stringify(d, null, 2)}</pre>
      ) : null}
    </li>
  );
};

function title(e: JobEvent): string {
  if (e.to_status) return `${e.from_status ? `${statusInfo(e.from_status as JobStatus).label} → ` : ''}${statusInfo(e.to_status as JobStatus).label}`;
  const names: Record<string, string> = {
    slot_edited: 'Slot edited',
    plan_edited: 'Plan edited',
    issue_resolved: 'Issue resolved',
    export: 'Final document exported',
    llm_call: 'LLM call',
    gap_removed: 'Gap removed from the final document',
    cancel_requested: 'Cancel requested',
  };
  return names[e.event] ?? humanize(e.event);
}

function summary(e: JobEvent): string | null {
  const d = e.detail ?? {};
  switch (e.event) {
    case 'slot_edited':
      return `${d.section} › ${d.slot}: ${d.changed?.length ?? 0} changed, ${d.added?.length ?? 0} added, ${d.removed?.length ?? 0} removed (draft v${d.draft_version})`;
    case 'plan_edited':
      return `${humanize(d.plan ?? 'plan')} v${d.version}${d.changed?.length ? ` · changed ${d.changed.join(', ')}` : ''}`;
    case 'issue_resolved':
      return `${d.issue_id}${d.gate ? ` (${humanize(d.gate)})` : ''}: ${splitNote(d.note).text}`;
    case 'llm_call':
      return `${d.task ?? ''} · ${d.model ?? ''} · ${(d.input_tokens ?? 0) + (d.output_tokens ?? 0)} tokens · ${d.latency_ms ?? '?'} ms · ${d.status ?? ''}`;
    case 'export':
      return `Final v${d.docx_version} · ${d.traceability_rows ?? 0} traceability rows · ${d.accepted_gaps?.length ?? 0} gap(s) removed`;
    case 'gap_removed':
      return `${d.slot_id}: ${splitNote(d.note).text}`;
    default:
      return typeof d.reason === 'string' ? d.reason : e.to_status ? humanize(e.event) : null;
  }
}
