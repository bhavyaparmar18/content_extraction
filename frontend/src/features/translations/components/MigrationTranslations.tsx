import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, ArrowRightLeft, Languages, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { formatTimeAgo } from '@/lib/format';
import { useMigrationJobs } from '@/features/migrations/hooks';
import { isExportable } from '@/features/migrations/status';
import { StatusPill } from '@/features/migrations/components/JobHeader';
import type { MigrationJobRow } from '@/features/migrations/types';
import type { SopRecord } from '@/types';
import { getDisplayTitle } from '@/lib/sopDisplay';
import { useLanguageNames, useTranslationJobs } from '../hooks';
import { jobsByMigration } from '../jobs';
import type { TranslationJobRow } from '../types';
import { LanguageLabel, TranslationStatusPill } from './parts';
import { StartTranslationDialog } from './StartTranslationDialog';

type Migration = Pick<MigrationJobRow, 'job_id' | 'status' | 'template_id' | 'template_version'> & { running?: boolean };

const JobLink: React.FC<{ job: TranslationJobRow; compact?: boolean }> = ({ job, compact }) => {
  const navigate = useNavigate();
  const names = useLanguageNames();
  return (
    <button type="button" onClick={() => navigate(`/translations/${job.job_id}`)}
      className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs hover:bg-white/[0.04]">
      <span className="min-w-0 flex-1">
        <LanguageLabel code={job.language} name={names(job.language)} />
        {!compact && <span className="ml-2 font-mono text-[11px] text-text-muted">{job.job_id}</span>}
      </span>
      <TranslationStatusPill status={job.status} running={job.running} />
      {!compact && <span className="w-20 text-right text-[11px] text-text-muted">{formatTimeAgo(job.updated_at)}</span>}
      <ArrowRight className="size-3.5 shrink-0 text-text-muted" />
    </button>
  );
};

/** The migration page's translations: this migration's jobs, and "Translate…" once it has completed. */
export const MigrationTranslations: React.FC<{ migration: Migration; title?: string }> = ({ migration, title }) => {
  const jobs = useTranslationJobs({ migration_job_id: migration.job_id });
  const [starting, setStarting] = useState(false);
  const can = isExportable(migration.status) && !migration.running;
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between font-semibold text-text-main">
        <span className="flex items-center gap-1.5"><Languages className="size-3.5 text-primary" /> Translations</span>
        {can && <Button size="sm" variant="ghost" className="h-6 px-2 text-[11px]" onClick={() => setStarting(true)}>Translate…</Button>}
      </div>
      {jobs.isLoading ? (
        <Loader2 className="size-3.5 animate-spin text-text-muted" />
      ) : jobs.data?.length ? (
        <div className="-mx-2 space-y-0.5">{jobs.data.map((j) => <JobLink key={j.job_id} job={j} compact />)}</div>
      ) : (
        <p className="text-[11px] text-text-muted">{can ? 'None yet.' : 'Available once the migration has completed.'}</p>
      )}
      {starting && <StartTranslationDialog migration={migration} title={title} onClose={() => setStarting(false)} />}
    </div>
  );
};

/** The Translation tab of an SOP's review page: its migrations' translation jobs, and a way to start more. */
export const SopTranslationJobs: React.FC<{ sop?: SopRecord; sopRecordId: number }> = ({ sop, sopRecordId }) => {
  const navigate = useNavigate();
  const migrations = useMigrationJobs();
  const jobs = useTranslationJobs();
  const [starting, setStarting] = useState<MigrationJobRow | null>(null);
  const mine = (migrations.data ?? []).filter((m) => m.sop_record_id === sopRecordId);
  const byMigration = jobsByMigration(jobs.data ?? []);
  const completed = mine.filter((m) => isExportable(m.status));
  const title = sop ? getDisplayTitle(sop) : undefined;

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-5 px-6 py-8">
        <div>
          <h2 className="flex items-center gap-2 text-base font-semibold text-text-main">
            <Languages className="size-4 text-primary" /> Translations of this SOP
          </h2>
          <p className="mt-1 max-w-xl text-xs text-text-muted">
            A translation starts from a completed migration: its final English document is translated into the languages you choose, one job per
            language, then you review, approve and download each.
          </p>
        </div>

        {(migrations.isLoading || jobs.isLoading) && <Loader2 className="size-4 animate-spin text-text-muted" />}
        {!migrations.isLoading && completed.length === 0 && (
          <div className="dashboard-card p-8 text-center text-xs text-text-muted">
            <ArrowRightLeft className="mx-auto mb-2 size-6" />
            Complete a migration of this SOP first.
            <div className="mt-3">
              <Button size="sm" variant="secondary" onClick={() => navigate(`/review/${sopRecordId}?mode=migration`)}>Go to its migrations</Button>
            </div>
          </div>
        )}

        {mine.filter((m) => isExportable(m.status) || byMigration.has(m.job_id)).map((m) => (
          <div key={m.job_id} className="dashboard-card">
            <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
              <button type="button" onClick={() => navigate(`/migrations/${m.job_id}?step=final`)} className="min-w-0 flex-1 text-left">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-text-main">{m.job_id}</span>
                  <StatusPill status={m.status} running={m.running} />
                </div>
                <div className="mt-0.5 text-[11px] text-text-muted">template {m.template_id} v{m.template_version} · {formatTimeAgo(m.updated_at)}</div>
              </button>
              {isExportable(m.status) && (
                <Button size="sm" variant="primary" leftIcon={<Languages className="size-3.5" />} onClick={() => setStarting(m)}>Translate…</Button>
              )}
            </div>
            <div className="p-2">
              {(byMigration.get(m.job_id) ?? []).map((j) => <JobLink key={j.job_id} job={j} />)}
              {!byMigration.has(m.job_id) && <p className="px-2 py-2 text-[11px] text-text-muted">No translation of this migration yet.</p>}
            </div>
          </div>
        ))}
      </div>
      {starting && <StartTranslationDialog migration={starting} title={title} onClose={() => setStarting(null)} />}
    </div>
  );
};
