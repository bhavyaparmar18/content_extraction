import React, { useMemo, useState } from 'react';
import { ArrowLeft, Check, EyeOff, GripVertical, HelpCircle, MoreHorizontal } from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/ToastStack';
import { apiErrorDetails } from '@/lib/api';
import { focusProps, useActiveFocus } from '../focusStore';
import { useJobMutations } from '../hooks';
import {
  markReviewed,
  movePlacement,
  placementsAt,
  planSignature,
  setJustification,
  type Place,
  type Placement,
} from '../sectionPlanEdit';
import { humanize } from '../status';
import type { MigrationJob, QualityReport, SectionMapping, SectionPlan, SourceDocument, TemplateModel } from '../types';
import { blockingIssues } from '../report';
import { ValidationStrip } from './issues';
import { PlanToolbar } from './PlanToolbar';
import { JustifyDialog } from './JustifyDialog';

interface Props {
  job: MigrationJob;
  plan: SectionPlan;
  validation?: QualityReport;
  source: SourceDocument;
  template: TemplateModel;
  editable: boolean;
}

type DragItem = Placement & { from: Place };

/** ① Which source sections go into which template section. */
export const SectionPlanReview: React.FC<Props> = ({ job, plan, validation, source, template, editable }) => {
  const { success, error } = useToast();
  const mutations = useJobMutations(job.job_id);
  const [draft, setDraft] = useState(plan);
  const [saveErrors, setSaveErrors] = useState<string[]>([]);
  const [dragOver, setDragOver] = useState<string | null>(null);
  const [omitting, setOmitting] = useState<DragItem | null>(null);
  const [shown, setShown] = useState(plan);
  if (shown !== plan) {
    // A new plan version arrived (saved, or refreshed): edits start from it.
    setShown(plan);
    setDraft(plan);
    setSaveErrors([]);
  }

  const dirty = planSignature(draft) !== planSignature(plan);
  const sections = useMemo(() => new Map(source.sections.map((s) => [s.section_id, s])), [source]);
  const targets = useMemo(() => [...template.sections].sort((a, b) => a.display_order - b.display_order), [template]);
  const blocking = blockingIssues(validation);

  const move = (item: DragItem, to: Place, justification?: string) => {
    if (to.kind === 'omitted' && justification === undefined) {
      setOmitting(item);
      return;
    }
    setDraft((d) => movePlacement(d, template, source, item, item.from, to, justification));
  };

  const save = () =>
    mutations.saveSectionPlan.mutate(draft, {
      onSuccess: (saved) => {
        setSaveErrors([]);
        const gates = blockingIssues(saved.validation).length;
        success(gates ? `Saved as v${saved.version}; ${gates} blocking issue(s) to fix before approval.` : `Saved as v${saved.version}.`, 'Section plan saved');
      },
      onError: (e) => {
        setSaveErrors(apiErrorDetails(e).length ? apiErrorDetails(e) : [e.message]);
        error(e.message, 'Not saved');
      },
    });

  const approve = () =>
    mutations.approveSectionPlan.mutate(undefined, {
      onSuccess: () => success('The slot planner runs next.', 'Section plan approved'),
      onError: (e) => error(e.message, 'Not approved'),
    });

  const blockers = [
    ...(dirty ? ['Save or discard your changes first'] : []),
    ...blocking.map((i) => i.message),
  ];

  const placeName = (place: Place) =>
    place.kind === 'target' ? targets.find((t) => t.section_id === place.id)?.heading ?? place.id : place.kind === 'omitted' ? 'Omitted' : 'Not placed';

  const chip = (item: Placement, from: Place) => (
    <SourceChip
      key={`${item.sectionId}:${item.unitIds?.join(',') ?? ''}`}
      item={item}
      from={from}
      section={sections.get(item.sectionId)}
      targetId={from.kind === 'target' ? from.id : undefined}
      editable={editable}
      moveOptions={[
        ...targets.map((t) => ({ place: { kind: 'target', id: t.section_id } as Place, label: `${t.number ? `${t.number} ` : ''}${t.heading}` })),
        { place: { kind: 'unplaced' } as Place, label: 'Not placed' },
        { place: { kind: 'omitted' } as Place, label: 'Omit (with a justification)…' },
      ]}
      onMove={(to) => move({ ...item, from }, to)}
    />
  );

  const dropProps = (key: string, to: Place) =>
    editable
      ? {
          onDragOver: (e: React.DragEvent) => {
            e.preventDefault();
            setDragOver(key);
          },
          onDragLeave: () => setDragOver((k) => (k === key ? null : k)),
          onDrop: (e: React.DragEvent) => {
            e.preventDefault();
            setDragOver(null);
            const raw = e.dataTransfer.getData('application/x-source-section');
            if (raw) move(JSON.parse(raw) as DragItem, to);
          },
        }
      : {};

  const unplaced = placementsAt(draft, { kind: 'unplaced' }, source);
  const omitted = placementsAt(draft, { kind: 'omitted' }, source);

  return (
    <div className="flex h-full flex-col">
      <PlanToolbar
        title="Section mapping"
        description="Which sections of the SOP go into which section of the template. Drag a source section to another row, or use its menu. Hover a row to see both sides in the panes."
        plan={plan}
        editable={editable}
        dirty={dirty}
        saving={mutations.saveSectionPlan.isPending}
        approving={mutations.approveSectionPlan.isPending}
        approveBlockers={editable ? blockers : []}
        onSave={save}
        onDiscard={() => setDraft(plan)}
        onApprove={approve}
      />

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
        <ValidationStrip report={validation} where={(i) => (i.target_section_id ? placeName({ kind: 'target', id: i.target_section_id }) : undefined)} />
        {saveErrors.length > 0 && (
          <div className="error-panel text-xs">
            <div className="mb-1 font-medium text-danger">The server refused the plan</div>
            <ul className="list-disc space-y-0.5 pl-4 text-text-muted">{saveErrors.map((m) => <li key={m}>{m}</li>)}</ul>
          </div>
        )}

        {(unplaced.length > 0 || dragOver === 'unplaced') && (
          <div
            {...dropProps('unplaced', { kind: 'unplaced' })}
            className={clsx('rounded-lg border border-dashed p-3', dragOver === 'unplaced' ? 'border-primary bg-primary/5' : 'border-warning/50 bg-warning/[0.04]')}
          >
            <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-warning">
              <HelpCircle className="size-3.5" /> Not placed: {unplaced.length} source section(s) go nowhere yet
            </div>
            <div className="flex flex-wrap gap-1.5">{unplaced.map((p) => chip(p, { kind: 'unplaced' }))}</div>
          </div>
        )}

        <div className="overflow-hidden rounded-lg border border-border">
          <div className="grid grid-cols-[minmax(0,2fr)_20px_minmax(0,3fr)_minmax(140px,1fr)] items-center gap-3 border-b border-border bg-black/10 px-3 py-2 text-[11px] font-medium uppercase tracking-wider text-text-muted">
            <span>Template section</span>
            <span />
            <span>From the SOP</span>
            <span>Mapping</span>
          </div>
          {targets.map((target) => {
            const place: Place = { kind: 'target', id: target.section_id };
            const mappings = draft.mappings.filter((m) => m.target_section_id === target.section_id);
            const placements = placementsAt(draft, place, source);
            return (
              <MappingRow
                key={target.section_id}
                targetId={target.section_id}
                title={`${target.number ? `${target.number} ` : ''}${target.heading}`}
                required={!!target.required}
                purpose={target.purpose_instruction}
                mappings={mappings}
                sourceIds={placements.map((p) => p.sectionId)}
                dropping={dragOver === target.section_id}
                dropProps={dropProps(target.section_id, place)}
                editable={editable}
                onMarkReviewed={() => setDraft((d) => markReviewed(d, target.section_id))}
              >
                {placements.length ? placements.map((p) => chip(p, place)) : (
                  <span className="text-[11px] italic text-text-muted">
                    {target.required ? 'No source content: the draft will show a gap here' : 'No source content: this optional section is removed'}
                  </span>
                )}
              </MappingRow>
            );
          })}
        </div>

        {(omitted.length > 0 || dragOver === 'omitted') && (
          <div {...dropProps('omitted', { kind: 'omitted' })} className={clsx('rounded-lg border p-3', dragOver === 'omitted' ? 'border-primary bg-primary/5' : 'border-border')}>
            <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-text-muted">
              <EyeOff className="size-3.5" /> Left out of the migrated SOP
            </div>
            <div className="space-y-2">
              {omitted.map((p) => {
                const m = draft.mappings.find((x) => x.mapping_type === 'omit' && x.source_section_ids.includes(p.sectionId));
                return (
                  <div key={p.sectionId} className="flex flex-wrap items-start gap-2">
                    {chip(p, { kind: 'omitted' })}
                    <input
                      className="field h-8 min-w-[240px] flex-1 text-xs"
                      value={m?.justification ?? ''}
                      disabled={!editable}
                      placeholder="Why is this left out? (required)"
                      onChange={(e) => setDraft((d) => setJustification(d, p.sectionId, e.target.value))}
                    />
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      <JustifyDialog
        open={!!omitting}
        title="Leave this section out?"
        description={omitting ? `${sections.get(omitting.sectionId)?.heading ?? omitting.sectionId} will not appear in the migrated SOP. Say why, for the audit trail.` : ''}
        onCancel={() => setOmitting(null)}
        onConfirm={(note) => {
          if (omitting) move(omitting, { kind: 'omitted' }, note);
          setOmitting(null);
        }}
      />
    </div>
  );
};

const MappingRow: React.FC<{
  targetId: string;
  title: string;
  required: boolean;
  purpose?: string;
  mappings: SectionMapping[];
  sourceIds: string[];
  dropping: boolean;
  dropProps: object;
  editable: boolean;
  onMarkReviewed: () => void;
  children: React.ReactNode;
}> = ({ targetId, title, required, purpose, mappings, sourceIds, dropping, dropProps, editable, onMarkReviewed, children }) => {
  const focus = useActiveFocus();
  const active = focus?.targetSectionId === targetId;
  const main = mappings[0];
  const needsReview = mappings.some((m) => m.status === 'needs_review');
  const confidence = mappings.find((m) => m.confidence != null)?.confidence;
  const reasons = [...new Set(mappings.map((m) => m.reason).filter(Boolean))];

  return (
    <div
      {...dropProps}
      onMouseEnter={focusProps({ targetSectionId: targetId, sourceSectionIds: sourceIds }).onMouseEnter}
      onMouseLeave={focusProps({}).onMouseLeave}
      className={clsx(
        'grid grid-cols-[minmax(0,2fr)_20px_minmax(0,3fr)_minmax(140px,1fr)] items-start gap-3 border-b border-border px-3 py-2.5 last:border-b-0 transition-colors',
        active && 'bg-primary/[0.05]',
        dropping && 'bg-primary/10 ring-1 ring-inset ring-primary',
        needsReview && !active && 'bg-warning/[0.03]',
      )}
    >
      <div
        className="min-w-0 cursor-pointer"
        onClick={focusProps({ targetSectionId: targetId, sourceSectionIds: sourceIds }).onClick}
      >
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-semibold text-text-main">{title}</span>
          {required && <span className="chip border-primary/30 bg-primary/10 text-primary">required</span>}
        </div>
        {purpose && <p className="mt-0.5 line-clamp-2 text-[11px] text-text-muted" title={purpose}>{purpose}</p>}
      </div>
      <ArrowLeft className="mt-0.5 size-4 text-text-muted/60" />
      <div className="min-w-0">
        <div className="flex flex-wrap gap-1.5">{children}</div>
        {reasons.length > 0 && <p className="mt-1.5 line-clamp-2 text-[11px] text-text-muted" title={reasons.join('\n')}>{reasons.join(' · ')}</p>}
      </div>
      <div className="space-y-1 text-[11px]">
        <div className="flex flex-wrap items-center gap-1">
          {main && <span className="chip-muted">{humanize(main.mapping_type)}</span>}
          {main && main.status !== 'mapped' && (
            <span className={clsx('chip', needsReview ? 'border-warning/40 bg-warning/10 text-warning' : 'border-border bg-white/5 text-text-muted')}>
              {humanize(main.status)}
            </span>
          )}
          {mappings.some((m) => m.origin === 'human') && <span className="chip border-info/30 bg-info/10 text-info">reviewer</span>}
          {mappings.some((m) => m.origin === 'llm') && <span className="chip-muted">LLM</span>}
        </div>
        {confidence != null && (
          <div className="flex items-center gap-1.5" title={`Confidence ${Math.round(confidence * 100)}%`}>
            <div className="h-1 w-16 overflow-hidden rounded-full bg-white/10">
              <div className={clsx('h-full rounded-full', confidence >= 0.8 ? 'bg-primary' : confidence >= 0.5 ? 'bg-warning' : 'bg-danger')} style={{ width: `${confidence * 100}%` }} />
            </div>
            <span className="text-text-muted">{Math.round(confidence * 100)}%</span>
          </div>
        )}
        {needsReview && editable && (
          <Button size="sm" variant="secondary" className="h-6 px-2 text-[11px]" leftIcon={<Check className="size-3" />} onClick={onMarkReviewed}>
            Looks right
          </Button>
        )}
      </div>
    </div>
  );
};

const SourceChip: React.FC<{
  item: Placement;
  from: Place;
  section?: SourceDocument['sections'][number];
  targetId?: string;
  editable: boolean;
  moveOptions: { place: Place; label: string }[];
  onMove: (to: Place) => void;
}> = ({ item, from, section, targetId, editable, moveOptions, onMove }) => {
  const focus = useActiveFocus();
  const active = focus?.sourceSectionIds?.includes(item.sectionId) && !focus?.targetSectionId;
  const total = section?.units.length ?? 0;
  const count = item.unitIds?.length ?? total;
  return (
    <span
      draggable={editable}
      onDragStart={(e) => {
        e.dataTransfer.setData('application/x-source-section', JSON.stringify({ ...item, from }));
        e.dataTransfer.effectAllowed = 'move';
      }}
      {...focusProps({ sourceSectionIds: [item.sectionId], sourceUnitIds: item.unitIds, targetSectionId: targetId })}
      className={clsx(
        'group inline-flex max-w-full items-center gap-1 rounded-md border py-0.5 pl-1 pr-0.5 text-[11px] transition-colors',
        active ? 'border-primary/60 bg-primary/15' : 'border-border bg-card hover:border-primary/40',
        editable && 'cursor-grab active:cursor-grabbing',
      )}
      title={section ? `${section.section_id} · ${section.heading}` : item.sectionId}
    >
      {editable && <GripVertical className="size-3 shrink-0 text-text-muted/60" />}
      <span className="truncate text-text-main">
        {section?.number && <span className="mr-1 text-text-muted">{section.number}</span>}
        {section?.heading ?? item.sectionId}
      </span>
      <span className="shrink-0 text-[10px] text-text-muted">{item.unitIds ? `${count}/${total}` : total} u</span>
      {editable && (
        <span className="relative grid size-5 shrink-0 place-items-center rounded text-text-muted hover:bg-white/10 hover:text-text-main">
          <MoreHorizontal className="size-3.5" />
          <select
            aria-label="Move to"
            className="absolute inset-0 cursor-pointer opacity-0"
            value=""
            onClick={(e) => e.stopPropagation()}
            onChange={(e) => {
              const option = moveOptions[Number(e.target.value)];
              if (option) onMove(option.place);
            }}
          >
            <option value="" disabled>Move to…</option>
            {moveOptions.map((o, i) => (
              <option key={i} value={i} disabled={JSON.stringify(o.place) === JSON.stringify(from)}>{o.label}</option>
            ))}
          </select>
        </span>
      )}
    </span>
  );
};
