import React from 'react';
import { MigrationSection } from '@/types';
import { Layers, ChevronRight } from 'lucide-react';
import { clsx } from 'clsx';

interface SectionNavProps {
  sections: MigrationSection[];
  activeSectionIdx: number;
  onSelectSection: (index: number) => void;
}

export const SectionNav: React.FC<SectionNavProps> = ({
  sections,
  activeSectionIdx,
  onSelectSection,
}) => {
  return (
    <nav className="dashboard-card sticky top-6 max-h-[calc(100vh-140px)] overflow-y-auto p-3 space-y-1">
      <div className="flex items-center gap-2 px-3 py-2 text-xs font-bold uppercase tracking-wider text-text-muted border-b border-border mb-2">
        <Layers className="size-3.5 text-primary" />
        <span>Document Sections ({sections.length})</span>
      </div>

      <div className="space-y-1">
        {sections.map((sec, idx) => {
          const isActive = idx === activeSectionIdx;
          const elementCount = sec.elements?.length || 0;

          return (
            <button
              key={idx}
              type="button"
              onClick={() => onSelectSection(idx)}
              className={clsx(
                'flex w-full items-center justify-between rounded-lg px-3 py-2.5 text-left text-xs transition-all',
                isActive
                  ? 'bg-primary/15 text-primary font-semibold shadow-sm border border-primary/30'
                  : 'text-text-muted hover:bg-white/5 hover:text-text-main border border-transparent'
              )}
            >
              <div className="flex items-center gap-2 min-w-0 pr-2">
                <span
                  className={clsx(
                    'grid size-5 shrink-0 place-items-center rounded text-[10px] font-mono',
                    isActive ? 'bg-primary text-slate-950 font-bold' : 'bg-white/5 text-text-muted'
                  )}
                >
                  {sec.section_number || idx}
                </span>
                <span className="truncate text-xs leading-tight">
                  {sec.title || `Section ${sec.section_number || idx}`}
                </span>
              </div>

              <div className="flex items-center gap-1 shrink-0 text-[10px] opacity-70">
                <span>{elementCount}</span>
                {isActive && <ChevronRight className="size-3 text-primary" />}
              </div>
            </button>
          );
        })}
      </div>
    </nav>
  );
};
