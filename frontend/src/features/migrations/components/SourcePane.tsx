import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, ExternalLink, Image as ImageIcon, Info, Loader2 } from 'lucide-react';
import { clsx } from 'clsx';
import { api } from '@/lib/api';
import { migrationsApi } from '../api';
import { useActiveFocus, focusProps, type Focus } from '../focusStore';
import type { EvidenceSpan, SourceDocument, SourceUnit } from '../types';
import { DocxViewer } from './DocxViewer';
import { PaneTabs, ScrollToFocus } from './paneParts';

interface SourcePaneProps {
  jobId: string;
  source?: SourceDocument;
  /** The SOP's document UID: its images are served under it. */
  documentUid?: string;
  /** Extra marks per unit, e.g. "unplaced" in the slot plan. */
  unitMarks?: Map<string, string>;
}

type View = 'structured' | 'document';

/** The original SOP: its extracted sections and units, or the uploaded file itself. */
export const SourcePane: React.FC<SourcePaneProps> = ({ jobId, source, documentUid, unitMarks }) => {
  const [view, setView] = useState<View>('structured');
  const focus = useActiveFocus();
  const isPdf = source?.file_type?.toLowerCase() === 'pdf';

  const highlights = useMemo(() => passagesFor(source, focus), [source, focus]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PaneTabs
        value={view}
        onChange={(v) => setView(v as View)}
        tabs={[
          { id: 'structured', label: 'Structured' },
          { id: 'document', label: isPdf ? 'Original PDF' : 'Original document' },
        ]}
        extra={source && <span className="truncate text-[10px] text-text-muted" title={source.source_file}>{fileName(source.source_file)}</span>}
      />
      <div className="min-h-0 flex-1">
        {view === 'structured' ? (
          source ? (
            <StructuredSource source={source} focus={focus} assetBase={documentUid || source.document_id} unitMarks={unitMarks} />
          ) : (
            <PaneLoading />
          )
        ) : isPdf ? (
          <PdfView jobId={jobId} page={focusPage(source, focus)} />
        ) : (
          <DocxViewer fileKey={['source', jobId]} load={() => migrationsApi.sourceFile(jobId)} highlights={highlights} />
        )}
      </div>
    </div>
  );
};

// ── Structured view ───────────────────────────────────────────────────

const StructuredSource: React.FC<{
  source: SourceDocument;
  focus: Focus | null;
  assetBase: string;
  unitMarks?: Map<string, string>;
}> = ({ source, focus, assetBase, unitMarks }) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const units = new Set(focus?.sourceUnitIds ?? []);
  const sections = new Set(focus?.sourceSectionIds ?? []);
  const spans = groupSpans(focus?.spans);
  const target = focus?.sourceUnitIds?.[0]
    ? `[data-unit-id="${focus.sourceUnitIds[0]}"]`
    : focus?.sourceSectionIds?.[0]
      ? `[data-section-id="${focus.sourceSectionIds[0]}"]`
      : null;

  return (
    <div ref={scrollRef} className="h-full overflow-y-auto px-3 py-3">
      <ScrollToFocus container={scrollRef} selector={focus?.origin === 'source' ? null : target} />
      <div className="space-y-4">
        {source.sections.map((section) => (
          <section
            key={section.section_id}
            data-section-id={section.section_id}
            className={clsx(
              'rounded-md border-l-2 pl-2.5 transition-colors',
              sections.has(section.section_id) ? 'border-primary bg-primary/[0.06]' : 'border-transparent',
            )}
          >
            <header className="flex items-baseline gap-2 py-1" {...focusProps({ sourceSectionIds: [section.section_id] }, 'source')}>
              <h4
                className={clsx('cursor-pointer font-semibold text-text-main', section.level <= 1 ? 'text-[13px]' : 'text-xs')}
                style={{ paddingLeft: Math.max(0, section.level - 1) * 8 }}
              >
                {section.number && <span className="mr-1.5 text-text-muted">{section.number}</span>}
                {section.heading}
              </h4>
              <span className="unit-id ml-auto shrink-0">{section.section_id}</span>
            </header>
            <div className="space-y-1">
              {section.units.map((unit) => (
                <UnitRow
                  key={unit.unit_id}
                  unit={unit}
                  focused={units.has(unit.unit_id)}
                  spans={spans.get(unit.unit_id)}
                  assetBase={assetBase}
                  mark={unitMarks?.get(unit.unit_id)}
                />
              ))}
              {section.units.length === 0 && <div className="py-1 text-[11px] italic text-text-muted">No content</div>}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
};

const UNIT_STYLE: Partial<Record<SourceUnit['unit_type'], string>> = {
  warning: 'border-l-2 border-danger/60 bg-danger/[0.06]',
  note: 'border-l-2 border-info/60 bg-info/[0.06]',
  caption: 'italic text-text-muted',
  heading_statement: 'font-semibold',
};

const UnitRow: React.FC<{
  unit: SourceUnit;
  focused: boolean;
  spans?: EvidenceSpan[];
  assetBase: string;
  mark?: string;
}> = ({ unit, focused, spans, assetBase, mark }) => {
  const figure = unit.assets?.find((a) => a.kind === 'figure');
  return (
    <div
      data-unit-id={unit.unit_id}
      {...focusProps({ sourceUnitIds: [unit.unit_id], sourceSectionIds: [unit.section_id] }, 'source')}
      className={clsx(
        'group cursor-pointer rounded px-2 py-1 text-xs leading-relaxed text-text-main/90 transition-colors hover:bg-white/[0.04]',
        UNIT_STYLE[unit.unit_type],
        focused && 'focus-ring',
        unit.is_boilerplate && 'opacity-60',
      )}
      style={{ marginLeft: (unit.list_level ?? 0) * 12 }}
    >
      <div className="mb-0.5 flex items-center gap-1.5">
        <span className="unit-id">{unit.unit_id.replace(`${unit.section_id}-`, '')}</span>
        {unit.unit_type !== 'paragraph' && <span className="chip-muted">{unit.unit_type.replace(/_/g, ' ')}</span>}
        {unit.unit_type === 'warning' && <AlertTriangle className="size-3 text-danger" />}
        {unit.unit_type === 'note' && <Info className="size-3 text-info" />}
        {mark && <span className="chip border-warning/40 bg-warning/10 text-warning">{mark}</span>}
        {unit.location?.page != null && <span className="ml-auto text-[10px] text-text-muted">p.{unit.location.page}</span>}
      </div>
      {unit.unit_type === 'table_row' && unit.table_ref?.cells?.length ? (
        <TableRowCells unit={unit} />
      ) : figure ? (
        <figure className="space-y-1">
          {figure.path ? (
            <img
              src={api.getAssetUrl(assetBase, api.assetFileName(figure.path))}
              alt={unit.text || 'Figure'}
              className="max-h-48 rounded border border-border bg-white object-contain"
              loading="lazy"
            />
          ) : (
            <ImageIcon className="size-6 text-text-muted" />
          )}
          {unit.text && <figcaption className="text-[11px] text-text-muted">{unit.text}</figcaption>}
        </figure>
      ) : (
        <p>
          {unit.list_number && <span className="mr-1 text-text-muted">{unit.list_number}.</span>}
          <SpanText text={unit.text} spans={spans} />
        </p>
      )}
    </div>
  );
};

const TableRowCells: React.FC<{ unit: SourceUnit }> = ({ unit }) => {
  const ref = unit.table_ref!;
  const headers = ref.header_cells ?? [];
  return (
    <div className="grid gap-px overflow-hidden rounded border border-border bg-border" style={{ gridTemplateColumns: `repeat(${Math.max(1, ref.cells!.length)}, minmax(0, 1fr))` }}>
      {ref.cells!.map((cell) => (
        <div key={cell.col} className={clsx('bg-card px-1.5 py-1', cell.is_header && 'font-semibold')}>
          {headers[cell.col] && !cell.is_header && <div className="text-[9px] uppercase tracking-wide text-text-muted">{headers[cell.col]}</div>}
          {(cell.paragraphs?.length ? cell.paragraphs : [cell.text]).map((p, i) => <div key={i}>{p}</div>)}
        </div>
      ))}
    </div>
  );
};

/** The unit's text with the evidence spans of the focused claim underlined. */
const SpanText: React.FC<{ text: string; spans?: EvidenceSpan[] }> = ({ text, spans }) => {
  if (!spans?.length) return <>{text}</>;
  const parts: React.ReactNode[] = [];
  let at = 0;
  [...spans].sort((a, b) => a.start - b.start).forEach((span, i) => {
    const start = Math.max(at, span.start);
    const end = Math.min(text.length, span.end);
    if (end <= start) return;
    parts.push(text.slice(at, start));
    parts.push(<mark key={i} className="rounded-sm bg-primary/30 text-inherit">{text.slice(start, end)}</mark>);
    at = end;
  });
  parts.push(text.slice(at));
  return <>{parts}</>;
};

// ── Document view helpers ─────────────────────────────────────────────

const PdfView: React.FC<{ jobId: string; page?: number }> = ({ jobId, page }) => {
  const file = useQuery({ queryKey: ['docx', 'source', jobId], queryFn: () => migrationsApi.sourceFile(jobId), staleTime: Infinity });
  const url = useMemo(() => (file.data ? URL.createObjectURL(file.data) : null), [file.data]);
  useEffect(() => () => {
    if (url) URL.revokeObjectURL(url);
  }, [url]);
  if (!url) return <PaneLoading />;
  return (
    <div className="flex h-full flex-col">
      <div className="flex justify-end border-b border-border px-3 py-1">
        <a href={url} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-[11px] text-text-muted hover:text-text-main">
          <ExternalLink className="size-3" /> Open in new tab
        </a>
      </div>
      <iframe key={page} src={`${url}#page=${page ?? 1}`} title="Original SOP" className="min-h-0 flex-1 bg-white" />
    </div>
  );
};

export const PaneLoading: React.FC = () => (
  <div className="grid h-full place-items-center text-xs text-text-muted">
    <span className="flex items-center gap-2">
      <Loader2 className="size-4 animate-spin" /> Loading…
    </span>
  </div>
);

/** The text of the focused passages, for finding them in the rendered document. */
function passagesFor(source: SourceDocument | undefined, focus: Focus | null): string[] {
  if (!source || !focus) return [];
  const byId = new Map(source.sections.flatMap((s) => s.units.map((u) => [u.unit_id, u] as const)));
  if (focus.sourceUnitIds?.length) {
    return focus.sourceUnitIds.map((id) => byId.get(id)).filter(Boolean).map((u) => unitNeedle(u!));
  }
  const sections = new Set(focus.sourceSectionIds ?? []);
  return source.sections.filter((s) => sections.has(s.section_id)).map((s) => s.heading);
}

function unitNeedle(unit: SourceUnit): string {
  const cells = unit.table_ref?.cells?.map((c) => c.text) ?? [];
  return cells.length ? cells.reduce((a, b) => (b.length > a.length ? b : a), '') : unit.text;
}

function focusPage(source: SourceDocument | undefined, focus: Focus | null): number | undefined {
  const id = focus?.sourceUnitIds?.[0];
  if (!source || !id) return undefined;
  for (const s of source.sections) {
    const unit = s.units.find((u) => u.unit_id === id);
    if (unit) return unit.location?.page;
  }
  return undefined;
}

function groupSpans(spans?: EvidenceSpan[]): Map<string, EvidenceSpan[]> {
  const map = new Map<string, EvidenceSpan[]>();
  spans?.forEach((s) => map.set(s.unit_id, [...(map.get(s.unit_id) ?? []), s]));
  return map;
}

const fileName = (path: string) => path.split(/[\\/]/).pop() || path;
