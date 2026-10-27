import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { BookOpen, CheckCircle2, ChevronDown, ChevronRight, Download, FileText, Loader2, Trash2, Upload } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/ToastStack';
import { saveBlob } from '@/lib/api';
import { formatTimeAgo } from '@/lib/format';
import { actorName } from '@/features/migrations/report';
import { translationsApi } from '../api';
import { useLanguageNames, useResourceMutations } from '../hooks';
import { GLOSSARY_STATUS, TEMPLATE_STATUS, groupVersions } from '../status';
import type { GlossaryRecord, LanguageTemplateRecord } from '../types';
import { LanguageLabel, ToneChip } from './parts';

const glossaryPath = (r: GlossaryRecord) => `/translations/resources/glossaries/${encodeURIComponent(r.glossary_id)}?version=${r.version}`;
const templatePath = (r: LanguageTemplateRecord) => `/translations/resources/templates/${encodeURIComponent(r.template_id)}?version=${r.version}`;

/** Versioned records grouped by id: the newest version as the row, older ones folded under it. */
function VersionGroups<T extends { id: number; version: number; updated_at: string }>({
  records,
  idOf,
  row,
  empty,
}: {
  records: T[];
  idOf: (r: T) => string;
  row: (r: T, latest: boolean) => React.ReactNode;
  empty: React.ReactNode;
}) {
  const [open, setOpen] = useState<Set<string>>(new Set());
  const groups = groupVersions(records, idOf);
  if (!groups.length) return <div className="p-8 text-center text-xs text-text-muted">{empty}</div>;
  return (
    <div className="divide-y divide-border">
      {groups.map((group) => {
        const id = idOf(group[0]);
        const expanded = open.has(id);
        return (
          <div key={id}>
            {row(group[0], true)}
            {group.length > 1 && (
              <button
                type="button"
                onClick={() => setOpen((s) => (s.has(id) ? new Set([...s].filter((x) => x !== id)) : new Set([...s, id])))}
                className="flex w-full items-center gap-1 px-4 pb-2 text-[11px] text-text-muted hover:text-text-main"
              >
                {expanded ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
                {group.length - 1} older version{group.length > 2 ? 's' : ''}
              </button>
            )}
            {expanded && <div className="border-t border-dashed border-border bg-black/10">{group.slice(1).map((r) => <React.Fragment key={r.id}>{row(r, false)}</React.Fragment>)}</div>}
          </div>
        );
      })}
    </div>
  );
}

const Meta: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-text-muted">{children}</div>
);

export const GlossaryList: React.FC<{
  records: GlossaryRecord[];
  loading: boolean;
  onNewVersion: (record: GlossaryRecord) => void;
}> = ({ records, loading, onNewVersion }) => {
  const navigate = useNavigate();
  const { success, error } = useToast();
  const names = useLanguageNames();
  const { approveGlossary, deleteGlossary } = useResourceMutations();
  const [deleting, setDeleting] = useState<GlossaryRecord | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);

  const exportAs = async (r: GlossaryRecord, format: 'csv' | 'xlsx') => {
    setExporting(`${r.id}:${format}`);
    try {
      saveBlob(await translationsApi.exportGlossary(r.glossary_id, r.version, format), `${r.glossary_id}_v${r.version}.${format}`);
    } catch (e) {
      error(e instanceof Error ? e.message : String(e), 'Not exported');
    } finally {
      setExporting(null);
    }
  };
  const approve = (r: GlossaryRecord) =>
    approveGlossary.mutate(
      { id: r.glossary_id, version: r.version },
      {
        onSuccess: () => success('Translation jobs of this language can now use it.', `${r.glossary_id} v${r.version} approved`),
        onError: (e) => error(e.message, 'Not approved'),
      },
    );
  const remove = () =>
    deleting &&
    deleteGlossary.mutate(
      { id: deleting.glossary_id, version: deleting.version },
      {
        onSuccess: () => success(`${deleting.glossary_id} v${deleting.version} was deleted.`, 'Glossary deleted'),
        onError: (e) => error(e.message, 'Not deleted'),
        onSettled: () => setDeleting(null),
      },
    );

  if (loading) return <div className="p-6"><Loader2 className="size-4 animate-spin text-text-muted" /></div>;
  return (
    <>
      <VersionGroups
        records={records}
        idOf={(r) => r.glossary_id}
        empty={<><BookOpen className="mx-auto mb-2 size-6" />No glossary yet. Without one, a translation is free: the LLM picks the terms.</>}
        row={(r, latest) => {
          const status = GLOSSARY_STATUS[r.status];
          return (
            <div className="flex flex-wrap items-center gap-3 px-4 py-3">
              <button type="button" onClick={() => navigate(glossaryPath(r))} className="min-w-0 flex-1 text-left">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-text-main hover:text-primary">{r.name}</span>
                  <span className="font-mono text-[11px] text-text-muted">{r.glossary_id} v{r.version}</span>
                  <ToneChip tone={status.tone}>{status.label}</ToneChip>
                </div>
                <Meta>
                  <LanguageLabel code={r.language} name={names(r.language)} />
                  <span>{r.total_entries ?? 0} terms</span>
                  {r.source_filename && <span>from {r.source_filename}</span>}
                  <span>{actorName(r.created_by)} · {formatTimeAgo(r.created_at)}</span>
                  {r.error && <span className="text-danger">{r.error}</span>}
                </Meta>
              </button>
              <div className="flex shrink-0 flex-wrap items-center gap-1.5">
                {r.status === 'in_review' && (
                  <Button size="sm" variant="primary" leftIcon={<CheckCircle2 className="size-3.5" />} isLoading={approveGlossary.isPending && approveGlossary.variables?.version === r.version && approveGlossary.variables.id === r.glossary_id} onClick={() => approve(r)}>
                    Approve
                  </Button>
                )}
                <Button size="sm" variant="ghost" leftIcon={<Download className="size-3.5" />} isLoading={exporting === `${r.id}:xlsx`} onClick={() => exportAs(r, 'xlsx')}>XLSX</Button>
                <Button size="sm" variant="ghost" isLoading={exporting === `${r.id}:csv`} onClick={() => exportAs(r, 'csv')}>CSV</Button>
                {latest && (
                  <Button size="sm" variant="ghost" leftIcon={<Upload className="size-3.5" />} onClick={() => onNewVersion(r)} title="Upload a file as the next version">
                    New version
                  </Button>
                )}
                <button type="button" title="Delete this version" onClick={() => setDeleting(r)} className="grid size-8 place-items-center rounded text-text-muted hover:bg-danger/10 hover:text-danger">
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            </div>
          );
        }}
      />
      <ConfirmDialog
        isOpen={!!deleting}
        title={`Delete ${deleting?.glossary_id} v${deleting?.version}?`}
        message="The version and its file are removed. A version that a translation job used cannot be deleted: the job's history keeps it."
        confirmLabel="Delete"
        isDangerous
        isLoading={deleteGlossary.isPending}
        onConfirm={remove}
        onCancel={() => setDeleting(null)}
      />
    </>
  );
};

export const LanguageTemplateList: React.FC<{
  records: LanguageTemplateRecord[];
  loading: boolean;
  onNewVersion: (record: LanguageTemplateRecord) => void;
}> = ({ records, loading, onNewVersion }) => {
  const navigate = useNavigate();
  const { success, error } = useToast();
  const names = useLanguageNames();
  const { deleteTemplate } = useResourceMutations();
  const [deleting, setDeleting] = useState<LanguageTemplateRecord | null>(null);

  const remove = () =>
    deleting &&
    deleteTemplate.mutate(
      { id: deleting.template_id, version: deleting.version },
      {
        onSuccess: () => success(`${deleting.template_id} v${deleting.version} was deleted.`, 'Language template deleted'),
        onError: (e) => error(e.message, 'Not deleted'),
        onSettled: () => setDeleting(null),
      },
    );

  if (loading) return <div className="p-6"><Loader2 className="size-4 animate-spin text-text-muted" /></div>;
  return (
    <>
      <VersionGroups
        records={records}
        idOf={(r) => r.template_id}
        empty={<><FileText className="mx-auto mb-2 size-6" />No language template yet. Without one, a translation keeps the English first page, header and footer.</>}
        row={(r, latest) => {
          const status = TEMPLATE_STATUS[r.status];
          return (
            <div className="flex flex-wrap items-center gap-3 px-4 py-3">
              <button type="button" onClick={() => navigate(templatePath(r))} className="min-w-0 flex-1 text-left">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-text-main hover:text-primary">{r.name}</span>
                  <span className="font-mono text-[11px] text-text-muted">{r.template_id} v{r.version}</span>
                  <ToneChip tone={status.tone}>{status.label}</ToneChip>
                </div>
                <Meta>
                  <LanguageLabel code={r.language} name={names(r.language)} />
                  {r.source_filename && <span>{r.source_filename}</span>}
                  <span>{actorName(r.created_by)} · {formatTimeAgo(r.created_at)}</span>
                  {r.error && <span className="text-danger">{r.error}</span>}
                </Meta>
              </button>
              <div className="flex shrink-0 items-center gap-1.5">
                <Button size="sm" variant={r.status === 'extracted' ? 'primary' : 'ghost'} onClick={() => navigate(templatePath(r))}>
                  {r.status === 'extracted' ? 'Check and mark ready' : 'Open'}
                </Button>
                {latest && (
                  <Button size="sm" variant="ghost" leftIcon={<Upload className="size-3.5" />} onClick={() => onNewVersion(r)}>New version</Button>
                )}
                <button type="button" title="Delete this version" onClick={() => setDeleting(r)} className="grid size-8 place-items-center rounded text-text-muted hover:bg-danger/10 hover:text-danger">
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            </div>
          );
        }}
      />
      <ConfirmDialog
        isOpen={!!deleting}
        title={`Delete ${deleting?.template_id} v${deleting?.version}?`}
        message="The version and its extracted files are removed. A version that a translation job used cannot be deleted: the job's history keeps it."
        confirmLabel="Delete"
        isDangerous
        isLoading={deleteTemplate.isPending}
        onConfirm={remove}
        onCancel={() => setDeleting(null)}
      />
    </>
  );
};
