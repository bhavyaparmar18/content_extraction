import React from 'react';
import { X } from 'lucide-react';
import { clsx } from 'clsx';
import { focusProps, useActiveFocus } from '../focusStore';
import { unitText } from '../report';
import type { GwpRule, SourceUnit } from '../types';

/** One source passage, short: its ID and the start of its text. Hover or click shows it in the SOP pane. */
export const UnitSnippet: React.FC<{
  unitId: string;
  unit?: SourceUnit;
  targetSectionId?: string;
  slotId?: string;
  onRemove?: () => void;
  trailing?: React.ReactNode;
  className?: string;
}> = ({ unitId, unit, targetSectionId, slotId, onRemove, trailing, className }) => {
  const focus = useActiveFocus();
  const active = focus?.sourceUnitIds?.includes(unitId);
  const text = unit ? unitText(unit) : '(passage not in the source model)';
  return (
    <div
      {...focusProps({ sourceUnitIds: [unitId], sourceSectionIds: unit ? [unit.section_id] : undefined, targetSectionId, slotId })}
      className={clsx(
        'group flex cursor-pointer items-start gap-2 rounded px-2 py-1 text-[11px] leading-relaxed transition-colors',
        active ? 'bg-primary/10 ring-1 ring-primary/50' : 'hover:bg-white/[0.04]',
        className,
      )}
    >
      <span className="unit-id mt-px shrink-0">{unitId}</span>
      <span className="min-w-0 flex-1 text-text-main/90">
        {unit && unit.unit_type !== 'paragraph' && <span className="chip-muted mr-1 align-[1px]">{unit.unit_type.replace(/_/g, ' ')}</span>}
        <span className="line-clamp-2">{text}</span>
      </span>
      {trailing}
      {onRemove && (
        <button
          type="button"
          title="Take this passage out of the slot"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="grid size-5 shrink-0 place-items-center rounded text-text-muted opacity-0 hover:bg-danger/15 hover:text-danger group-hover:opacity-100"
        >
          <X className="size-3" />
        </button>
      )}
    </div>
  );
};

/** GWP or preservation rule IDs, with the rule text on hover. */
export const RuleChips: React.FC<{ ids?: string[]; rules: Map<string, GwpRule>; max?: number }> = ({ ids, rules, max = 6 }) => {
  if (!ids?.length) return null;
  const shown = ids.slice(0, max);
  return (
    <span className="inline-flex flex-wrap gap-1">
      {shown.map((id) => (
        <span key={id} className="chip-muted cursor-help font-mono" title={rules.get(id)?.text ?? id}>
          {id}
        </span>
      ))}
      {ids.length > max && (
        <span className="chip-muted cursor-help" title={ids.slice(max).map((id) => `${id}: ${rules.get(id)?.text ?? ''}`).join('\n')}>
          +{ids.length - max}
        </span>
      )}
    </span>
  );
};

/** A compact select styled like a chip (assign a passage, change an action). */
export const ChipSelect: React.FC<React.SelectHTMLAttributes<HTMLSelectElement>> = ({ className, children, ...props }) => (
  <select
    {...props}
    onClick={(e) => e.stopPropagation()}
    className={clsx(
      'h-6 min-w-0 max-w-full cursor-pointer truncate rounded border border-border bg-card py-0 pl-1.5 pr-6 text-[11px] text-text-main focus:border-primary focus:ring-0',
      className,
    )}
  >
    {children}
  </select>
);
