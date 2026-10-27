import React, { useEffect, useRef, useState } from 'react';
import { AlertOctagon, CheckCircle2, ChevronDown, Loader2, RefreshCw, ShieldCheck } from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/ToastStack';
import { apiErrorDetails } from '@/lib/api';
import { SEVERITY_ORDER } from '@/features/migrations/status';
import { openIssues } from '@/features/migrations/report';
import { useTranslationMutations } from '../hooks';
import { translationPermissions } from '../status';
import type { QualityReport, TranslationJob } from '../types';
import { ErrorPanel, Modal } from './parts';

/** The review's state, above the work: is the document current, what blocks the approval, and the approval itself. */
export const ReviewBar: React.FC<{
  job: TranslationJob;
  report?: QualityReport;
  onSelectIssue?: (issueId: string) => void;
  onApproved?: () => void;
}> = ({ job, report, onSelectIssue, onApproved }) => {
  const { success, error } = useToast();
  const mutations = useTranslationMutations(job.job_id);
  const can = translationPermissions(job);
  const [approving, setApproving] = useState(false);
  const rendering = job.status === 'RENDERING' || (job.running && job.status === 'REVIEW_PENDING');
  const review = job.review;
  const blockers = review?.blockers ?? [];

  if (job.status === 'APPROVED') {
    return (
      <div className="flex shrink-0 items-center gap-2 border-b border-primary/25 bg-primary/[0.06] px-4 py-1.5 text-xs text-text-main">
        <ShieldCheck className="size-4 text-primary" />
        Approved{job.approved_at ? ` on ${new Date(job.approved_at).toLocaleString()}` : ''}. The approved document is final: a change needs a new translation job.
      </div>
    );
  }
  if (job.status !== 'REVIEW_PENDING' && job.status !== 'RENDERING') return null;

  const render = () =>
    mutations.render.mutate(undefined, {
      onSuccess: () => success('The document is rendered again from the latest translations.', 'Updating the document'),
      onError: (e) => error(e.message, 'Not rendered'),
    });

  return (
    <div className="flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1.5 border-b border-border bg-card/40 px-4 py-1.5 text-xs">
      {rendering ? (
        <span className="flex items-center gap-1.5 text-info"><Loader2 className="size-3.5 animate-spin" /> Rendering the document…</span>
      ) : review?.render_current ? (
        <span className="flex items-center gap-1.5 text-text-muted"><CheckCircle2 className="size-3.5 text-primary" /> Document up to date{review.docx_version ? ` (render v${review.docx_version})` : ''}</span>
      ) : (
        <span className="flex items-center gap-2 text-warning">
          <RefreshCw className="size-3.5" /> Edits since the last render are not in the document yet
          <Button size="sm" variant="secondary" className="h-6 px-2 text-[11px]" disabled={!can.render} isLoading={mutations.render.isPending} onClick={render}>
            Update document
          </Button>
        </span>
      )}

      <div className="ml-auto flex items-center gap-2">
        {!rendering && blockers.length > 0 && <Blockers blockers={blockers} onSelectIssue={onSelectIssue} />}
        <Button size="sm" variant="primary" leftIcon={<ShieldCheck className="size-3.5" />} disabled={!can.approve}
          title={can.approve ? 'Approve the current render' : blockers.length ? 'Resolve what blocks the approval first' : undefined}
          onClick={() => setApproving(true)}>
          Approve…
        </Button>
      </div>
      {approving && (
        <ApproveDialog job={job} report={report} onClose={() => setApproving(false)} onApproved={() => { setApproving(false); onApproved?.(); }} />
      )}
    </div>
  );
};

const Blockers: React.FC<{ blockers: NonNullable<TranslationJob['review']>['blockers']; onSelectIssue?: (issueId: string) => void }> = ({ blockers, onSelectIssue }) => {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return undefined;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    window.addEventListener('mousedown', close);
    return () => window.removeEventListener('mousedown', close);
  }, [open]);
  return (
    <div ref={ref} className="relative">
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex items-center gap-1 rounded-md border border-danger/30 bg-danger/[0.06] px-2 py-1 text-[11px] text-danger hover:bg-danger/10">
        <AlertOctagon className="size-3.5" />
        Approval blocked ({blockers.length})
        <ChevronDown className="size-3" />
      </button>
      {open && (
        <div className="absolute right-0 z-40 mt-1.5 max-h-80 w-96 overflow-y-auto rounded-lg border border-border bg-card p-1.5 shadow-panel">
          {blockers.map((b, i) => (
            <button key={`${b.code}-${b.issue_id ?? i}`} type="button" disabled={!b.issue_id || !onSelectIssue}
              onClick={() => { if (b.issue_id) onSelectIssue?.(b.issue_id); setOpen(false); }}
              className={clsx('block w-full rounded-md px-2.5 py-1.5 text-left text-[11px]', b.issue_id && onSelectIssue ? 'hover:bg-white/5' : 'cursor-default')}>
              <span className="font-mono text-danger">{b.code}</span>
              <span className="ml-1.5 text-text-main">{b.message}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

const ApproveDialog: React.FC<{ job: TranslationJob; report?: QualityReport; onClose: () => void; onApproved: () => void }> = ({ job, report, onClose, onApproved }) => {
  const { success } = useToast();
  const { approve } = useTranslationMutations(job.job_id);
  const [note, setNote] = useState('');
  const open = openIssues(report);
  const bySeverity = SEVERITY_ORDER.map((s) => [s, open.filter((i) => i.severity === s).length] as const).filter(([, n]) => n);
  const submit = () =>
    approve.mutate(note.trim() || undefined, {
      onSuccess: () => {
        success('Download it from the Final step or the header.', 'Translation approved');
        onApproved();
      },
    });
  return (
    <Modal
      open
      onClose={onClose}
      icon={<ShieldCheck className="size-4 text-primary" />}
      title="Approve this translation?"
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button variant="primary" size="sm" isLoading={approve.isPending} onClick={submit}>Approve</Button>
        </>
      }
    >
      <p className="text-xs text-text-muted">
        The current render (v{job.review?.docx_version}) becomes the approved document. It is final: a later change needs a new translation job.
      </p>
      {open.length > 0 && (
        <p className="rounded-md border border-warning/25 bg-warning/[0.05] px-3 py-2 text-[11px] text-text-muted">
          {open.length} open issue{open.length > 1 ? 's' : ''} ({bySeverity.map(([s, n]) => `${n} ${s}`).join(', ')}) stay open; they don't block the approval and are recorded with it.
        </p>
      )}
      <div>
        <label className="field-label" htmlFor="approve-note">Note (optional)</label>
        <textarea id="approve-note" className="field min-h-[64px]" value={note} onChange={(e) => setNote(e.target.value)} placeholder="e.g. Reviewed by the German QA team" />
      </div>
      <ErrorPanel error={approve.error} details={apiErrorDetails(approve.error)} />
    </Modal>
  );
};
