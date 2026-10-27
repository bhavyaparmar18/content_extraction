import React, { useCallback, useEffect, useRef, useState } from 'react';
import { PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, X } from 'lucide-react';
import { clsx } from 'clsx';
import { useReviewUi } from '../focusStore';

interface Pane {
  title: string;
  /** For the show / hide toggle, e.g. "SOP". */
  short: string;
  icon: React.ReactNode;
  content: React.ReactNode;
}

interface ReviewShellProps {
  left: Pane;
  right: Pane;
  /** Start with both side panes hidden (a step that needs the room, e.g. the document preview). */
  roomy?: boolean;
  /** Where the pane sizes are remembered (each workspace its own). */
  storageKey?: string;
  children: React.ReactNode;
}

/** Below this width the work area would be squeezed: the context panes open as drawers instead. */
const WIDE_SHELL_PX = 1100;
const MIN_WIDTH = 260;
const STORAGE_KEY = 'migration-review-panes';

interface PaneState {
  left: number;
  right: number;
  leftOpen: boolean;
  rightOpen: boolean;
}

const DEFAULTS: PaneState = { left: 380, right: 340, leftOpen: true, rightOpen: true };

function readPanes(key: string): PaneState {
  try {
    return { ...DEFAULTS, ...JSON.parse(localStorage.getItem(key) || '{}') };
  } catch {
    return DEFAULTS;
  }
}

/** Whether the element is at least ``min`` pixels wide (it follows window and sidebar changes). */
function useWiderThan(ref: React.RefObject<HTMLElement | null>, min: number): boolean {
  const [wide, setWide] = useState(true);
  useEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const observer = new ResizeObserver(([entry]) => setWide(entry.contentRect.width >= min));
    observer.observe(el);
    return () => observer.disconnect();
  }, [ref, min]);
  return wide;
}

/**
 * Source SOP | work area | template. On wide screens the side panes are resizable and collapsible
 * (sizes remembered); on narrower ones they open as drawers over the work area.
 */
export const ReviewShell: React.FC<ReviewShellProps> = ({ left, right, roomy = false, storageKey = STORAGE_KEY, children }) => {
  const rowRef = useRef<HTMLDivElement>(null);
  const wide = useWiderThan(rowRef, WIDE_SHELL_PX);
  const [panes, setPanes] = useState<PaneState>(() => readPanes(storageKey));
  const [drawer, setDrawer] = useState<'left' | 'right' | null>(null);
  // In a roomy step the panes start hidden; showing one there is not remembered for the other steps.
  const [roomyOpen, setRoomyOpen] = useState({ left: false, right: false, roomy });
  if (roomyOpen.roomy !== roomy) setRoomyOpen({ left: false, right: false, roomy });

  // Another part of the page asked for a pane (e.g. the issues, after a click on a claim's badge).
  const request = useReviewUi((s) => s.paneRequest);
  const [handled, setHandled] = useState(request);
  if (request !== handled) {
    setHandled(request);
    if (request) {
      const side = request.side;
      if (!wide) setDrawer(side);
      else if (roomy) setRoomyOpen((o) => ({ ...o, [side]: true }));
      else setPanes((p) => (side === 'left' ? { ...p, leftOpen: true } : { ...p, rightOpen: true }));
    }
  }

  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(panes));
    } catch {
      /* private mode: sizes are not remembered */
    }
  }, [panes, storageKey]);

  const startResize = useCallback((side: 'left' | 'right') => (event: React.PointerEvent) => {
    event.preventDefault();
    const row = rowRef.current?.getBoundingClientRect();
    if (!row) return;
    const move = (e: PointerEvent) => {
      const max = row.width * 0.45;
      const width = side === 'left' ? e.clientX - row.left : row.right - e.clientX;
      setPanes((p) => ({ ...p, [side]: Math.round(Math.min(max, Math.max(MIN_WIDTH, width))) }));
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      document.body.style.cursor = '';
    };
    document.body.style.cursor = 'col-resize';
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  }, []);

  const toggle = (side: 'left' | 'right') => {
    if (!wide) setDrawer((d) => (d === side ? null : side));
    else if (roomy) setRoomyOpen((o) => ({ ...o, [side]: !o[side] }));
    else setPanes((p) => (side === 'left' ? { ...p, leftOpen: !p.leftOpen } : { ...p, rightOpen: !p.rightOpen }));
  };
  const showLeft = roomy ? roomyOpen.left : panes.leftOpen;
  const showRight = roomy ? roomyOpen.right : panes.rightOpen;
  const leftOpen = wide ? showLeft : drawer === 'left';
  const rightOpen = wide ? showRight : drawer === 'right';

  return (
    <div ref={rowRef} className="relative flex min-h-0 flex-1 overflow-hidden">
      {/* Left: source SOP */}
      {wide && showLeft && (
        <>
          <aside className="flex min-h-0 shrink-0 flex-col border-r border-border bg-card/40" style={{ width: panes.left }}>
            <PaneHeader pane={left} onClose={() => toggle('left')} side="left" />
            <div className="min-h-0 flex-1">{left.content}</div>
          </aside>
          <ResizeHandle onPointerDown={startResize('left')} />
        </>
      )}

      {/* Work area */}
      <main className="flex min-h-0 min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-border px-3 py-1">
          <PaneToggle open={leftOpen} side="left" label={left.short} icon={left.icon} onClick={() => toggle('left')} />
          <PaneToggle open={rightOpen} side="right" label={right.short} icon={right.icon} onClick={() => toggle('right')} />
        </div>
        <div className="min-h-0 flex-1 overflow-hidden">{children}</div>
      </main>

      {/* Right: template */}
      {wide && showRight && (
        <>
          <ResizeHandle onPointerDown={startResize('right')} />
          <aside className="flex min-h-0 shrink-0 flex-col border-l border-border bg-card/40" style={{ width: panes.right }}>
            <PaneHeader pane={right} onClose={() => toggle('right')} side="right" />
            <div className="min-h-0 flex-1">{right.content}</div>
          </aside>
        </>
      )}

      {/* Drawers on narrow screens */}
      {!wide && drawer && (
        <>
          <div className="absolute inset-0 z-20 bg-black/40" onClick={() => setDrawer(null)} />
          <aside
            className={clsx(
              'absolute inset-y-0 z-30 flex w-[min(440px,90%)] flex-col border-border bg-card shadow-panel',
              drawer === 'left' ? 'left-0 border-r' : 'right-0 border-l',
            )}
          >
            <PaneHeader pane={drawer === 'left' ? left : right} onClose={() => setDrawer(null)} side={drawer} drawer />
            <div className="min-h-0 flex-1">{(drawer === 'left' ? left : right).content}</div>
          </aside>
        </>
      )}
    </div>
  );
};

const PaneHeader: React.FC<{ pane: Pane; onClose: () => void; side: 'left' | 'right'; drawer?: boolean }> = ({
  pane,
  onClose,
  side,
  drawer,
}) => {
  const Icon = drawer ? X : side === 'left' ? PanelLeftClose : PanelRightClose;
  return (
    <div className="flex h-10 shrink-0 items-center justify-between border-b border-border px-3">
      <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-text-muted">
        {pane.icon}
        {pane.title}
      </div>
      <button type="button" onClick={onClose} title="Hide" className="grid size-7 place-items-center rounded text-text-muted hover:bg-white/5 hover:text-text-main">
        <Icon className="size-4" />
      </button>
    </div>
  );
};

const PaneToggle: React.FC<{
  open: boolean;
  side: 'left' | 'right';
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
}> = ({ open, side, label, icon, onClick }) => {
  const Icon = side === 'left' ? (open ? PanelLeftClose : PanelLeftOpen) : open ? PanelRightClose : PanelRightOpen;
  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        'flex h-7 items-center gap-1.5 rounded px-2 text-[11px] font-medium transition',
        open ? 'text-text-muted hover:text-text-main' : 'bg-primary/10 text-primary hover:bg-primary/15',
        side === 'right' && 'flex-row-reverse',
      )}
    >
      <Icon className="size-3.5" />
      {!open && icon}
      {open ? `Hide ${label}` : `Show ${label}`}
    </button>
  );
};

const ResizeHandle: React.FC<{ onPointerDown: (e: React.PointerEvent) => void }> = ({ onPointerDown }) => (
  <div
    role="separator"
    aria-orientation="vertical"
    onPointerDown={onPointerDown}
    className="group relative w-1 shrink-0 cursor-col-resize bg-transparent hover:bg-primary/30"
  >
    <div className="absolute inset-y-0 -left-1 -right-1" />
  </div>
);
