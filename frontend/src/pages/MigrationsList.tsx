import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowRightLeft, Loader2 } from 'lucide-react';
import { clsx } from 'clsx';
import { api } from '@/lib/api';
import { formatTimeAgo } from '@/lib/format';
import { getDisplayTitle } from '@/lib/sopDisplay';
import { useMigrationJobs } from '@/features/migrations/hooks';
import { isTerminal, isWorking, statusInfo } from '@/features/migrations/status';
import { StatusPill } from '@/features/migrations/components/JobHeader';
import type { MigrationJobRow } from '@/features/migrations/types';

type Filter = 'all' | 'review' | 'working' | 'done';

const FILTERS: { id: Filter; label: string; test: (j: MigrationJobRow) => boolean }[] = [
  { id: 'all', label: 'All', test: () => true },
  { id: 'review', label: 'Needs review', test: (j) => !j.running && statusInfo(j.status).tone === 'review' },
  { id: 'working', label: 'Running', test: (j) => isWorking(j) },
  { id: 'done', label: 'Finished', test: (j) => isTerminal(j.status) },
];

/** Every v2 migration job, newest first. */
export const MigrationsList: React.FC = () => {
  const navigate = useNavigate();
  const jobs = useMigrationJobs();
  const sops = useQuery({ queryKey: ['sops'], queryFn: () => api.getSops() });
  const [filter, setFilter] = useState<Filter>('all');
  const sopById = useMemo(() => new Map((sops.data ?? []).map((s) => [s.id, s])), [sops.data]);
  const rows = (jobs.data ?? []).filter(FILTERS.find((f) => f.id === filter)!.test);

  return (
    <div className="content-pane space-y-5">
      <div>
        <h1 className="page-title">Migrations</h1>
        <p className="page-description">SOPs being moved onto a new template. Open one to review its mapping, its draft and the final document.</p>
      </div>

      <div className="flex flex-wrap gap-2">
        {FILTERS.map((f) => (
          <button key={f.id} type="button" onClick={() => setFilter(f.id)} className={clsx('filter-chip', filter === f.id && 'filter-chip-active')}>
            {f.label}
            <span className="font-semibold">{(jobs.data ?? []).filter(f.test).length}</span>
          </button>
        ))}
      </div>

      <div className="dashboard-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr>
                <th className="table-header-cell min-w-[260px]">SOP</th>
                <th className="table-header-cell">TEMPLATE</th>
                <th className="table-header-cell">GWP</th>
                <th className="table-header-cell">STATUS</th>
                <th className="table-header-cell">UPDATED</th>
              </tr>
            </thead>
            <tbody>
              {jobs.isLoading && (
                <tr><td colSpan={5} className="table-cell"><Loader2 className="size-4 animate-spin" /></td></tr>
              )}
              {!jobs.isLoading && rows.length === 0 && (
                <tr>
                  <td colSpan={5} className="table-cell py-10 text-center">
                    <ArrowRightLeft className="mx-auto mb-2 size-6 text-text-muted" />
                    No migration here yet. Start one from the SOP Repository ("Migrate…" in a row's menu).
                  </td>
                </tr>
              )}
              {rows.map((j) => {
                const sop = sopById.get(j.sop_record_id);
                return (
                  <tr key={j.job_id} className="table-row cursor-pointer" onClick={() => navigate(`/migrations/${j.job_id}`)}>
                    <td className="table-cell">
                      <div className="font-medium text-text-main">{sop ? getDisplayTitle(sop) : `SOP #${j.sop_record_id}`}</div>
                      <div className="font-mono text-[11px]">{j.job_id}</div>
                    </td>
                    <td className="table-cell">{j.template_id} v{j.template_version}</td>
                    <td className="table-cell">{j.gwp_id ? `${j.gwp_id} v${j.gwp_version}` : '—'}</td>
                    <td className="table-cell"><StatusPill status={j.status} running={j.running} /></td>
                    <td className="table-cell whitespace-nowrap">{formatTimeAgo(j.updated_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
