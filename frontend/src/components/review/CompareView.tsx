import React from 'react';
import { ArrowRightLeft, Check, X, FileText } from 'lucide-react';

interface CompareViewProps {
  originalText: string;
  modifiedText: string;
  originalLabel?: string;
  modifiedLabel?: string;
}

export const CompareView: React.FC<CompareViewProps> = ({
  originalText,
  modifiedText,
  originalLabel = 'Source / Original Version',
  modifiedLabel = 'Draft / Proposed Version',
}) => {
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
            {originalText || 'No source content'}
          </div>
        </div>

        {/* Right: Modified */}
        <div className="p-4 space-y-2 bg-emerald-500/[0.02]">
          <div className="font-semibold text-text-muted text-[11px] uppercase tracking-wider">
            {modifiedLabel}
          </div>
          <div className="font-mono text-xs whitespace-pre-wrap leading-relaxed text-text-main">
            {modifiedText || 'No modified content'}
          </div>
        </div>
      </div>
    </div>
  );
};
