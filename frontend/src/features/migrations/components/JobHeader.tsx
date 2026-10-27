import React, { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, ChevronDown, Download, FileSpreadsheet, FileText, Languages, Loader2, RotateCcw, Square } from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/ToastStack';
import { getDisplayTitle } from '@/lib/sopDisplay';
import type { SopRecord } from '@/types';
import { useJobMutations } from '../hooks';
import { useDownloads } from '../useDownloads';
import { isExportable, permissions, statusInfo } from '../status';
import type { JobStatus, MigrationJob } from '../types';
import { StartTranslationDialog } from '@/features/translations/components/StartTranslationDialog';

export const StatusPill: React.FC<{ status: JobStatus; running?: boolean; className?: string }> = ({ status, running, className }) => {
  const info = statusInfo(status);
  return (
    <span className={clsx('inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[11px] font-medium', info.classes, className)}>
      {running || info.tone === 'working' ? <Loader2 className="size-3 animate-spin" /> : <span className="size-1.5 rounded-full bg-current" />}
      {info.label}
    </span>
  );
};

export const JobHeader: React.FC<{ job: MigrationJob; sop?: SopRecord }> = ({ job, sop }) => {
  const navigate = useNavigate();
  const { success, error } = useToast();
  const mutations = useJobMutations(job.job_id);
  const can = permissions(job);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [translating, setTranslating] = useState(false);

  const cancel = () =>
    mutations.cancel.mutate(undefined, {
      onSuccess: () => success(job.running ? 'The job stops after its current stage.' : 'The job was cancelled.', 'Cancel'),
      onError: (e) => error(e.message, 'Could not cancel'),
      onSettled: () => setConfirmCancel(false),
    });
  const retry = () =>
    mutations.retry.mutate(undefined, {
      onSuccess: () => success('The job runs again from the stage that stopped.', 'Retry'),
      onError: (e) => error(e.message, 'Could not retry'),
    });

  return (
    <header className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-border bg-card/60 px-4 py-2.5">
      <button
        type="button"
        onClick={() => navigate('/migrations')}
        className="grid size-8 place-items-center rounded-md text-text-muted hover:bg-white/5 hover:text-text-main"
        title="All migrations"
      >
        <ArrowLeft className="size-4" />
      </button>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <h1 className="truncate text-[15px] font-semibold text-text-main">{sop ? getDisplayTitle(sop) : `SOP #${job.sop_record_id}`}</h1>
          <StatusPill status={job.status} running={job.running} />
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-text-muted">
          <span className="font-mono">{job.job_id}</span>
          <span>
            Template <span className="text-text-main">{job.template_id}</span> v{job.template_version}
          </span>
          <span>
            {job.gwp_id ? (
              <>
                GWP <span className="text-text-main">{job.gwp_id}</span> v{job.gwp_version}
              </>
            ) : (
              'No GWP (content placed as written)'
            )}
          </span>
          <span>{job.mode === 'review' ? 'Review mode' : 'Auto mode'}</span>
        </div>
        {job.error && <div className="mt-1 text-[11px] text-danger">{job.error}</div>}
      </div>
      <div className="flex items-center gap-2">
        {can.retry && (
          <Button size="sm" variant="secondary" leftIcon={<RotateCcw className="size-3.5" />} onClick={retry} isLoading={mutations.retry.isPending}>
            Retry
          </Button>
        )}
        {can.cancel && (
          <Button size="sm" variant="ghost" leftIcon={<Square className="size-3.5" />} onClick={() => setConfirmCancel(true)}>
            Cancel job
          </Button>
        )}
        {can.export && (
          <Button size="sm" variant="secondary" leftIcon={<Languages className="size-3.5" />} onClick={() => setTranslating(true)}>
            Translate…
          </Button>
        )}
        <DownloadMenu job={job} />
      </div>
      {translating && <StartTranslationDialog migration={job} title={sop ? getDisplayTitle(sop) : undefined} onClose={() => setTranslating(false)} />}
      <ConfirmDialog
        isOpen={confirmCancel}
        title="Cancel this migration?"
        message="The job stops and cannot continue from here; you can retry it later. Drafts and plans made so far are kept."
        confirmLabel="Cancel job"
        cancelLabel="Keep running"
        isDangerous
        isLoading={mutations.cancel.isPending}
        onConfirm={cancel}
        onCancel={() => setConfirmCancel(false)}
      />
    </header>
  );
};

/** Review draft, final document and traceability, each fetched with the reviewer's token. */
export const DownloadMenu: React.FC<{ job: MigrationJob; align?: 'left' | 'right' }> = ({ job, align = 'right' }) => {
  const [open, setOpen] = useState(false);
  const download = useDownloads(job);
  const ref = useRef<HTMLDivElement>(null);
  const hasReview = job.artifacts.some((a) => a.kind === 'docx' && !a.scope);
  const hasDrafts = job.artifacts.some((a) => a.kind === 'section_draft');

  useEffect(() => {
    if (!open) return undefined;
    const close = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false);
    window.addEventListener('mousedown', close);
    return () => window.removeEventListener('mousedown', close);
  }, [open]);

  const item = (label: string, hint: string, icon: React.ReactNode, enabled: boolean, run: () => void) => (
    <button
      type="button"
      disabled={!enabled || !!download.busy}
      onClick={() => {
        setOpen(false);
        run();
      }}
      className="flex w-full items-start gap-2.5 rounded-md px-2.5 py-2 text-left hover:bg-white/5 disabled:cursor-not-allowed disabled:opacity-40"
    >
      <span className="mt-0.5 text-text-muted">{icon}</span>
      <span>
        <span className="block text-xs font-medium text-text-main">{label}</span>
        <span className="block text-[11px] text-text-muted">{hint}</span>
      </span>
    </button>
  );

  return (
    <div ref={ref} className="relative">
      <Button
        size="sm"
        variant="primary"
        leftIcon={download.busy ? <Loader2 className="size-3.5 animate-spin" /> : <Download className="size-3.5" />}
        rightIcon={<ChevronDown className="size-3.5" />}
        onClick={() => setOpen((o) => !o)}
      >
        Download
      </Button>
      {open && (
        <div className={clsx('absolute z-40 mt-1.5 w-72 rounded-lg border border-border bg-card p-1.5 shadow-panel', align === 'right' ? 'right-0' : 'left-0')}>
          {item('Final document (.docx)', isExportable(job.status) ? 'Gaps removed, ready to use' : 'Available once the job has completed',
            <FileText className="size-4" />, isExportable(job.status) && !job.running, download.final)}
          {item('Review draft (.docx)', 'Gap markers and content controls kept', <FileText className="size-4" />, hasReview, download.review)}
          {item('Traceability (.csv)', 'Every claim with its source passages', <FileSpreadsheet className="size-4" />, hasDrafts, download.trace)}
        </div>
      )}
    </div>
  );
};
