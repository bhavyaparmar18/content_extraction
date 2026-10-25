import React, { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowLeft, BookOpen, Download, FileText, RotateCcw, Square } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/ToastStack';
import { useLanguageNames, useTranslationMutations } from '../hooks';
import { translationPermissions } from '../status';
import { useTranslationDownload } from '../useTranslationDownload';
import type { TranslationJob } from '../types';
import { TranslationStatusPill } from './parts';

/** The job: SOP and language, what it was started with, and the job-level actions. */
export const TranslationHeader: React.FC<{ job: TranslationJob; sopTitle?: string }> = ({ job, sopTitle }) => {
  const navigate = useNavigate();
  const names = useLanguageNames();
  const { success, error } = useToast();
  const mutations = useTranslationMutations(job.job_id);
  const download = useTranslationDownload(job);
  const can = translationPermissions(job);
  const [confirmCancel, setConfirmCancel] = useState(false);

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
      <button type="button" onClick={() => navigate(`/migrations/${job.migration_job_id}?step=final`)} title="The migration"
        className="grid size-8 place-items-center rounded-md text-text-muted hover:bg-white/5 hover:text-text-main">
        <ArrowLeft className="size-4" />
      </button>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <h1 className="truncate text-[15px] font-semibold text-text-main">
            {sopTitle ?? job.migration_job_id} <span className="text-text-muted">→</span> {names(job.language)}
            <span className="ml-1.5 font-mono text-[11px] font-normal text-text-muted">{job.language}</span>
          </h1>
          <TranslationStatusPill status={job.status} running={job.running} />
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-text-muted">
          <span className="font-mono">{job.job_id}</span>
          <Link to={`/migrations/${job.migration_job_id}?step=final`} className="hover:text-primary">from <span className="font-mono">{job.migration_job_id}</span></Link>
          <span className="flex items-center gap-1">
            <BookOpen className="size-3" />
            {job.glossary_id ? (
              <Link to={`/translations/resources/glossaries/${encodeURIComponent(job.glossary_id)}?version=${job.glossary_version}`} className="text-text-main hover:text-primary">
                {job.glossary_id} v{job.glossary_version}
              </Link>
            ) : 'No glossary: free translation'}
          </span>
          <span className="flex items-center gap-1">
            <FileText className="size-3" />
            {job.language_template_id ? (
              <Link to={`/translations/resources/templates/${encodeURIComponent(job.language_template_id)}?version=${job.language_template_version}`} className="text-text-main hover:text-primary">
                {job.language_template_id} v{job.language_template_version}
              </Link>
            ) : 'English first page, header and footer kept'}
          </span>
        </div>
        {job.error && <div className="mt-1 text-[11px] text-danger">{job.error}</div>}
      </div>
      <div className="flex items-center gap-2">
        {can.retry && (
          <Button size="sm" variant="secondary" leftIcon={<RotateCcw className="size-3.5" />} onClick={retry} isLoading={mutations.retry.isPending}>Retry</Button>
        )}
        {can.cancel && (
          <Button size="sm" variant="ghost" leftIcon={<Square className="size-3.5" />} onClick={() => setConfirmCancel(true)}>Cancel job</Button>
        )}
        <Button size="sm" variant="primary" leftIcon={<Download className="size-3.5" />} disabled={!can.download} isLoading={download.busy}
          title={can.download ? 'The approved document; the download is recorded' : 'Available once approved'} onClick={download.run}>
          Download
        </Button>
      </div>
      <ConfirmDialog
        isOpen={confirmCancel}
        title="Cancel this translation?"
        message="The job stops and cannot continue from here; you can retry it later. Translations and edits made so far are kept."
        confirmLabel="Cancel job"
        cancelLabel="Keep it"
        isDangerous
        isLoading={mutations.cancel.isPending}
        onConfirm={cancel}
        onCancel={() => setConfirmCancel(false)}
      />
    </header>
  );
};
