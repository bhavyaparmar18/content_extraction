import React, { useMemo, useRef, useState } from 'react';
import { clsx } from 'clsx';
import { migrationsApi } from '../api';
import { focusProps, useActiveFocus } from '../focusStore';
import { humanize } from '../status';
import type { CalloutStyle, TargetSlot, TemplateModel } from '../types';
import { DocxViewer } from './DocxViewer';
import { PaneTabs, ScrollToFocus } from './paneParts';
import { PaneLoading } from './SourcePane';

type View = 'structured' | 'normalized' | 'original';

/** The target template: its sections and instruction slots, or the template file itself. */
export const TemplatePane: React.FC<{ jobId: string; template?: TemplateModel }> = ({ jobId, template }) => {
  const [view, setView] = useState<View>('structured');
  const focus = useActiveFocus();

  const highlights = useMemo(() => {
    if (!template || !focus) return [];
    const section = template.sections.find((s) => s.section_id === focus.targetSectionId);
    const slot = section?.slots.find((s) => s.slot_id === focus.slotId);
    if (slot) return [slot.instruction];
    return section ? [section.heading] : [];
  }, [template, focus]);

  return (
    <div className="flex h-full min-h-0 flex-col">
      <PaneTabs
        value={view}
        onChange={(v) => setView(v as View)}
        tabs={[
          { id: 'structured', label: 'Structured' },
          { id: 'normalized', label: 'Template' },
          { id: 'original', label: 'As uploaded' },
        ]}
        extra={template && <span className="text-[10px] text-text-muted">{template.template_id} v{template.template_version}</span>}
      />
      <div className="min-h-0 flex-1">
        {view === 'structured' ? (
          template ? <StructuredTemplate template={template} /> : <PaneLoading />
        ) : (
          <DocxViewer
            key={view}
            fileKey={['template', jobId, view]}
            load={() => migrationsApi.templateFile(jobId, view === 'original' ? 'original' : 'normalized')}
            highlights={highlights}
          />
        )}
      </div>
    </div>
  );
};

const StructuredTemplate: React.FC<{ template: TemplateModel }> = ({ template }) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const focus = useActiveFocus();
  const palette = new Map(template.callout_palette.map((c) => [c.kind, c]));
  const selector = focus?.origin === 'template'
    ? null
    : focus?.slotId
      ? `[data-slot-id="${focus.slotId}"]`
      : focus?.targetSectionId
        ? `[data-target-section-id="${focus.targetSectionId}"]`
        : null;

  return (
    <div ref={scrollRef} className="h-full space-y-3 overflow-y-auto px-3 py-3">
      <ScrollToFocus container={scrollRef} selector={selector} />
      {template.sections.map((section) => {
        const active = focus?.targetSectionId === section.section_id;
        return (
          <section
            key={section.section_id}
            data-target-section-id={section.section_id}
            className={clsx(
              'rounded-lg border p-2.5 transition-colors',
              active ? 'border-primary/50 bg-primary/[0.06]' : 'border-border bg-card/40',
            )}
          >
            <header className="cursor-pointer" {...focusProps({ targetSectionId: section.section_id }, 'template')}>
              <div className="flex items-baseline gap-2">
                <h4 className="text-[13px] font-semibold text-text-main">
                  {section.number && <span className="mr-1.5 text-text-muted">{section.number}</span>}
                  {section.heading}
                </h4>
                {section.required && <span className="chip border-primary/30 bg-primary/10 text-primary">required</span>}
                {section.optional_marker && <span className="chip-muted">optional</span>}
              </div>
              {section.purpose_instruction && (
                <p className="mt-1 text-[11px] leading-relaxed text-text-muted">{section.purpose_instruction}</p>
              )}
            </header>
            {section.slots.length > 0 && (
              <ul className="mt-2 space-y-1">
                {[...section.slots].sort((a, b) => a.display_order - b.display_order).map((slot) => (
                  <SlotRow
                    key={slot.slot_id}
                    slot={slot}
                    callout={slot.callout_kind ? palette.get(slot.callout_kind) : undefined}
                    active={focus?.slotId === slot.slot_id}
                  />
                ))}
              </ul>
            )}
            {!!section.conditional_regions?.length && (
              <div className="mt-2 space-y-1">
                {section.conditional_regions.map((r) => (
                  <div key={r.region_id} className="rounded border border-dashed border-border px-2 py-1 text-[11px] text-text-muted">
                    <span className="chip-muted mr-1">{r.kind === 'inline_choice' ? 'choice' : 'conditional'}</span>
                    {r.text}
                  </div>
                ))}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
};

const SlotRow: React.FC<{ slot: TargetSlot; callout?: CalloutStyle; active: boolean }> = ({ slot, callout, active }) => (
  <li
    data-slot-id={slot.slot_id}
    {...focusProps({ targetSectionId: slot.section_id, slotId: slot.slot_id }, 'template')}
    className={clsx(
      'cursor-pointer rounded-md border-l-2 px-2 py-1.5 text-[11px] leading-relaxed transition-colors hover:bg-white/[0.04]',
      active ? 'focus-ring border-primary' : 'border-border',
    )}
    style={callout ? { borderLeftColor: `#${callout.fill_hex}` } : undefined}
  >
    <div className="mb-0.5 flex flex-wrap items-center gap-1">
      <span className="font-medium text-text-main">{slot.key ? humanize(slot.key) : slot.slot_id}</span>
      <span className="chip-muted">{humanize(slot.content_type)}</span>
      {slot.required && <span className="chip border-primary/30 bg-primary/10 text-primary">required</span>}
      {callout && (
        <span className="chip border-border" style={{ backgroundColor: `#${callout.fill_hex}33` }}>
          {callout.label}
        </span>
      )}
    </div>
    <p className="text-text-muted">{slot.instruction}</p>
  </li>
);
