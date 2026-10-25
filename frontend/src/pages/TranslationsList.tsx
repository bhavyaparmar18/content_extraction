import React, { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { BookOpen, Languages, Loader2 } from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/ui/Button';
import { api } from '@/lib/api';
import { formatTimeAgo } from '@/lib/format';
import { getDisplayTitle } from '@/lib/sopDisplay';
import { useMigrationJobs } from '@/features/migrations/hooks';
import { useLanguageNames, useLanguages, useTranslationJobs } from '@/features/translations/hooks';
import { isTranslationTerminal, isTranslationWorking } from '@/features/translations/status';
import { jobSopTitles } from '@/features/translations/jobs';
import { LanguageLabel, TranslationStatusPill } from '@/features/translations/components/parts';
import type { LanguageCode, TranslationJobRow } from '@/features/translations/types';

type Filter = 'all' | 'review' | 'working' | 'done';

const FILTERS: { id: Filter; label: string; test: (j: TranslationJobRow) => boolean }[] = [
  { id: 'all', label: 'All', test: () => true },
  { id: 'review', label: 'Needs review', test: (j) => !j.running && j.status === 'REVIEW_PENDING' },
  { id: 'working', label: 'Running', test: (j) => isTranslationWorking(j) },
  { id: 'done', label: 'Finished', test: (j) => isTranslationTerminal(j.status) },
];

/** Every translation job, newest first. */
export const TranslationsList: React.FC = () => {
  const navigate = useNavigate();
  const jobs = useTranslationJobs();
  const migrations = useMigrationJobs();
  const sops = useQuery({ queryKey: ['sops'], queryFn: () => api.getSops() });
  const languages = useLanguages();
  const names = useLanguageNames();
  const [filter, setFilter] = useState<Filter>('all');
  const [language, setLanguage] = useState<LanguageCode | ''>('');
  const titles = useMemo(
    () => jobSopTitles(migrations.data ?? [], new Map((sops.data ?? []).map((s) => [s.id, getDisplayTitle(s)]))),
    [migrations.data, sops.data],
  );
  const all = (jobs.data ?? []).filter((j) => !language || j.language === language);
  const rows = all.filter(FILTERS.find((f) => f.id === filter)!.test);

  return (
    <div className="content-pane space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="page-title">Translations</h1>
          <p className="page-description">
            Completed migrations translated into other languages, one job per language. Open one to review its segments, then approve and download it.
            Start a translation from a completed migration's page.
          </p>
        </div>
        <Button variant="secondary" size="sm" leftIcon={<BookOpen className="size-3.5" />} onClick={() => navigate('/translations/resources')}>
          Language resources
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        {FILTERS.map((f) => (
          <button key={f.id} type="button" onClick={() => setFilter(f.id)} className={clsx('filter-chip', filter === f.id && 'filter-chip-active')}>
            {f.label}
            <span className="font-semibold">{all.filter(f.test).length}</span>
          </button>
        ))}
        <select value={language} onChange={(e) => setLanguage(e.target.value as LanguageCode | '')} className="field h-8 w-48 py-0 text-xs" aria-label="Language">
          <option value="">All languages</option>
          {(languages.data ?? []).map((l) => <option key={l.code} value={l.code}>{l.name} ({l.code})</option>)}
        </select>
      </div>

      <div className="dashboard-card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr>
                <th className="table-header-cell min-w-[240px]">SOP</th>
                <th className="table-header-cell">LANGUAGE</th>
                <th className="table-header-cell">GLOSSARY</th>
                <th className="table-header-cell">FIRST PAGE, HEADERS</th>
                <th className="table-header-cell">STATUS</th>
                <th className="table-header-cell">UPDATED</th>
              </tr>
            </thead>
            <tbody>
              {jobs.isLoading && (
                <tr><td colSpan={6} className="table-cell"><Loader2 className="size-4 animate-spin" /></td></tr>
              )}
              {jobs.error && (
                <tr><td colSpan={6} className="table-cell text-danger">{jobs.error.message}</td></tr>
              )}
              {!jobs.isLoading && !jobs.error && rows.length === 0 && (
                <tr>
                  <td colSpan={6} className="table-cell py-10 text-center">
                    <Languages className="mx-auto mb-2 size-6 text-text-muted" />
                    No translation here yet. Open a completed migration and use "Translate…".
                  </td>
                </tr>
              )}
              {rows.map((j) => (
                <tr key={j.job_id} className="table-row cursor-pointer" onClick={() => navigate(`/translations/${j.job_id}`)}>
                  <td className="table-cell">
                    <div className="font-medium text-text-main">{titles.get(j.migration_job_id) ?? j.migration_job_id}</div>
                    <div className="font-mono text-[11px]">{j.job_id} · {j.migration_job_id}</div>
                  </td>
                  <td className="table-cell"><LanguageLabel code={j.language} name={names(j.language)} /></td>
                  <td className="table-cell">{j.glossary_id ? `${j.glossary_id} v${j.glossary_version}` : <span className="text-text-muted">None (free)</span>}</td>
                  <td className="table-cell">
                    {j.language_template_id ? `${j.language_template_id} v${j.language_template_version}` : <span className="text-text-muted">English kept</span>}
                  </td>
                  <td className="table-cell"><TranslationStatusPill status={j.status} running={j.running} /></td>
                  <td className="table-cell whitespace-nowrap">{formatTimeAgo(j.updated_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
