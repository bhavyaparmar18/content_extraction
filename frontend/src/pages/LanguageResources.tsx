import React, { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { BookOpen, Check, FileText, Minus, Plus } from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/ui/Button';
import { useGlossaries, useLanguages, useLanguageTemplates } from '@/features/translations/hooks';
import { GlossaryList, LanguageTemplateList } from '@/features/translations/components/ResourceLists';
import { GlossaryUploadDialog, LanguageTemplateUploadDialog } from '@/features/translations/components/ResourceUploadDialogs';
import type { GlossaryRecord, LanguageCode, LanguageTemplateRecord } from '@/features/translations/types';

type Tab = 'glossaries' | 'templates';

/**
 * The per-language resources of translation: glossaries (terms a translation must use) and language templates (the
 * first page, headers and footers that replace the English ones). Both are optional on a translation job.
 */
export const LanguageResources: React.FC = () => {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab: Tab = params.get('tab') === 'templates' ? 'templates' : 'glossaries';
  const language = (params.get('language') || undefined) as LanguageCode | undefined;
  const set = (changes: Record<string, string | undefined>) => {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    setParams(next, { replace: true });
  };

  const languages = useLanguages();
  const glossaries = useGlossaries();
  const templates = useLanguageTemplates();
  const [newGlossary, setNewGlossary] = useState<{ base?: GlossaryRecord } | null>(null);
  const [newTemplate, setNewTemplate] = useState<{ base?: LanguageTemplateRecord } | null>(null);

  const shownGlossaries = (glossaries.data ?? []).filter((g) => !language || g.language === language);
  const shownTemplates = (templates.data ?? []).filter((t) => !language || t.language === language);

  return (
    <div className="content-pane space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="page-title">Language resources</h1>
          <p className="page-description max-w-3xl">
            Both are optional, per language. A <span className="text-text-main">glossary</span> makes a translation use its terms; without one the
            translation is free. A <span className="text-text-main">language template</span> gives the translated document its first page, headers and
            footers; without one the English ones are kept.
          </p>
        </div>
        <Button variant="secondary" size="sm" onClick={() => navigate('/translations')}>Translation jobs</Button>
      </div>

      {/* Coverage: what each language has ready */}
      <div className="dashboard-card overflow-x-auto">
        <div className="flex min-w-max divide-x divide-border">
          <CoverageCell active={!language} onClick={() => set({ language: undefined })} title="All languages" />
          {(languages.data ?? []).map((l) => {
            const glossary = (glossaries.data ?? []).some((g) => g.language === l.code && g.status === 'approved');
            const template = (templates.data ?? []).some((t) => t.language === l.code && t.status === 'ready');
            return (
              <CoverageCell
                key={l.code}
                active={language === l.code}
                onClick={() => set({ language: language === l.code ? undefined : l.code })}
                title={l.name}
                code={l.code}
                glossary={glossary}
                template={template}
              />
            );
          })}
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex gap-1">
          {([
            ['glossaries', 'Glossaries', <BookOpen key="g" className="size-3.5" />, shownGlossaries.length],
            ['templates', 'Language templates', <FileText key="t" className="size-3.5" />, shownTemplates.length],
          ] as const).map(([id, label, icon, count]) => (
            <button key={id} type="button" onClick={() => set({ tab: id === 'glossaries' ? undefined : id })}
              className={clsx('filter-chip', tab === id && 'filter-chip-active')}>
              {icon}
              {label}
              <span className="font-semibold">{count}</span>
            </button>
          ))}
        </div>
        {tab === 'glossaries' ? (
          <Button variant="primary" size="sm" leftIcon={<Plus className="size-3.5" />} onClick={() => setNewGlossary({})}>New glossary</Button>
        ) : (
          <Button variant="primary" size="sm" leftIcon={<Plus className="size-3.5" />} onClick={() => setNewTemplate({})}>Upload language template</Button>
        )}
      </div>

      <div className="dashboard-card">
        {tab === 'glossaries' ? (
          <GlossaryList records={shownGlossaries} loading={glossaries.isLoading} onNewVersion={(base) => setNewGlossary({ base })} />
        ) : (
          <LanguageTemplateList records={shownTemplates} loading={templates.isLoading} onNewVersion={(base) => setNewTemplate({ base })} />
        )}
      </div>

      {newGlossary && (
        <GlossaryUploadDialog
          open
          base={newGlossary.base}
          language={language}
          onClose={() => setNewGlossary(null)}
          onCreated={(r) => {
            setNewGlossary(null);
            navigate(`/translations/resources/glossaries/${encodeURIComponent(r.glossary_id)}?version=${r.version}`);
          }}
        />
      )}
      {newTemplate && (
        <LanguageTemplateUploadDialog
          open
          base={newTemplate.base}
          language={language}
          onClose={() => setNewTemplate(null)}
          onCreated={(r) => {
            setNewTemplate(null);
            navigate(`/translations/resources/templates/${encodeURIComponent(r.template_id)}?version=${r.version}`);
          }}
        />
      )}
    </div>
  );
};

const CoverageCell: React.FC<{
  active: boolean;
  onClick: () => void;
  title: string;
  code?: string;
  glossary?: boolean;
  template?: boolean;
}> = ({ active, onClick, title, code, glossary, template }) => (
  <button type="button" onClick={onClick} className={clsx('min-w-[118px] px-3 py-2.5 text-left text-xs transition', active ? 'bg-primary/10' : 'hover:bg-white/[0.03]')}>
    <div className={clsx('font-medium', active ? 'text-primary' : 'text-text-main')}>{title}</div>
    {code ? (
      <div className="mt-1 space-y-0.5 text-[11px] text-text-muted">
        <div className="font-mono">{code}</div>
        <Has ok={!!glossary} label="Glossary" />
        <Has ok={!!template} label="Template" />
      </div>
    ) : (
      <div className="mt-1 text-[11px] text-text-muted">Approved glossary and ready template per language</div>
    )}
  </button>
);

const Has: React.FC<{ ok: boolean; label: string }> = ({ ok, label }) => (
  <div className={clsx('flex items-center gap-1', ok ? 'text-primary' : 'text-text-muted/70')}>
    {ok ? <Check className="size-3" /> : <Minus className="size-3" />}
    {label}
  </div>
);
