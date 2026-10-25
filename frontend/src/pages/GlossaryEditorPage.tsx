import React, { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AlertCircle, ArrowLeft, CheckCircle2, Download, Loader2, Plus, Save, Search, Trash2 } from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/ToastStack';
import { apiErrorDetails, saveBlob } from '@/lib/api';
import { formatTimeAgo } from '@/lib/format';
import { actorName } from '@/features/migrations/report';
import { translationsApi } from '@/features/translations/api';
import { emptyRow, rowProblems, rowsChanged, toEntries, toRows, type TermRow } from '@/features/translations/glossaryEdit';
import { translationKeys, useGlossaries, useGlossaryEntries, useLanguageNames, useResourceMutations } from '@/features/translations/hooks';
import { GLOSSARY_STATUS } from '@/features/translations/status';
import { ErrorPanel, LanguageLabel, ToneChip } from '@/features/translations/components/parts';
import type { Glossary, GlossaryRecord } from '@/features/translations/types';

/** One glossary version: its terms in an editable table. An approved version is never changed: saving makes the next. */
export const GlossaryEditorPage: React.FC = () => {
  const { glossaryId = '' } = useParams<{ glossaryId: string }>();
  const [params] = useSearchParams();
  const asked = params.get('version') ? Number(params.get('version')) : undefined;
  const record = useQuery({
    queryKey: [...translationKeys.glossaries({ glossary_id: glossaryId }), 'record', asked],
    queryFn: () => translationsApi.glossary(glossaryId, asked),
  });
  const entries = useGlossaryEntries(glossaryId, record.data?.version);

  if (record.isLoading || entries.isLoading) {
    return <div className="grid h-full place-items-center text-sm text-text-muted"><Loader2 className="size-4 animate-spin" /></div>;
  }
  if (record.error || !record.data || entries.error || !entries.data) {
    return (
      <div className="content-pane">
        <div className="error-panel flex items-start gap-2 text-sm">
          <AlertCircle className="mt-0.5 size-4 text-danger" />
          <div>
            <div className="font-medium text-text-main">This glossary could not be loaded</div>
            <div className="text-xs text-text-muted">{(record.error ?? entries.error)?.message}</div>
          </div>
        </div>
      </div>
    );
  }
  // A new key per version (and per reload of it) starts the editor again from the saved terms.
  return <Editor key={`${record.data.id}:${entries.dataUpdatedAt}`} record={record.data} glossary={entries.data} />;
};

const Editor: React.FC<{ record: GlossaryRecord; glossary: Glossary }> = ({ record, glossary }) => {
  const navigate = useNavigate();
  const { success, error } = useToast();
  const names = useLanguageNames();
  const versions = useGlossaries({ glossary_id: record.glossary_id });
  const { saveGlossary, approveGlossary } = useResourceMutations();
  const [rows, setRows] = useState<TermRow[]>(() => toRows(glossary.entries));
  const [name, setName] = useState(glossary.name);
  const [notes, setNotes] = useState(glossary.style_notes ?? '');
  const [search, setSearch] = useState('');

  const problems = useMemo(() => rowProblems(rows), [rows]);
  const dirty = rowsChanged(rows, glossary.entries) || name.trim() !== glossary.name || notes.trim() !== (glossary.style_notes ?? '').trim();
  const approved = record.status === 'approved';
  const status = GLOSSARY_STATUS[record.status];
  const needle = search.trim().toLocaleLowerCase();
  const shown = needle
    ? rows.filter((r) => `${r.source_term}\u0000${r.target_term}\u0000${r.note}`.toLocaleLowerCase().includes(needle))
    : rows;

  useEffect(() => {
    if (!dirty) return undefined;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [dirty]);

  const leave = (to: string) => {
    if (!dirty || window.confirm('Leave without saving your changes to this glossary?')) navigate(to);
  };
  const update = (key: number, change: Partial<TermRow>) => setRows((rs) => rs.map((r) => (r.key === key ? { ...r, ...change } : r)));

  const save = () =>
    saveGlossary.mutate(
      { id: record.glossary_id, version: record.version, entries: toEntries(rows), style_notes: notes.trim() || null, name: name.trim() },
      {
        onSuccess: (saved) => {
          if (saved.version !== record.version) {
            success(`v${record.version} stays approved; approve v${saved.version} to use the changes.`, `Saved as v${saved.version}`);
            navigate(`/translations/resources/glossaries/${encodeURIComponent(saved.glossary_id)}?version=${saved.version}`, { replace: true });
          } else {
            success(`${saved.total_entries ?? 0} terms.`, 'Glossary saved');
          }
        },
      },
    );
  const approve = () =>
    approveGlossary.mutate(
      { id: record.glossary_id, version: record.version },
      {
        onSuccess: () => success('Translation jobs of this language can now use it.', `v${record.version} approved`),
        onError: (e) => error(e.message, 'Not approved'),
      },
    );
  const exportAs = async (format: 'csv' | 'xlsx') => {
    try {
      saveBlob(await translationsApi.exportGlossary(record.glossary_id, record.version, format), `${record.glossary_id}_v${record.version}.${format}`);
    } catch (e) {
      error(e instanceof Error ? e.message : String(e), 'Not exported');
    }
  };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <header className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-b border-border bg-card/60 px-4 py-2.5">
        <button type="button" onClick={() => leave('/translations/resources')} title="Language resources"
          className="grid size-8 place-items-center rounded-md text-text-muted hover:bg-white/5 hover:text-text-main">
          <ArrowLeft className="size-4" />
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <input value={name} onChange={(e) => setName(e.target.value)} aria-label="Glossary name" size={Math.max(8, name.length + 1)}
              className="min-w-0 rounded border border-transparent bg-transparent px-1 text-[15px] font-semibold text-text-main hover:border-border focus:border-primary/50 focus:outline-none" />
            <ToneChip tone={status.tone}>{status.label}</ToneChip>
            {dirty && <ToneChip tone="warning">Unsaved changes</ToneChip>}
          </div>
          <div className="mt-0.5 flex flex-wrap items-center gap-x-3 text-[11px] text-text-muted">
            <span className="font-mono">{record.glossary_id}</span>
            <select value={record.version} aria-label="Version" className="rounded border border-border bg-transparent px-1 py-0 text-[11px]"
              onChange={(e) => leave(`/translations/resources/glossaries/${encodeURIComponent(record.glossary_id)}?version=${e.target.value}`)}>
              {(versions.data ?? [record]).map((v) => <option key={v.id} value={v.version}>v{v.version} · {GLOSSARY_STATUS[v.status].label}</option>)}
            </select>
            <LanguageLabel code={record.language} name={names(record.language)} />
            <span>{actorName(record.created_by)} · updated {formatTimeAgo(record.updated_at)}</span>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="ghost" leftIcon={<Download className="size-3.5" />} onClick={() => exportAs('xlsx')}>XLSX</Button>
          <Button size="sm" variant="ghost" onClick={() => exportAs('csv')}>CSV</Button>
          {record.status === 'in_review' && (
            <Button size="sm" variant="secondary" leftIcon={<CheckCircle2 className="size-3.5" />} disabled={dirty} title={dirty ? 'Save first' : undefined}
              isLoading={approveGlossary.isPending} onClick={approve}>
              Approve
            </Button>
          )}
          <Button size="sm" variant="primary" leftIcon={<Save className="size-3.5" />} disabled={!dirty || problems.size > 0} isLoading={saveGlossary.isPending} onClick={save}>
            {approved ? 'Save as new version' : 'Save'}
          </Button>
        </div>
      </header>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-6xl space-y-4 px-6 py-5">
          {approved && (
            <p className="rounded-md border border-primary/25 bg-primary/[0.05] px-3 py-2 text-xs text-text-muted">
              This version is approved and never changes: jobs that used it keep it. Saving your edits makes v{(versions.data?.[0]?.version ?? record.version) + 1}, in review until approved.
            </p>
          )}
          <ErrorPanel error={saveGlossary.error} details={apiErrorDetails(saveGlossary.error)} />

          <div>
            <label className="field-label" htmlFor="style-notes">Style notes</label>
            <textarea id="style-notes" className="field min-h-[60px]" value={notes} onChange={(e) => setNotes(e.target.value)}
              placeholder="Optional. Passed to the translator as written, e.g. “Use the formal Sie form.”" />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-text-muted" />
              <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search terms…" className="field h-8 w-64 pl-8 text-xs" />
            </div>
            <div className="flex items-center gap-3 text-xs text-text-muted">
              <span>{toEntries(rows).length} terms{needle ? ` · ${shown.length} shown` : ''}</span>
              {problems.size > 0 && <span className="text-danger">{problems.size} row{problems.size > 1 ? 's' : ''} to fix</span>}
              <Button size="sm" variant="secondary" leftIcon={<Plus className="size-3.5" />} onClick={() => { setSearch(''); setRows((rs) => [...rs, emptyRow()]); }}>
                Add term
              </Button>
            </div>
          </div>

          <div className="dashboard-card overflow-x-auto">
            <table className="w-full border-collapse text-left text-xs">
              <thead>
                <tr>
                  <th className="table-header-cell w-[28%]">ENGLISH TERM</th>
                  <th className="table-header-cell w-[28%]">TRANSLATION</th>
                  <th className="table-header-cell">NOTE</th>
                  <th className="table-header-cell w-20 text-center" title="Match the English term only with this exact case">CASE</th>
                  <th className="table-header-cell w-24 text-center" title="Keep the English term as it is (a name, a product)">KEEP ENGLISH</th>
                  <th className="table-header-cell w-10" />
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {shown.length === 0 && (
                  <tr><td colSpan={6} className="table-cell py-8 text-center text-text-muted">{needle ? 'No term matches.' : 'No term yet: add one, or upload a file as a new version.'}</td></tr>
                )}
                {shown.map((row) => {
                  const rowIssues = problems.get(row.key);
                  return (
                    <React.Fragment key={row.key}>
                      <tr className={clsx(rowIssues && 'bg-danger/[0.04]')}>
                        <td className="px-2 py-1.5">
                          <input className="field h-8 text-xs" value={row.source_term} onChange={(e) => update(row.key, { source_term: e.target.value })} aria-label="English term" />
                        </td>
                        <td className="px-2 py-1.5">
                          <input className="field h-8 text-xs disabled:opacity-60" value={row.do_not_translate ? row.source_term : row.target_term} disabled={row.do_not_translate}
                            onChange={(e) => update(row.key, { target_term: e.target.value })} aria-label="Translation" />
                        </td>
                        <td className="px-2 py-1.5">
                          <input className="field h-8 text-xs" value={row.note} onChange={(e) => update(row.key, { note: e.target.value })} aria-label="Note" />
                        </td>
                        <td className="px-2 py-1.5 text-center">
                          <input type="checkbox" checked={row.case_sensitive} onChange={(e) => update(row.key, { case_sensitive: e.target.checked })} aria-label="Case-sensitive" />
                        </td>
                        <td className="px-2 py-1.5 text-center">
                          <input type="checkbox" checked={row.do_not_translate} onChange={(e) => update(row.key, { do_not_translate: e.target.checked })} aria-label="Do not translate" />
                        </td>
                        <td className="px-2 py-1.5">
                          <button type="button" title="Remove this term" onClick={() => setRows((rs) => rs.filter((r) => r.key !== row.key))}
                            className="grid size-7 place-items-center rounded text-text-muted hover:bg-danger/10 hover:text-danger">
                            <Trash2 className="size-3.5" />
                          </button>
                        </td>
                      </tr>
                      {rowIssues && (
                        <tr className="bg-danger/[0.04]"><td colSpan={6} className="px-3 pb-2 text-[11px] text-danger">{rowIssues.join(' · ')}</td></tr>
                      )}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-text-muted">
            With a glossary, a translation must use each translation exactly where the English term occurs (whole words, plurals included); the
            checks flag a missed one for the reviewer. "Keep English" terms must appear unchanged.
          </p>
        </div>
      </div>
    </div>
  );
};
