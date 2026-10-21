import React, { useMemo } from 'react';
import { ArrowRightLeft, Check, X, FileText } from 'lucide-react';
import { diffWords, type DiffPart } from '@/lib/diff';

interface CompareViewProps {
  originalText: string;
  modifiedText: string;
  originalLabel?: string;
  modifiedLabel?: string;
  /** Mark the words removed on the left and the words added on the right. */
  diff?: boolean;
}

/** One side of a word diff: the shared words plus this side's own ("removed" on the left, "added" on the right). */
export const DiffText: React.FC<{ parts: DiffPart[]; side: 'before' | 'after' }> = ({ parts, side }) => (
  <>
    {parts.map((part, i) =>
      part.type === 'same' ? (
        <span key={i}>{part.text}</span>
      ) : part.type === (side === 'before' ? 'removed' : 'added') ? (
        <mark
          key={i}
          className={side === 'before' ? 'rounded-sm bg-red-500/25 text-inherit line-through decoration-red-400/70' : 'rounded-sm bg-emerald-500/25 text-inherit'}
        >
          {part.text}
        </mark>
      ) : null,
    )}
  </>
);

export const CompareView: React.FC<CompareViewProps> = ({
  originalText,
  modifiedText,
  originalLabel = 'Source / Original Version',
  modifiedLabel = 'Draft / Proposed Version',
  diff = false,
}) => {
  const parts = useMemo(() => (diff ? diffWords(originalText, modifiedText) : null), [diff, originalText, modifiedText]);
  return (
    <div className="dashboard-card flex flex-col h-full overflow-hidden">
      <div className="flex items-center justify-between border-b border-border bg-card/60 px-4 py-2.5 text-xs">
        <div className="flex items-center gap-1.5 font-semibold text-text-main">
          <ArrowRightLeft className="size-3.5 text-primary" />
          <span>Side-by-Side Comparison</span>
        </div>
        <div className="flex items-center gap-3 text-[10px]">
          <span className="flex items-center gap-1 text-red-400">
            <span className="size-2 rounded-full bg-red-400" /> Removed
          </span>
          <span className="flex items-center gap-1 text-emerald-400">
            <span className="size-2 rounded-full bg-emerald-400" /> Added
          </span>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 divide-y md:divide-y-0 md:divide-x divide-border flex-1 overflow-auto text-xs">
        {/* Left: Original */}
        <div className="p-4 space-y-2 bg-red-500/[0.02]">
          <div className="font-semibold text-text-muted text-[11px] uppercase tracking-wider">
            {originalLabel}
          </div>
          <div className="font-mono text-xs whitespace-pre-wrap leading-relaxed text-text-main/80">
            {parts ? <DiffText parts={parts} side="before" /> : originalText || 'No source content'}
          </div>
        </div>

        {/* Right: Modified */}
        <div className="p-4 space-y-2 bg-emerald-500/[0.02]">
          <div className="font-semibold text-text-muted text-[11px] uppercase tracking-wider">
            {modifiedLabel}
          </div>
          <div className="font-mono text-xs whitespace-pre-wrap leading-relaxed text-text-main">
            {parts ? <DiffText parts={parts} side="after" /> : modifiedText || 'No modified content'}
          </div>
        </div>
      </div>
    </div>
  );
};
