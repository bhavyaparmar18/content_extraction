import React, { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { AlertTriangle, BookOpen, CheckCircle2, Replace, Search } from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/ToastStack';
import { apiErrorCode, apiErrorDetails } from '@/lib/api';
import { IssueRow } from '@/features/migrations/components/issues';
import { JustifyDialog } from '@/features/migrations/components/JustifyDialog';
import { sortIssues } from '@/features/migrations/report';
import { translationsApi } from '../api';
import { useJobGlossary, useJobTerms, useTranslationMutations } from '../hooks';
import type { GlossaryEntry, QualityReport, ReplacePreview, ReplaceResult, Segment, TranslationJob, ValidationIssue } from '../types';
import { ErrorPanel } from './parts';

// ── Issues ────────────────────────────────────────────────────────────

type IssueFilter = 'blocking' | 'open' | 'resolved';

const blocks = (i: ValidationIssue) => !!i.gate || i.severity === 'critical';

/** The QA checks: what blocks the approval first, then the rest; each resolvable with a note. */
export const TranslationIssuePanel: React.FC<{
  jobId: string;
  report?: QualityReport;
  canResolve: boolean;
  scope: string;
  scopeOf: Map<string, string>;
  headingOf: (scope: string) => string;
  active?: string | null;
  onSelect: (issue: ValidationIssue) => void;
}> = ({ jobId, report, canResolve, scope, scopeOf, headingOf, active, onSelect }) => {
  const { success, error } = useToast();
  const { resolveIssue } = useTranslationMutations(jobId);
  const issues = report?.issues ?? [];
  const [filter, setFilter] = useState<IssueFilter>(() => (issues.some((i) => blocks(i) && !i.resolved) ? 'blocking' : 'open'));
  const [here, setHere] = useState(false);
  const [resolving, setResolving] = useState<ValidationIssue | null>(null);

  const inScope = (i: ValidationIssue) => !here || (i.segment_ids ?? []).some((id) => scopeOf.get(id) === scope);
  const test: Record<IssueFilter, (i: ValidationIssue) => boolean> = {
    blocking: (i) => !i.resolved && blocks(i),
    open: (i) => !i.resolved,
    resolved: (i) => !!i.resolved,
  };
  const shown = sortIssues(issues.filter((i) => test[filter](i) && inScope(i)));
  const where = (i: ValidationIssue) => {
    const id = i.segment_ids?.[0];
    return id ? `${headingOf(scopeOf.get(id) ?? '')} › ${id}` : undefined;
  };
  const resolve = (note: string) =>
    resolving &&
    resolveIssue.mutate(
      { issueId: resolving.issue_id, note },
      {
        onSuccess: (res) => {
          success(res.blockers.length ? `${res.blockers.length} thing(s) still block the approval.` : 'Nothing blocks the approval any more.', 'Issue resolved');
          setResolving(null);
        },
        onError: (e) => error(e.message, 'Not resolved'),
      },
    );

  if (!report) return <p className="p-4 text-xs text-text-muted">The translation has not been checked yet.</p>;
  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 space-y-2 border-b border-border px-3 py-2.5">
        <div className="flex flex-wrap gap-1">
          {(['blocking', 'open', 'resolved'] as IssueFilter[]).map((f) => (
            <button key={f} type="button" onClick={() => setFilter(f)} className={clsx('filter-chip h-7 px-2 text-[11px]', filter === f && 'filter-chip-active')}>
              {f === 'blocking' ? 'Blocking' : f === 'open' ? 'All open' : 'Resolved'}
              <span className="font-semibold">{issues.filter((i) => test[f](i) && inScope(i)).length}</span>
            </button>
          ))}
        </div>
        <label className="flex items-center gap-1.5 text-[11px] text-text-muted">
          <input type="checkbox" checked={here} onChange={(e) => setHere(e.target.checked)} /> Only this section
        </label>
      </div>
      <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto p-3">
        {shown.length === 0 && (
          <div className="flex flex-col items-center gap-2 py-10 text-center text-xs text-text-muted">
            <CheckCircle2 className="size-6 text-primary" />
            {filter === 'blocking' ? 'Nothing here blocks the approval.' : filter === 'resolved' ? 'No issue resolved yet.' : 'No open issue.'}
          </div>
        )}
        {shown.map((issue) => (
          <div key={issue.issue_id} onClickCapture={() => onSelect(issue)} className={clsx('rounded-md', active === issue.issue_id && 'ring-1 ring-primary/60')}>
            <IssueRow
              issue={issue}
              where={where(issue)}
              actions={
                canResolve && !issue.resolved ? (
                  <Button size="sm" variant={blocks(issue) ? 'primary' : 'secondary'} className="h-6 px-2 text-[11px]"
                    onClick={(e) => { e.stopPropagation(); setResolving(issue); }}>
                    Resolve…
                  </Button>
                ) : undefined
              }
            />
          </div>
        ))}
        {!canResolve && issues.some((i) => !i.resolved) && <p className="pt-1 text-[11px] text-text-muted">Issues can be resolved while the job waits for review.</p>}
      </div>
      <JustifyDialog
        open={!!resolving}
        title="Resolve this issue?"
        description={`${resolving?.message ?? ''}: say what you checked or why it is fine. Editing the segment again reopens it.`}
        confirmLabel="Resolve"
        busy={resolveIssue.isPending}
        onCancel={() => setResolving(null)}
        onConfirm={resolve}
      />
    </div>
  );
};

// ── Glossary and document terms ───────────────────────────────────────

const mentions = (english: string, term: string) => english.toLocaleLowerCase().includes(term.toLocaleLowerCase());

/** The job's glossary snapshot and its document terms; the selected segment's terms first. */
export const JobGlossaryPanel: React.FC<{ job: TranslationJob; selected?: Segment; onReplace: (find: string) => void }> = ({ job, selected, onReplace }) => {
  const glossary = useJobGlossary(job);
  const terms = useJobTerms(job);
  const [search, setSearch] = useState('');
  const english = selected?.source_text ?? '';

  const order = (entries: GlossaryEntry[]) => {
    const needle = search.trim().toLocaleLowerCase();
    return entries
      .filter((e) => !needle || `${e.source_term}\u0000${e.target_term}`.toLocaleLowerCase().includes(needle))
      .map((e) => ({ e, used: !!english && mentions(english, e.source_term) }))
      .sort((a, b) => Number(b.used) - Number(a.used));
  };
  const entry = (e: GlossaryEntry, used: boolean, agreed = false) => (
    <li key={e.source_term} className={clsx('rounded-md border px-2.5 py-1.5', used ? 'border-primary/40 bg-primary/[0.05]' : 'border-border')}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="text-text-muted">{e.source_term}</div>
          <div className="font-medium text-text-main">{e.do_not_translate ? <span title="Kept in English">{e.source_term} <span className="chip-muted text-[10px]">keep</span></span> : e.target_term}</div>
          {e.note && <div className="text-[10px] text-text-muted">{e.note}</div>}
        </div>
        {agreed && job.status === 'REVIEW_PENDING' && (
          <button type="button" title="Find this translation everywhere, to agree another one" onClick={() => onReplace(e.target_term)}
            className="shrink-0 rounded p-1 text-text-muted hover:bg-white/5 hover:text-text-main">
            <Replace className="size-3.5" />
          </button>
        )}
      </div>
    </li>
  );

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 border-b border-border px-3 py-2.5">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-text-muted" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search terms…" className="field h-7 pl-7 text-[11px]" />
        </div>
        {selected && <p className="mt-1.5 text-[10px] text-text-muted">Terms {selected.segment_id}'s English uses come first.</p>}
      </div>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3 text-xs">
        <div>
          <div className="mb-1.5 flex items-center gap-1.5 font-semibold text-text-main"><BookOpen className="size-3.5 text-primary" /> Glossary</div>
          {!job.glossary_id ? (
            <p className="text-[11px] text-text-muted">No glossary: free translation. The document terms below keep the wording consistent.</p>
          ) : glossary.data ? (
            <ul className="space-y-1">{order(glossary.data.entries).map(({ e, used }) => entry(e, used))}</ul>
          ) : (
            <p className="text-[11px] text-text-muted">Loading…</p>
          )}
          {job.glossary_id && <p className="mt-1.5 text-[10px] text-text-muted">{job.glossary_id} v{job.glossary_version}, as the job snapshotted it. Its terms are mandatory (HIGH issues).</p>}
        </div>
        <div>
          <div className="mb-1.5 font-semibold text-text-main">Document terms</div>
          {terms.data?.entries.length ? (
            <>
              <ul className="space-y-1">{order(terms.data.entries).map(({ e, used }) => entry(e, used, true))}</ul>
              <p className="mt-1.5 text-[10px] text-text-muted">
                Recurring English terms, translated once and used everywhere (MEDIUM issues). To agree another translation, replace every occurrence of
                the agreed one in the whole document.
              </p>
            </>
          ) : (
            <p className="text-[11px] text-text-muted">{terms.isLoading ? 'Loading…' : 'No recurring terms in this document.'}</p>
          )}
        </div>
      </div>
    </div>
  );
};

// ── Find and replace ──────────────────────────────────────────────────

const MARKERS = /[⟦⟧]|\{\{|\}\}/;
const key = (m: { segment_id: string; occurrence: number }) => `${m.segment_id}:${m.occurrence}`;

/** Find a word or phrase in the translations, preview every occurrence, replace the chosen ones. */
export const FindReplacePanel: React.FC<{
  job: TranslationJob;
  scope: string;
  scopeLabel: string;
  editable: boolean;
  initialFind?: string;
  onSelectSegment: (segmentId: string, scope: string) => void;
}> = ({ job, scope, scopeLabel, editable, initialFind = '', onSelectSegment }) => {
  const { success, info } = useToast();
  const { replace } = useTranslationMutations(job.job_id);
  const [find, setFind] = useState(initialFind);
  const [replaceWith, setReplaceWith] = useState('');
  const [caseSensitive, setCaseSensitive] = useState(false);
  const [wholeWord, setWholeWord] = useState(true);
  const [onlyHere, setOnlyHere] = useState(false);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  const [result, setResult] = useState<ReplaceResult | null>(null);
  const options = { find: find.trim(), case_sensitive: caseSensitive, whole_word: wholeWord, section: onlyHere ? scope : undefined };

  const preview = useMutation({
    mutationFn: (opts: typeof options) => translationsApi.replacePreview(job.job_id, opts),
    onSuccess: (p: ReplacePreview) => {
      setChosen(new Set(p.matches.map(key)));
      setResult(null);
    },
  });
  const p = preview.data;
  const all = !!p && p.matches.length > 0 && chosen.size === p.matches.length;
  const invalid = MARKERS.test(find) || MARKERS.test(replaceWith) ? 'Markers and reference tokens cannot be searched or typed.' : null;

  const run = (opts = options) => !invalid && opts.find && preview.mutate(opts);
  const apply = () => {
    if (!p) return;
    replace.mutate(
      {
        find: p.find, replace: replaceWith, case_sensitive: options.case_sensitive, whole_word: options.whole_word, section: options.section,
        targets: all ? 'all' : p.matches.filter((m) => chosen.has(key(m))).map((m) => ({ segment_id: m.segment_id, occurrence: m.occurrence })),
        expected_versions: p.translation_versions,
      },
      {
        onSuccess: (r) => {
          setResult(r);
          preview.reset();
          success(`${r.replaced} occurrence(s) in ${r.segments.length} segment(s)${r.term_updated.length ? '; the document term is agreed anew' : ''}.`, 'Replaced');
        },
        onError: (e) => {
          if (apiErrorCode(e) === 'PREVIEW_OUT_OF_DATE') {
            info('The translations changed since the preview; it was run again. Check the matches and replace again.', 'Preview refreshed');
            run({ ...options, find: p.find });
          }
        },
      },
    );
  };
  const withoutWholeWords = () => {
    setWholeWord(false);
    run({ ...options, whole_word: false });
  };

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 space-y-2 border-b border-border px-3 py-2.5 text-[11px]">
        <input value={find} onChange={(e) => setFind(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && run()} placeholder="Find in the translations…" className="field h-8 text-xs" aria-label="Find" />
        <input value={replaceWith} onChange={(e) => setReplaceWith(e.target.value)} placeholder="Replace with…" className="field h-8 text-xs" aria-label="Replace with" />
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-text-muted">
          <label className="flex items-center gap-1"><input type="checkbox" checked={wholeWord} onChange={(e) => setWholeWord(e.target.checked)} /> Whole words</label>
          <label className="flex items-center gap-1"><input type="checkbox" checked={caseSensitive} onChange={(e) => setCaseSensitive(e.target.checked)} /> Match case</label>
          <label className="flex items-center gap-1" title={scopeLabel}><input type="checkbox" checked={onlyHere} onChange={(e) => setOnlyHere(e.target.checked)} /> Only this section</label>
        </div>
        {invalid && <p className="text-danger">{invalid}</p>}
        <Button size="sm" variant="secondary" className="w-full" leftIcon={<Search className="size-3.5" />} disabled={!find.trim() || !!invalid} isLoading={preview.isPending} onClick={() => run()}>
          Find
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3 text-xs">
        <ErrorPanel error={preview.error} details={apiErrorDetails(preview.error)} />
        <ErrorPanel error={replace.error && apiErrorCode(replace.error) !== 'PREVIEW_OUT_OF_DATE' ? replace.error : null} details={apiErrorDetails(replace.error)} />
        {result && <ReplaceSummary result={result} />}
        {p && (
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-medium text-text-main">{p.total} match{p.total === 1 ? '' : 'es'} in {p.segments} segment{p.segments === 1 ? '' : 's'}</span>
              {p.matches.length > 0 && (
                <button type="button" className="text-[11px] text-primary hover:underline" onClick={() => setChosen(all ? new Set() : new Set(p.matches.map(key)))}>
                  {all ? 'Select none' : 'Select all'}
                </button>
              )}
            </div>
            {p.warnings.map((w) => (
              <p key={w} className="flex gap-1.5 rounded-md border border-warning/30 bg-warning/[0.06] px-2 py-1.5 text-[11px] text-text-muted">
                <AlertTriangle className="mt-0.5 size-3 shrink-0 text-warning" />{w}
              </p>
            ))}
            {Object.keys(p.longer_words).length > 0 && wholeWord && (
              <button type="button" onClick={withoutWholeWords} className="text-[11px] text-primary hover:underline">Search again without whole words</button>
            )}
            <ul className="space-y-1">
              {p.matches.map((m) => (
                <li key={key(m)} className="flex gap-2 rounded-md border border-border px-2 py-1.5">
                  <input type="checkbox" className="mt-0.5" checked={chosen.has(key(m))} aria-label={`${m.segment_id} occurrence ${m.occurrence + 1}`}
                    onChange={(e) => setChosen((s) => { const n = new Set(s); if (e.target.checked) n.add(key(m)); else n.delete(key(m)); return n; })} />
                  <button type="button" className="min-w-0 flex-1 text-left" onClick={() => onSelectSegment(m.segment_id, m.scope)}>
                    <div className="text-[10px] text-text-muted"><span className="font-mono">{m.segment_id}</span>{m.origin === 'human' && ' · edited'}</div>
                    <div className="text-text-main">
                      …{m.context_before}<mark className="rounded bg-warning/30 px-0.5 text-text-main">{m.match}</mark>{m.context_after}…
                    </div>
                    <div className="mt-0.5 line-clamp-1 text-[10px] text-text-muted">{m.english}</div>
                  </button>
                </li>
              ))}
            </ul>
            {p.matches.length > 0 && (
              <Button size="sm" variant="primary" className="w-full" leftIcon={<Replace className="size-3.5" />} disabled={!editable || !chosen.size} isLoading={replace.isPending} onClick={apply}
                title={editable ? undefined : 'Replacing is possible while the job waits for review'}>
                {all ? `Replace all ${p.total}` : `Replace ${chosen.size} selected`}
              </Button>
            )}
            {p.matches.length > 0 && !replaceWith && <p className="text-[10px] text-text-muted">With "Replace with" empty, the matches are deleted.</p>}
          </div>
        )}
        {!p && !result && !preview.error && (
          <p className="text-[11px] text-text-muted">
            Searches the current translations, never inside markers or reference tokens. Every replaced segment becomes a reviewer edit and is checked
            again; the document updates with "Update document".
          </p>
        )}
      </div>
    </div>
  );
};

const ReplaceSummary: React.FC<{ result: ReplaceResult }> = ({ result }) => (
  <div className="mb-3 space-y-1.5 rounded-md border border-primary/30 bg-primary/[0.05] px-3 py-2 text-[11px]">
    <div className="font-medium text-text-main">{result.replaced} occurrence(s) replaced in {result.segments.length} segment(s)</div>
    {result.term_updated.length > 0 && <div className="text-text-muted">Document term agreed anew: {result.term_updated.join(', ')}</div>}
    {result.skipped.length > 0 && (
      <div className="text-warning">
        Skipped (the document could not show the result):
        <ul className="ml-3 list-disc">{result.skipped.map((s) => <li key={s.segment_id}>{s.segment_id}: {s.problems.join('; ')}</li>)}</ul>
      </div>
    )}
    {Object.keys(result.longer_words).length > 0 && (
      <div className="text-text-muted">Still inside longer words: {Object.entries(result.longer_words).map(([w, n]) => `${w} (${n})`).join(', ')}</div>
    )}
    {result.issues.length > 0 && <div className="text-text-muted">{result.issues.length} issue(s) open on the changed segments.</div>}
  </div>
);
