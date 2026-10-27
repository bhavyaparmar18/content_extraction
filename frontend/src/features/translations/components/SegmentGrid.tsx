import React, { Suspense, lazy, useEffect, useMemo, useRef, useState } from 'react';
import { AlertTriangle, Check, Pencil, Search, X } from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/ToastStack';
import { apiErrorCode, apiErrorDetails } from '@/lib/api';
import { SEVERITY_CLASSES } from '@/features/migrations/status';
import { useTranslationMutations } from '../hooks';
import { hasCells, structuralProblems } from '../markers';
import { filterSegments, locatorLabel, sameTextSegments, worstSeverity, type SectionEntry, type SegmentFilter } from '../segments';
import type { Segment, ValidationIssue } from '../types';
import { SegmentText } from './SegmentText';

// The editor (TipTap, a few hundred kB) loads on the first edit, not with the page.
const SegmentEditor = lazy(() => import('./SegmentEditor').then((m) => ({ default: m.SegmentEditor })));

/** The review's left pane: each section with its segment count, its worst open issue and its edits. */
export const TranslationSectionNav: React.FC<{
  sections: SectionEntry[];
  byScope: Map<string, Segment[]>;
  open: Map<string, ValidationIssue[]>;
  current: string;
  onSelect: (scope: string) => void;
}> = ({ sections, byScope, open, current, onSelect }) => {
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return;
    e.preventDefault();
    const at = sections.findIndex((s) => s.scope === current);
    const next = sections[Math.min(sections.length - 1, Math.max(0, at + (e.key === 'ArrowDown' ? 1 : -1)))];
    if (next) onSelect(next.scope);
  };
  return (
    <nav className="h-full overflow-y-auto p-2" onKeyDown={onKey}>
      {sections.map((s) => {
        const segments = byScope.get(s.scope) ?? [];
        const issues = segments.flatMap((seg) => open.get(seg.segment_id) ?? []);
        const worst = worstSeverity(issues);
        const edited = segments.filter((seg) => seg.origin === 'human').length;
        return (
          <button
            key={s.scope}
            type="button"
            onClick={() => onSelect(s.scope)}
            className={clsx(
              'flex w-full items-start gap-2 rounded-md px-2.5 py-2 text-left text-xs transition',
              current === s.scope ? 'bg-primary/10 text-text-main ring-1 ring-primary/40' : 'text-text-muted hover:bg-white/5 hover:text-text-main',
            )}
          >
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium">{s.number ? `${s.number} ` : ''}{s.heading}</span>
              <span className="mt-0.5 flex flex-wrap gap-x-2 text-[10px] text-text-muted">
                <span>{segments.length} segment{segments.length === 1 ? '' : 's'}</span>
                {edited > 0 && <span className="text-info">{edited} edited</span>}
              </span>
            </span>
            {worst && (
              <span className={clsx('mt-0.5 rounded border px-1 text-[10px] font-semibold', SEVERITY_CLASSES[worst])} title={`${issues.length} open issue(s)`}>
                {issues.length}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
};

const FILTERS: { id: SegmentFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'issues', label: 'With issues' },
  { id: 'edited', label: 'Edited' },
  { id: 'english', label: 'Shown in English' },
  { id: 'copied', label: 'Copied' },
];

interface GridProps {
  jobId: string;
  section: SectionEntry | undefined;
  segments: Segment[];
  all: Segment[];
  open: Map<string, ValidationIssue[]>;
  english: Set<string>;
  languageName: string;
  selected: string | null;
  editable: boolean;
  readOnlyReason?: string;
  onSelect: (segmentId: string) => void;
  onSelectIssue: (issue: ValidationIssue) => void;
}

/** ③ One section's segments: the English and its translation side by side, each editable around its markers. */
export const SegmentGrid: React.FC<GridProps> = ({ jobId, section, segments, all, open, english, languageName, selected, editable, readOnlyReason, onSelect, onSelectIssue }) => {
  const [filter, setFilter] = useState<SegmentFilter>('all');
  const [search, setSearch] = useState('');
  const [editingId, setEditing] = useState<string | null>(null);
  const editing = editable ? editingId : null; // a render or an approval closes the editor
  const scrollRef = useRef<HTMLDivElement>(null);
  const context = useMemo(() => ({ open, english }), [open, english]);
  const shown = filterSegments(segments, filter, context, search);

  // Bring the selected segment into view (a click on an issue or a match may select one far away).
  useEffect(() => {
    const box = scrollRef.current;
    const row = selected ? box?.querySelector<HTMLElement>(`[data-segment="${selected}"]`) : null;
    // Scroll the list only: scrollIntoView would also scroll the panes around it, which hide their overflow.
    if (box && row) box.scrollTo({ top: row.offsetTop - box.clientHeight / 2 + row.clientHeight / 2, behavior: 'smooth' });
  }, [selected, section?.scope]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-border px-3 py-2">
        <h2 className="mr-2 truncate text-sm font-semibold text-text-main">{section ? `${section.number ? `${section.number} ` : ''}${section.heading}` : 'Segments'}</h2>
        <div className="flex flex-wrap gap-1">
          {FILTERS.map((f) => {
            const n = filterSegments(segments, f.id, context).length;
            return (
              <button key={f.id} type="button" onClick={() => setFilter(f.id)} disabled={f.id !== 'all' && !n}
                className={clsx('filter-chip h-7 px-2 text-[11px] disabled:opacity-40', filter === f.id && 'filter-chip-active')}>
                {f.label} <span className="font-semibold">{n}</span>
              </button>
            );
          })}
        </div>
        <div className="relative ml-auto">
          <Search className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-text-muted" />
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Filter this section…" className="field h-7 w-52 pl-7 text-[11px]" />
        </div>
      </div>
      {!editable && readOnlyReason && (
        <div className="shrink-0 border-b border-info/20 bg-info/[0.06] px-4 py-1.5 text-[11px] text-info">{readOnlyReason}</div>
      )}
      <div className="grid shrink-0 grid-cols-2 gap-4 border-b border-border px-4 py-1 text-[10px] font-semibold uppercase tracking-wider text-text-muted">
        <span>English</span>
        <span>{languageName}</span>
      </div>
      <div ref={scrollRef} className="relative min-h-0 flex-1 divide-y divide-border overflow-y-auto">
        {shown.length === 0 && <p className="p-8 text-center text-xs text-text-muted">No segment here{filter !== 'all' || search ? ' with this filter' : ''}.</p>}
        {shown.map((segment) => (
          <SegmentRow
            key={segment.segment_id}
            jobId={jobId}
            segment={segment}
            all={all}
            issues={open.get(segment.segment_id) ?? []}
            inEnglish={english.has(segment.segment_id)}
            selected={selected === segment.segment_id}
            editing={editing === segment.segment_id}
            editable={editable}
            onSelect={() => onSelect(segment.segment_id)}
            onEdit={() => { onSelect(segment.segment_id); setEditing(segment.segment_id); }}
            onDone={() => setEditing(null)}
            onSelectIssue={onSelectIssue}
          />
        ))}
      </div>
    </div>
  );
};

const ORIGIN: Record<string, { label: string; className: string; title: string }> = {
  llm: { label: 'LLM', className: 'chip-muted', title: 'Translated by the LLM' },
  repair: { label: 'repaired', className: 'chip-muted', title: 'Retranslated once after a check failed' },
  human: { label: 'edited', className: 'chip border-info/40 bg-info/10 text-info', title: 'Edited by a reviewer: never overwritten by the LLM' },
  copied: { label: 'copied', className: 'chip-muted', title: 'Nothing to translate: copied from the English' },
};

const SegmentRow: React.FC<{
  jobId: string;
  segment: Segment;
  all: Segment[];
  issues: ValidationIssue[];
  inEnglish: boolean;
  selected: boolean;
  editing: boolean;
  editable: boolean;
  onSelect: () => void;
  onEdit: () => void;
  onDone: () => void;
  onSelectIssue: (issue: ValidationIssue) => void;
}> = ({ jobId, segment, all, issues, inEnglish, selected, editing, editable, onSelect, onEdit, onDone, onSelectIssue }) => {
  const cells = hasCells(segment.source_text);
  const xref = segment.kind === 'xref';
  const origin = segment.origin ? ORIGIN[segment.origin] : undefined;
  return (
    <div
      data-segment={segment.segment_id}
      onClick={onSelect}
      onDoubleClick={() => editable && !editing && onEdit()}
      className={clsx('group px-4 py-2.5 transition-colors', selected ? 'bg-primary/[0.06]' : 'hover:bg-white/[0.02]')}
    >
      <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[10px] text-text-muted">
        <span className="font-mono">{segment.segment_id}</span>
        <span>{locatorLabel(segment)}</span>
        {origin && <span className={clsx('text-[10px]', origin.className)} title={origin.title}>{origin.label}</span>}
        {inEnglish && <span className="chip border-warning/40 bg-warning/10 text-[10px] text-warning" title="The last render showed the English here">shown in English</span>}
        {issues.map((i) => (
          <button key={i.issue_id} type="button" title={i.message}
            onClick={(e) => { e.stopPropagation(); onSelectIssue(i); }}
            className={clsx('rounded border px-1 font-mono text-[10px]', SEVERITY_CLASSES[i.gate ? 'critical' : i.severity])}>
            {i.issue_id.replace(`TQ-${segment.segment_id}-`, '')}
          </button>
        ))}
        {editable && !editing && (
          <button type="button" onClick={(e) => { e.stopPropagation(); onEdit(); }}
            className="ml-auto flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] text-text-muted opacity-0 hover:bg-white/5 hover:text-text-main group-hover:opacity-100 focus:opacity-100">
            <Pencil className="size-3" /> Edit
          </button>
        )}
      </div>
      <div className="grid grid-cols-2 gap-4 text-xs leading-relaxed">
        <SegmentText text={segment.source_text} cells={cells} xref={xref} className="text-text-muted" />
        {editing ? (
          <EditBox jobId={jobId} segment={segment} all={all} cells={cells} xref={xref} onDone={onDone} />
        ) : (
          <SegmentText text={segment.target_text} cells={cells} xref={xref} className="text-text-main" />
        )}
      </div>
    </div>
  );
};

/** The editor of one segment, then the choice of how far the edit goes when other segments show the same English. */
const EditBox: React.FC<{ jobId: string; segment: Segment; all: Segment[]; cells: boolean; xref: boolean; onDone: () => void }> = ({
  jobId,
  segment,
  all,
  cells,
  xref,
  onDone,
}) => {
  const { success, error } = useToast();
  const { editSegment } = useTranslationMutations(jobId);
  const initial = segment.target_text ?? '';
  const [draft, setDraft] = useState(initial);
  const [asking, setAsking] = useState(false);
  const [serverProblems, setServerProblems] = useState<string[]>([]);
  const same = useMemo(() => sameTextSegments(segment, all), [segment, all]);
  const problems = structuralProblems(segment.source_text, draft);
  const changed = draft.trim() !== initial.trim();

  const send = (applyTo: 'same_text' | 'this') =>
    editSegment.mutate(
      { segmentId: segment.segment_id, text: draft, applyTo },
      {
        onSuccess: (result) => {
          const opened = result.issues.length;
          success(
            `${result.segments.length > 1 ? `Saved to ${result.segments.length} segments` : 'Saved'}${opened ? `; ${opened} issue(s) open on ${result.segments.length > 1 ? 'them' : 'it'}` : ''}. The document updates with "Update document".`,
            `${segment.segment_id} edited`,
          );
          onDone();
        },
        onError: (e) => {
          setAsking(false);
          if (apiErrorCode(e) === 'SEGMENT_INVALID') setServerProblems(apiErrorDetails(e));
          else error(e.message, 'Not saved');
        },
      },
    );
  const save = () => {
    if (!changed || problems.length || editSegment.isPending) return;
    if (same.length && !asking) setAsking(true);
    else send('same_text');
  };

  return (
    <div onClick={(e) => e.stopPropagation()} className="space-y-1.5">
      <Suspense fallback={<div className="rounded-md border border-primary/50 px-2.5 py-2 text-xs text-text-muted">Loading the editor…</div>}>
        <SegmentEditor initial={initial} cells={cells} xref={xref} onChange={(t) => { setDraft(t); setAsking(false); setServerProblems([]); }} onSave={save} onCancel={onDone} />
      </Suspense>
      {[...problems, ...serverProblems].length > 0 && changed && (
        <ul className="space-y-0.5 text-[11px] text-danger">
          {[...new Set([...problems, ...serverProblems])].map((p) => <li key={p} className="flex gap-1"><AlertTriangle className="mt-0.5 size-3 shrink-0" />{p}</li>)}
        </ul>
      )}
      {asking ? (
        <div className="rounded-md border border-primary/30 bg-primary/[0.05] p-2 text-[11px]">
          <p className="mb-1.5 text-text-main">{same.length} other segment{same.length > 1 ? 's show' : ' shows'} the same English. Apply this translation to:</p>
          <div className="flex flex-wrap gap-1.5">
            <Button size="sm" variant="primary" className="h-7 px-2 text-[11px]" isLoading={editSegment.isPending && editSegment.variables?.applyTo === 'same_text'} onClick={() => send('same_text')}>
              All {same.length + 1} with this English
            </Button>
            <Button size="sm" variant="secondary" className="h-7 px-2 text-[11px]" isLoading={editSegment.isPending && editSegment.variables?.applyTo === 'this'} onClick={() => send('this')}>
              This segment only
            </Button>
            <Button size="sm" variant="ghost" className="h-7 px-2 text-[11px]" onClick={() => setAsking(false)}>Back</Button>
          </div>
          <p className="mt-1 text-[10px] text-text-muted">Segments a reviewer already edited keep their own text.</p>
        </div>
      ) : (
        <div className="flex items-center gap-1.5">
          <Button size="sm" variant="primary" className="h-7 px-2 text-[11px]" leftIcon={<Check className="size-3" />} disabled={!changed || problems.length > 0}
            isLoading={editSegment.isPending} onClick={save}>
            Save
          </Button>
          <Button size="sm" variant="ghost" className="h-7 px-2 text-[11px]" leftIcon={<X className="size-3" />} onClick={onDone}>Cancel</Button>
          <span className="ml-auto text-[10px] text-text-muted">Ctrl+Enter saves · Esc cancels · chips can't be removed</span>
        </div>
      )}
    </div>
  );
};
