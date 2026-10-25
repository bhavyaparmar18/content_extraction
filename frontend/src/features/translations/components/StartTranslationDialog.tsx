import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { BookOpen, FileText, Languages } from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/ToastStack';
import { apiErrorDetails } from '@/lib/api';
import type { MigrationJobRow } from '@/features/migrations/types';
import { translationsApi } from '../api';
import { defaultPicks, languageChoice, pickOf, usableGlossaries, usableTemplates, type ResourcePick } from '../jobs';
import { translationKeys, useGlossaries, useLanguages, useLanguageTemplates, useTranslationJobs } from '../hooks';
import { translationStatusInfo } from '../status';
import type { LanguageCode } from '../types';
import { ErrorPanel, Modal } from './parts';

type Migration = Pick<MigrationJobRow, 'job_id' | 'status' | 'template_id' | 'template_version'>;
type Picks = { glossary: ResourcePick; template: ResourcePick };

/**
 * Start translations of a completed migration: one job per checked language, each with an optional glossary
 * (approved versions) and an optional language template (ready versions).
 */
export const StartTranslationDialog: React.FC<{ migration: Migration; title?: string; onClose: () => void }> = ({ migration, title, onClose }) => {
  const navigate = useNavigate();
  const client = useQueryClient();
  const { success } = useToast();
  const languages = useLanguages();
  const glossaries = useGlossaries({ status: 'approved' });
  const templates = useLanguageTemplates({ status: 'ready' });
  const existing = useTranslationJobs({ migration_job_id: migration.job_id });
  const [picked, setPicked] = useState<Map<LanguageCode, Picks>>(new Map());
  const resourcesLoaded = !glossaries.isLoading && !templates.isLoading;

  const toggle = (code: LanguageCode) =>
    setPicked((m) => {
      const next = new Map(m);
      if (next.has(code)) next.delete(code);
      else next.set(code, defaultPicks(code, glossaries.data ?? [], templates.data ?? []));
      return next;
    });
  const choose = (code: LanguageCode, change: Partial<Picks>) => setPicked((m) => new Map(m).set(code, { ...m.get(code)!, ...change }));

  const create = useMutation({
    mutationFn: () =>
      translationsApi.create({
        migration_job_id: migration.job_id,
        languages: (languages.data ?? []).filter((l) => picked.has(l.code)).map((l) => languageChoice(l.code, picked.get(l.code)!)),
      }),
    onSuccess: (jobs) => {
      client.invalidateQueries({ queryKey: translationKeys.lists() });
      onClose();
      if (jobs.length === 1) {
        success('Preparing the English document; the translation follows.', 'Translation started');
        navigate(`/translations/${jobs[0].job_id}`);
      } else {
        success(jobs.map((j) => `${j.language}: ${j.job_id}`).join(' · '), `${jobs.length} translations started`);
      }
    },
  });

  return (
    <Modal
      open
      wide
      onClose={onClose}
      icon={<Languages className="size-4 text-primary" />}
      title="Translate the migrated SOP"
      footer={
        <>
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button variant="primary" size="sm" leftIcon={<Languages className="size-3.5" />} disabled={!picked.size} isLoading={create.isPending} onClick={() => create.mutate()}>
            {picked.size > 1 ? `Start ${picked.size} translations` : 'Start translation'}
          </Button>
        </>
      }
    >
      <div className="rounded-md border border-border bg-black/10 px-3 py-2 text-xs">
        {title && <div className="font-medium text-text-main">{title}</div>}
        <div className="text-text-muted">
          <span className="font-mono">{migration.job_id}</span> · template {migration.template_id} v{migration.template_version}
        </div>
      </div>
      <p className="text-[11px] text-text-muted">
        Each language becomes its own job: the final English document is translated, checked, rendered, and waits for your review and approval.
      </p>

      <div className="space-y-2">
        {(languages.data ?? []).map((l) => {
          const on = picked.get(l.code);
          const jobs = (existing.data ?? []).filter((j) => j.language === l.code);
          const glossaryOptions = usableGlossaries(glossaries.data ?? [], l.code);
          const templateOptions = usableTemplates(templates.data ?? [], l.code);
          return (
            <div key={l.code} className={clsx('rounded-md border px-3 py-2', on ? 'border-primary/50 bg-primary/[0.05]' : 'border-border')}>
              <label className="flex cursor-pointer items-center gap-2.5 text-xs">
                <input type="checkbox" checked={!!on} disabled={!resourcesLoaded} onChange={() => toggle(l.code)} />
                <span className="font-medium text-text-main">{l.name}</span>
                <span className="font-mono text-[11px] text-text-muted">{l.code}</span>
                {jobs.length > 0 && (
                  <span className="ml-auto truncate text-[11px] text-text-muted" title="A new job is still possible">
                    already: {jobs.slice(0, 2).map((j) => `${translationStatusInfo(j.status).label} (${j.job_id})`).join(', ')}
                    {jobs.length > 2 ? ` +${jobs.length - 2}` : ''}
                  </span>
                )}
              </label>
              {on && (
                <div className="mt-2 grid gap-2 pl-6 sm:grid-cols-2">
                  <div>
                    <label className="mb-0.5 flex items-center gap-1 text-[11px] font-medium text-text-muted"><BookOpen className="size-3" /> Glossary</label>
                    <select className="field h-8 py-0 text-xs" value={on.glossary} onChange={(e) => choose(l.code, { glossary: e.target.value })} aria-label={`${l.name} glossary`}>
                      <option value="">None (free translation)</option>
                      {glossaryOptions.map((g) => <option key={g.id} value={pickOf(g.glossary_id, g.version)}>{g.name} v{g.version} ({g.total_entries ?? 0} terms)</option>)}
                    </select>
                    <p className="mt-0.5 text-[10px] text-text-muted">{on.glossary ? 'Its terms are mandatory and checked.' : glossaryOptions.length ? 'The LLM picks the terms.' : 'No approved glossary for this language.'}</p>
                  </div>
                  <div>
                    <label className="mb-0.5 flex items-center gap-1 text-[11px] font-medium text-text-muted"><FileText className="size-3" /> First page, headers, footers</label>
                    <select className="field h-8 py-0 text-xs" value={on.template} onChange={(e) => choose(l.code, { template: e.target.value })} aria-label={`${l.name} language template`}>
                      <option value="">None (keep English first page, header and footer)</option>
                      {templateOptions.map((t) => <option key={t.id} value={pickOf(t.template_id, t.version)}>{t.name} v{t.version}</option>)}
                    </select>
                    <p className="mt-0.5 text-[10px] text-text-muted">{on.template ? "The language template's, unchanged." : templateOptions.length ? 'The English ones stay.' : 'No ready language template for this language.'}</p>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
      <ErrorPanel error={create.error} details={apiErrorDetails(create.error)} />
    </Modal>
  );
};
