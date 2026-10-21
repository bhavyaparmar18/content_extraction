import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, ArrowRightLeft, FileText, Layers, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { formatTimeAgo } from '@/lib/format';
import type { SopRecord } from '@/types';
import { useMigrationJobs } from '../hooks';
import { StatusPill } from './JobHeader';
import { StartMigrationDialog } from './StartMigrationDialog';

/** The migration tab of an SOP's review page: its v2 migration jobs and a way to start one. */
export const SopMigrationJobs: React.FC<{ sop?: SopRecord; sopRecordId: number }> = ({ sop, sopRecordId }) => {
  const navigate = useNavigate();
  const jobs = useMigrationJobs();
  const [starting, setStarting] = useState(false);
  const mine = (jobs.data ?? []).filter((j) => j.sop_record_id === sopRecordId);

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-5 px-6 py-8">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-base font-semibold text-text-main">
              <ArrowRightLeft className="size-4 text-primary" /> Migrations of this SOP
            </h2>
            <p className="mt-1 max-w-xl text-xs text-text-muted">
              A migration moves the SOP onto a template: you review which sections and passages go where, read the draft
              next to the original and the template, resolve its issues, then preview and download the final document.
            </p>
          </div>
          <Button variant="primary" size="sm" leftIcon={<ArrowRightLeft className="size-3.5" />} onClick={() => setStarting(true)} disabled={!sop}>
            Start a migration
          </Button>
        </div>

        <div className="dashboard-card divide-y divide-border">
          {jobs.isLoading && <div className="p-4"><Loader2 className="size-4 animate-spin text-text-muted" /></div>}
          {!jobs.isLoading && mine.length === 0 && (
            <div className="p-8 text-center text-xs text-text-muted">No migration yet for this SOP.</div>
          )}
          {mine.map((j) => (
            <button
              key={j.job_id}
              type="button"
              onClick={() => navigate(`/migrations/${j.job_id}`)}
              className="flex w-full items-center gap-4 px-4 py-3 text-left transition hover:bg-white/[0.03]"
            >
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-xs text-text-main">{j.job_id}</span>
                  <StatusPill status={j.status} running={j.running} />
                </div>
                <div className="mt-1 flex flex-wrap gap-x-4 text-[11px] text-text-muted">
                  <span className="flex items-center gap-1"><Layers className="size-3" /> {j.template_id} v{j.template_version}</span>
                  <span className="flex items-center gap-1"><FileText className="size-3" /> {j.gwp_id ? `${j.gwp_id} v${j.gwp_version}` : 'No GWP'}</span>
                  <span>{formatTimeAgo(j.updated_at)}</span>
                </div>
              </div>
              <ArrowRight className="size-4 text-text-muted" />
            </button>
          ))}
        </div>
      </div>
      <StartMigrationDialog sop={starting ? sop ?? null : null} onClose={() => setStarting(false)} />
    </div>
  );
};
