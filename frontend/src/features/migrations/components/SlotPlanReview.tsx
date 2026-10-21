import React, { useMemo, useState } from 'react';
import { AlertTriangle, Check, Flag, HelpCircle, Info } from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/ToastStack';
import { apiErrorDetails } from '@/lib/api';
import { focusProps, useActiveFocus, useFocusStore } from '../focusStore';
import { useJobMutations, useJobRules, useSourceIndex } from '../hooks';
import { assignUnit, markSlotReviewed, removeUnit, setAction, slotPlanSignature } from '../slotPlanEdit';
import { humanize } from '../status';
import type {
  MigrationAction,
  MigrationJob,
  QualityReport,
  SectionPlan,
  SectionSlotPlan,
  SlotMapping,
  SlotPlan,
  SourceDocument,
  TargetSection,
  TargetSlot,
  TemplateModel,
} from '../types';
import { blockingIssues } from '../report';
import { ValidationStrip } from './issues';
import { PlanToolbar } from './PlanToolbar';
import { ChipSelect, RuleChips, UnitSnippet } from './unitParts';

interface Props {
  job: MigrationJob;
  plan: SlotPlan;
  validation?: QualityReport;
  sectionPlan?: SectionPlan;
  source: SourceDocument;
  template: TemplateModel;
  editable: boolean;
}

const ACTIONS: { value: MigrationAction; label: string }[] = [
  { value: 'copy_verbatim', label: 'Copy as written' },
  { value: 'extract_and_rewrite', label: 'Rewrite (GWP)' },
  { value: 'extract_and_consolidate', label: 'Consolidate (GWP)' },
  { value: 'rewrite_as_ordered_procedure', label: 'Ordered procedure (GWP)' },
];

/** ② Which source passages fill which slot of each template section. */
export const SlotPlanReview: React.FC<Props> = ({ job, plan, validation, sectionPlan, source, template, editable }) => {
  const { success, error } = useToast();
  const mutations = useJobMutations(job.job_id);
  const rules = useJobRules(job.job_id, job);
  const index = useSourceIndex(source);
  const [draft, setDraft] = useState(plan);
  const [saveErrors, setSaveErrors] = useState<string[]>([]);
  const targets = useMemo(
    () => [...template.sections].sort((a, b) => a.display_order - b.display_order).filter((t) => plan.sections.some((s) => s.target_section_id === t.section_id)),
    [template, plan],
  );
  const [selected, setSelected] = useState<string>(() => firstToReview(plan, targets) ?? targets[0]?.section_id);
  const pinned = useFocusStore((s) => s.pinned);
  const [shown, setShown] = useState({ plan, pinned });
  if (shown.plan !== plan) {
    // A new plan version arrived (saved, or refreshed): edits start from it.
    setDraft(plan);
    setSaveErrors([]);
  }
  if (shown.pinned !== pinned && pinned?.targetSectionId && targets.some((t) => t.section_id === pinned.targetSectionId)) {
    // Follow a click elsewhere (an issue, the template pane) to its section.
    setSelected(pinned.targetSectionId);
  }
  if (shown.plan !== plan || shown.pinned !== pinned) setShown({ plan, pinned });

  const ctx = useMemo(
    () => ({
      template,
      seq: new Map([...index.units.values()].map((u) => [u.unit_id, u.seq])),
      defaultAction: (job.gwp_id ? 'extract_and_rewrite' : 'copy_verbatim') as MigrationAction,
    }),
    [template, index, job.gwp_id],
  );

  const dirty = slotPlanSignature(draft) !== slotPlanSignature(plan);
  const blocking = blockingIssues(validation);
  const section = draft.sections.find((s) => s.target_section_id === selected);
  const target = targets.find((t) => t.section_id === selected);

  const save = () =>
    mutations.saveSlotPlan.mutate(draft, {
      onSuccess: (saved) => {
        setSaveErrors([]);
        success(`Saved as v${saved.version}.`, 'Slot plan saved');
      },
      onError: (e) => {
        setSaveErrors(apiErrorDetails(e).length ? apiErrorDetails(e) : [e.message]);
        error(e.message, 'Not saved');
      },
    });
  const approve = () =>
    mutations.approveSlotPlan.mutate(undefined, {
      onSuccess: () => success('Drafting starts now; this page follows its progress.', 'Slot plan approved'),
      onError: (e) => error(e.message, 'Not approved'),
    });

  return (
    <div className="flex h-full flex-col">
      <PlanToolbar
        title="Slot mapping"
        description="Which passages of the SOP fill each instruction slot of the template. A passage can feed more than one slot. Hover a passage or a slot to see it in the panes."
        plan={plan}
        editable={editable}
        dirty={dirty}
        saving={mutations.saveSlotPlan.isPending}
        approving={mutations.approveSlotPlan.isPending}
        approveBlockers={editable ? [...(dirty ? ['Save or discard your changes first'] : []), ...blocking.map((i) => i.message)] : []}
        onSave={save}
        onDiscard={() => setDraft(plan)}
        onApprove={approve}
      >
        {plan.gwp_guide_id && <span>· rules {plan.gwp_guide_id === 'BASELINE' ? 'preservation only' : plan.gwp_guide_id}</span>}
      </PlanToolbar>

      <div className="flex min-h-0 flex-1">
        <nav className="w-52 shrink-0 space-y-0.5 overflow-y-auto border-r border-border p-2">
          {targets.map((t) => {
            const s = draft.sections.find((x) => x.target_section_id === t.section_id)!;
            const flags = attention(s);
            return (
              <button
                key={t.section_id}
                type="button"
                onClick={() => setSelected(t.section_id)}
                {...{ onMouseEnter: focusProps({ targetSectionId: t.section_id, sourceSectionIds: s.source_section_ids }).onMouseEnter, onMouseLeave: focusProps({}).onMouseLeave }}
                className={clsx(
                  'flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition',
                  selected === t.section_id ? 'bg-primary/10 text-text-main' : 'text-text-muted hover:bg-white/5 hover:text-text-main',
                )}
              >
                <span className="min-w-0 flex-1 truncate">
                  {t.number && <span className="mr-1 text-text-muted">{t.number}</span>}
                  {t.heading}
                </span>
                {flags > 0 && <span className="grid size-4 shrink-0 place-items-center rounded-full bg-warning/20 text-[9px] font-semibold text-warning">{flags}</span>}
              </button>
            );
          })}
        </nav>

        <div className="min-w-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
          <ValidationStrip report={validation} where={(i) => i.slot_id ?? i.target_section_id} />
          {saveErrors.length > 0 && (
            <div className="error-panel text-xs">
              <div className="mb-1 font-medium text-danger">The server refused the plan</div>
              <ul className="list-disc space-y-0.5 pl-4 text-text-muted">{saveErrors.map((m) => <li key={m}>{m}</li>)}</ul>
            </div>
          )}
          {section && target && (
            <SectionSlots
              key={section.target_section_id}
              section={section}
              target={target}
              sectionPlan={sectionPlan}
              source={source}
              index={index}
              rules={rules}
              editable={editable}
              onAssign={(slotId, unitId) => setDraft((d) => assignUnit(d, ctx, section.target_section_id, slotId, unitId))}
              onRemove={(slotId, unitId) => setDraft((d) => removeUnit(d, ctx, section.target_section_id, slotId, unitId))}
              onAction={(slotId, action) => setDraft((d) => setAction(d, section.target_section_id, slotId, action))}
              onReviewed={(slotId) => setDraft((d) => markSlotReviewed(d, section.target_section_id, slotId))}
            />
          )}
        </div>
      </div>
    </div>
  );
};

const SectionSlots: React.FC<{
  section: SectionSlotPlan;
  target: TargetSection;
  sectionPlan?: SectionPlan;
  source: SourceDocument;
  index: ReturnType<typeof useSourceIndex>;
  rules: ReturnType<typeof useJobRules>;
  editable: boolean;
  onAssign: (slotId: string, unitId: string) => void;
  onRemove: (slotId: string, unitId: string) => void;
  onAction: (slotId: string, action: MigrationAction) => void;
  onReviewed: (slotId: string) => void;
}> = ({ section, target, sectionPlan, source, index, rules, editable, onAssign, onRemove, onAction, onReviewed }) => {
  const scope = useMemo(() => unitsInScope(section, sectionPlan, source), [section, sectionPlan, source]);
  const slots = [...target.slots].sort((a, b) => a.display_order - b.display_order);
  const mappings = new Map(section.slot_mappings.map((m) => [m.slot_id, m]));
  const slotOptions = slots.map((s) => ({ id: s.slot_id, label: s.key ? humanize(s.key) : s.slot_id }));

  return (
    <div className="space-y-3">
      <div>
        <h3 className="text-sm font-semibold text-text-main">
          {target.number && <span className="mr-1.5 text-text-muted">{target.number}</span>}
          {target.heading}
        </h3>
        <div className="mt-1 flex flex-wrap items-center gap-1 text-[11px] text-text-muted">
          From
          {section.source_section_ids.map((id) => {
            const s = index.sections.get(id);
            return (
              <span key={id} className="chip-muted cursor-pointer" {...focusProps({ sourceSectionIds: [id] })}>
                {s?.number ? `${s.number} ` : ''}{s?.heading ?? id}
              </span>
            );
          })}
          {section.source_section_ids.length === 0 && <span className="italic">no source section</span>}
        </div>
        {!!section.notes?.length && (
          <ul className="mt-2 space-y-1">
            {section.notes.map((n) => (
              <li key={n} className="flex gap-1.5 text-[11px] text-text-muted"><Info className="mt-0.5 size-3 shrink-0 text-info" />{n}</li>
            ))}
          </ul>
        )}
      </div>

      {section.unplaced_unit_ids.length > 0 && (
        <div className="rounded-lg border border-dashed border-warning/50 bg-warning/[0.04] p-2.5">
          <div className="mb-1.5 flex items-center gap-1.5 text-xs font-medium text-warning">
            <HelpCircle className="size-3.5" /> {section.unplaced_unit_ids.length} passage(s) fit no slot yet
          </div>
          {section.unplaced_unit_ids.map((id) => (
            <UnitSnippet
              key={id}
              unitId={id}
              unit={index.units.get(id)}
              targetSectionId={target.section_id}
              trailing={editable && <AssignSelect options={slotOptions} onPick={(slotId) => onAssign(slotId, id)} />}
            />
          ))}
        </div>
      )}

      {slots.map((slot) => (
        <SlotCard
          key={slot.slot_id}
          slot={slot}
          mapping={mappings.get(slot.slot_id)}
          index={index}
          rules={rules}
          scope={scope}
          editable={editable}
          onAssign={(unitId) => onAssign(slot.slot_id, unitId)}
          onRemove={(unitId) => onRemove(slot.slot_id, unitId)}
          onAction={(action) => onAction(slot.slot_id, action)}
          onReviewed={() => onReviewed(slot.slot_id)}
        />
      ))}

      {(!!section.callout_assignments?.length || !!section.region_choices?.length) && (
        <div className="rounded-lg border border-border p-2.5 text-[11px]">
          <div className="mb-1.5 font-medium text-text-main">Also decided by the planner</div>
          {section.callout_assignments?.map((a, i) => (
            <div key={`c${i}`} className="mb-1 text-text-muted">
              <span className="chip-muted mr-1">callout: {humanize(a.kind)}</span>
              {a.unit_ids.join(', ')} · {a.reason}
            </div>
          ))}
          {section.region_choices?.map((r) => (
            <div key={r.region_id} className="mb-1 text-text-muted">
              <span className="chip-muted mr-1">template choice {r.region_id}</span>
              {r.choice ? `"${r.choice}"` : 'kept'} from {r.unit_ids.join(', ')}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

const SlotCard: React.FC<{
  slot: TargetSlot;
  mapping?: SlotMapping;
  index: ReturnType<typeof useSourceIndex>;
  rules: ReturnType<typeof useJobRules>;
  scope: string[];
  editable: boolean;
  onAssign: (unitId: string) => void;
  onRemove: (unitId: string) => void;
  onAction: (action: MigrationAction) => void;
  onReviewed: () => void;
}> = ({ slot, mapping, index, rules, scope, editable, onAssign, onRemove, onAction, onReviewed }) => {
  const focus = useActiveFocus();
  const active = focus?.slotId === slot.slot_id;
  const units = mapping?.source_unit_ids ?? [];
  const below = new Set(mapping?.below_unit_ids ?? []);
  const empty = units.length === 0;
  const missing = mapping?.status === 'source_content_not_found' || (empty && slot.required);
  const flagged = !!mapping?.requires_human_review || mapping?.status === 'needs_review';
  const available = scope.filter((u) => !units.includes(u));

  return (
    <div
      data-slot-card={slot.slot_id}
      className={clsx(
        'rounded-lg border transition-colors',
        active ? 'border-primary/50 bg-primary/[0.04]' : missing ? 'border-danger/30' : flagged ? 'border-warning/40' : 'border-border',
      )}
    >
      <div
        className="cursor-pointer border-b border-border px-3 py-2"
        {...focusProps({ targetSectionId: slot.section_id, slotId: slot.slot_id, sourceUnitIds: units.length ? units : undefined })}
      >
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-semibold text-text-main">{slot.key ? humanize(slot.key) : slot.slot_id}</span>
          <span className="chip-muted">{humanize(slot.content_type)}</span>
          {slot.required && <span className="chip border-primary/30 bg-primary/10 text-primary">required</span>}
          {slot.callout_kind && <span className="chip-muted">callout: {humanize(slot.callout_kind)}</span>}
          {mapping && mapping.status !== 'mapped' && (
            <span className={clsx('chip', missing ? 'border-danger/40 bg-danger/10 text-danger' : 'border-border bg-white/5 text-text-muted')}>
              {humanize(mapping.status)}
            </span>
          )}
          {flagged && <span className="chip border-warning/40 bg-warning/10 text-warning"><Flag className="size-2.5" /> check</span>}
          {mapping?.origin === 'human' && <span className="chip border-info/30 bg-info/10 text-info">reviewer</span>}
          <span className="ml-auto flex items-center gap-1.5">
            {!empty && (editable ? (
              <ChipSelect value={mapping?.migration_action} onChange={(e) => onAction(e.target.value as MigrationAction)} aria-label="Migration action">
                {ACTIONS.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
              </ChipSelect>
            ) : (
              <span className="chip-muted">{ACTIONS.find((a) => a.value === mapping?.migration_action)?.label ?? mapping?.migration_action}</span>
            ))}
          </span>
        </div>
        <p className="mt-1 text-[11px] leading-relaxed text-text-muted">{slot.instruction}</p>
        {mapping?.note && <p className="mt-1 text-[11px] italic text-text-muted">{mapping.note}</p>}
        {!!mapping?.rule_ids?.length && (
          <div className="mt-1.5 flex items-center gap-1.5 text-[10px] text-text-muted">
            Rules <RuleChips ids={mapping.rule_ids} rules={rules} />
          </div>
        )}
      </div>
      <div className="space-y-0.5 px-1.5 py-1.5">
        {units.map((id) => (
          <UnitSnippet
            key={id}
            unitId={id}
            unit={index.units.get(id)}
            targetSectionId={slot.section_id}
            slotId={slot.slot_id}
            onRemove={editable ? () => onRemove(id) : undefined}
            trailing={below.has(id) ? <span className="chip-muted shrink-0" title="Shown below the slot's table rows">below table</span> : undefined}
          />
        ))}
        {empty && (
          <div className={clsx('flex items-center gap-1.5 px-2 py-1 text-[11px]', missing ? 'text-danger' : 'text-text-muted')}>
            {missing && <AlertTriangle className="size-3" />}
            {missing ? 'No source content: the draft shows a gap the reviewer must fill or accept' : 'Empty: this optional slot is removed'}
          </div>
        )}
        {editable && (
          <div className="flex min-w-0 items-center gap-2 px-2 pb-0.5 pt-1">
            {available.length > 0 && (
              <ChipSelect value="" onChange={(e) => e.target.value && onAssign(e.target.value)} aria-label="Add a passage">
                <option value="">+ Add a passage…</option>
                {available.map((id) => {
                  const u = index.units.get(id);
                  return <option key={id} value={id}>{id} · {(u?.text ?? '').slice(0, 70)}</option>;
                })}
              </ChipSelect>
            )}
            {flagged && !missing && (
              <Button size="sm" variant="secondary" className="h-6 px-2 text-[11px]" leftIcon={<Check className="size-3" />} onClick={onReviewed}>
                Looks right
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};

const AssignSelect: React.FC<{ options: { id: string; label: string }[]; onPick: (id: string) => void }> = ({ options, onPick }) => (
  <ChipSelect value="" onChange={(e) => e.target.value && onPick(e.target.value)} aria-label="Assign to a slot" className="shrink-0">
    <option value="">Assign to…</option>
    {options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
  </ChipSelect>
);

/** Passages the section may use: its split units, or every unit of its source sections; plus any already used. */
function unitsInScope(section: SectionSlotPlan, sectionPlan: SectionPlan | undefined, source: SourceDocument): string[] {
  const split = sectionPlan?.mappings.find((m) => m.target_section_id === section.target_section_id && m.mapping_type === 'split');
  const ids = split?.unit_ids.length
    ? split.unit_ids
    : source.sections.filter((s) => section.source_section_ids.includes(s.section_id)).flatMap((s) => s.units.map((u) => u.unit_id));
  const used = section.slot_mappings.flatMap((m) => m.source_unit_ids);
  return [...new Set([...ids, ...used, ...section.unplaced_unit_ids])];
}

function attention(section: SectionSlotPlan): number {
  return (
    section.unplaced_unit_ids.length +
    section.slot_mappings.filter((m) => m.requires_human_review || m.status === 'needs_review' || m.status === 'source_content_not_found').length
  );
}

function firstToReview(plan: SlotPlan, targets: TargetSection[]): string | undefined {
  return targets.find((t) => {
    const s = plan.sections.find((x) => x.target_section_id === t.section_id);
    return s && attention(s) > 0;
  })?.section_id;
}
