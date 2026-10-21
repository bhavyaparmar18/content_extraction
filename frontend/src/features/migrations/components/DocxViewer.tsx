import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { AlertCircle, Loader2, Maximize2, ZoomIn, ZoomOut } from 'lucide-react';
import { clsx } from 'clsx';
import { apiErrorDetails } from '@/lib/api';
import { findBlocks, needleOf } from '../docxHighlight';

interface DocxViewerProps {
  /** Cache key of the file; a new key loads and renders again. */
  fileKey: readonly unknown[];
  load: () => Promise<Blob>;
  /** Passages to highlight and scroll to (their text; matched best-effort). */
  highlights?: string[];
  /** Shown instead of the document when it cannot be loaded (e.g. the export is not allowed yet). */
  emptyMessage?: React.ReactNode;
  toolbarExtra?: React.ReactNode;
  className?: string;
}

const PAGE_WIDTH_PX = 816; // A4/Letter at 96 dpi, before docx-preview's own padding
const BLOCK_SELECTOR = 'p, tr';
const SKIPPED_STYLES = /(^|\s)docx_toc/i;

/** A Word document rendered in the browser (docx-preview, loaded on first use). */
export const DocxViewer: React.FC<DocxViewerProps> = ({
  fileKey,
  load,
  highlights,
  emptyMessage,
  toolbarExtra,
  className,
}) => {
  const hostRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [rendered, setRendered] = useState(0); // bumps after each render, so highlights apply again
  const [renderError, setRenderError] = useState<string | null>(null);
  const [zoom, setZoom] = useState<number | 'fit'>('fit');
  const [fitScale, setFitScale] = useState(1);

  const file = useQuery({ queryKey: ['docx', ...fileKey], queryFn: load, staleTime: Infinity, retry: false });

  useEffect(() => {
    const host = hostRef.current;
    if (!file.data || !host) return;
    let cancelled = false;
    setRenderError(null);
    import('docx-preview')
      .then(({ renderAsync }) => {
        if (cancelled) return undefined;
        host.innerHTML = '';
        return renderAsync(file.data, host, undefined, {
          className: 'docx',
          inWrapper: true,
          breakPages: true,
          ignoreLastRenderedPageBreak: false,
          renderHeaders: true,
          renderFooters: true,
          renderComments: false,
          renderChanges: false,
        });
      })
      .then(() => !cancelled && setRendered((n) => n + 1))
      .catch((err: unknown) => !cancelled && setRenderError(err instanceof Error ? err.message : String(err)));
    return () => {
      cancelled = true;
    };
  }, [file.data]);

  // Fit the page width to the pane.
  useLayoutEffect(() => {
    const scroller = scrollRef.current;
    if (!scroller) return undefined;
    const observer = new ResizeObserver(([entry]) => {
      const width = entry.contentRect.width - 24;
      setFitScale(Math.max(0.3, Math.min(1.5, width / (PAGE_WIDTH_PX + 60))));
    });
    observer.observe(scroller);
    return () => observer.disconnect();
  }, []);

  // Highlight and scroll to the focused passages.
  const highlightKey = (highlights ?? []).join('\u0000');
  const needles = useMemo(() => (highlightKey ? highlightKey.split('\u0000').map(needleOf).filter(Boolean) : []), [highlightKey]);
  useEffect(() => {
    const host = hostRef.current;
    if (!host || !rendered) return;
    host.querySelectorAll('.docx-focus').forEach((el) => el.classList.remove('docx-focus'));
    if (!needles.length) return;
    const blocks = Array.from(host.querySelectorAll<HTMLElement>(BLOCK_SELECTOR)).filter(
      (el) =>
        !(el.tagName === 'P' && el.closest('tr')) && // a table row is one block
        !SKIPPED_STYLES.test(el.className) && // the table of contents repeats every heading
        !el.closest('header, footer'),
    );
    const matches = findBlocks(blocks.map((el) => el.textContent ?? ''), needles);
    matches.forEach((i) => blocks[i].classList.add('docx-focus'));
    if (matches.length) blocks[matches[0]].scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [needles, rendered]);

  const scale = zoom === 'fit' ? fitScale : zoom;
  const failed = file.error || renderError;
  const reasons = file.error ? apiErrorDetails(file.error) : [];

  return (
    <div className={clsx('flex h-full min-h-0 flex-col', className)}>
      <div className="flex items-center justify-between gap-2 border-b border-border px-3 py-1.5">
        <div className="flex min-w-0 items-center gap-2">{toolbarExtra}</div>
        <div className="flex shrink-0 items-center gap-0.5 text-text-muted">
          <ToolButton title="Zoom out" onClick={() => setZoom(Math.max(0.3, +(scale - 0.1).toFixed(2)))}>
            <ZoomOut className="size-3.5" />
          </ToolButton>
          <span className="w-10 text-center font-mono text-[11px]">{Math.round(scale * 100)}%</span>
          <ToolButton title="Zoom in" onClick={() => setZoom(Math.min(2, +(scale + 0.1).toFixed(2)))}>
            <ZoomIn className="size-3.5" />
          </ToolButton>
          <ToolButton title="Fit width" active={zoom === 'fit'} onClick={() => setZoom('fit')}>
            <Maximize2 className="size-3.5" />
          </ToolButton>
        </div>
      </div>

      <div ref={scrollRef} className="docx-scroll relative min-h-0 flex-1 overflow-auto">
        {file.isLoading && (
          <div className="absolute inset-0 grid place-items-center text-xs text-text-muted">
            <span className="flex items-center gap-2">
              <Loader2 className="size-4 animate-spin" /> Loading document…
            </span>
          </div>
        )}
        {failed ? (
          <div className="p-6 text-sm text-text-muted">
            {emptyMessage ?? (
              <div className="flex items-start gap-2">
                <AlertCircle className="mt-0.5 size-4 shrink-0 text-danger" />
                <div>
                  <div className="font-medium text-text-main">The document could not be shown</div>
                  <div className="mt-1 text-xs">{file.error instanceof Error ? file.error.message : renderError}</div>
                  {reasons.length > 0 && (
                    <ul className="mt-2 list-disc space-y-0.5 pl-4 text-xs">
                      {reasons.map((r) => <li key={r}>{r}</li>)}
                    </ul>
                  )}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div ref={hostRef} className="docx-host" style={{ zoom: scale }} />
        )}
      </div>
    </div>
  );
};

const ToolButton: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement> & { active?: boolean }> = ({
  active,
  className,
  ...props
}) => (
  <button
    type="button"
    className={clsx(
      'grid size-7 place-items-center rounded hover:bg-white/5 hover:text-text-main',
      active && 'bg-primary/10 text-primary',
      className,
    )}
    {...props}
  />
);
