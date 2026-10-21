import React, { useEffect, useMemo, useRef, useState } from 'react';
import { ChevronRight, History, ListChecks, Pencil, RefreshCw, ShieldAlert } from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/ToastStack';
import { focusProps, useFocusStore, useReviewUi } from '../focusStore';
import { useJobMutations, useSourceIndex, type SourceIndex } from '../hooks';
import { humanize, permissions } from '../status';
import type { MigrationJob, QualityReport, SectionDraft, SlotPlan, SourceDocument, TemplateModel, ValidationIssue } from '../types';
import { DraftVersions } from './DraftVersions';
import { blockingIssues, openIssues } from '../report';
import { SlotDraftView } from './SlotDraftView';
import { SlotEditor } from './SlotEditor';

interface Props {
  job: MigrationJob;
  drafts: SectionDraft[];
  report?: QualityReport;
  slotPlan?: SlotPlan;
  source: SourceDocument;
  template: TemplateModel;
  assetBase: string;
}

/** ③ The drafted SOP in template order, with its issues; slots can be edited and issues resolved. */
export const DraftReview: React.FC<Props> = ({ job, drafts, report, slotPlan, source, template, assetBase }) => {
  const can = permissions(job);
  const index = useSourceIndex(source);
  const [editing, setEditing] = useState<string | null>(null);
  const [history, setHistory] = useState<string | null>(null);
  const docRef = useRef<HTMLDivElement>(null);
  const pinned = useFocusStore((s) => s.pinned);
  const pin = useFocusStore((s) => s.pin);
  const { setRightTab, showPane } = useReviewUi.getState();
  const showIssues = () => {
    setRightTab('issues');
    showPane('right');
  };

  const draftBySection = useMemo(() => new Map(drafts.map((d) => [d.target_section_id, d])), [drafts]);
  const sections = useMemo(() => [...template.sections].sort((a, b) => a.display_order - b.display_order), [template]);
  const palette = useMemo(() => new Map(template.callout_palette.map((c) => [c.kind as string, c])), [template]);
  const issuesByClaim = useMemo(() => {
    const map = new Map<string, ValidationIssue[]>();
    openIssues(report).forEach((i) => i.claim_ids?.forEach((id) => map.set(id, [...(map.get(id) ?? []), i])));
    return map;
  }, [report]);
  const claimsByUnit = useMemo(() => {
    const map = new Map<string, string>();
    drafts.forEach((d) => d.slots.forEach((s) => s.claims.forEach((c) => c.source_unit_ids.forEach((u) => !map.has(u) && map.set(u, c.claim_id)))));
    return map;
  }, [drafts]);

  // A click elsewhere (an issue, the template, a source passage) brings its place in the draft into view.
  useEffect(() => {
    if (!pinned || !docRef.current) return;
    const claimId = pinned.claimId ?? (pinned.origin === 'source' ? pinned.sourceUnitIds?.map((u) => claimsByUnit.get(u)).find(Boolean) : undefined);
    const selector = claimId
      ? `[data-claim-id="${claimId}"]`
      : pinned.slotId
        ? `[data-slot-anchor="${pinned.slotId}"]`
        : pinned.targetSectionId
          ? `[data-draft-section="${pinned.targetSectionId}"]`
          : null;
    if (!selector || (pinned.origin === 'work' && !pinned.issueId)) return;
    docRef.current.querySelector<HTMLElement>(selector)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [pinned, claimsByUnit]);

  const openIssue = (issue: ValidationIssue) => {
    showIssues();
    pin({ issueId: issue.issue_id, targetSectionId: issue.target_section_id, slotId: issue.slot_id, claimId: issue.claim_ids?.[0], sourceUnitIds: issue.unit_ids, origin: 'work' });
  };

  return (
    <div className="flex h-full flex-col">
      <GateSummary job={job} report={report} onShowIssues={showIssues} />
      <div className="flex min-h-0 flex-1">
        <div ref={docRef} className="min-w-0 flex-1 overflow-y-auto">
          <SectionJump sections={sections.filter((s) => draftBySection.has(s.section_id))} container={docRef} />
          <div className="mx-auto max-w-3xl space-y-8 py-4 pl-5 pr-12">
            {sections.map((section) => {
              const draft = draftBySection.get(section.section_id);
              if (!draft) return null;
              const slotOrder = new Map(section.slots.map((s) => [s.slot_id, s.display_order]));
              const slots = [...draft.slots].sort((a, b) => (slotOrder.get(a.slot_id) ?? 0) - (slotOrder.get(b.slot_id) ?? 0));
              const heading = `${section.number ? `${section.number} ` : ''}${section.heading}`;
              const sectionIssues = openIssues(report).filter((i) => i.target_section_id === section.section_id);
              return (
                <section key={section.section_id} data-draft-section={section.section_id} className="scroll-mt-14">
                  <header className="mb-3 flex items-baseline gap-2 border-b border-border pb-1.5" {...focusProps({ targetSectionId: section.section_id })}>
                    <h3 className="cursor-pointer text-base font-semibold text-text-main">{heading}</h3>
                    <span className="chip-muted">v{draft.version}{draft.origin !== 'llm' ? ` · ${draft.origin}` : ''}</span>
                    {sectionIssues.length > 0 && (
                      <button type="button" onClick={() => openIssue(sectionIssues[0])} className={clsx('chip', blockingIssues({ ...report!, issues: sectionIssues }).length ? 'border-danger/40 bg-danger/10 text-danger' : 'border-warning/40 bg-warning/10 text-warning')}>
                        {sectionIssues.length} issue(s)
                      </button>
                    )}
                    {job.artifacts.filter((a) => a.kind === 'section_draft' && a.scope === section.section_id).length > 1 && (
                      <button type="button" onClick={() => setHistory(section.section_id)} className="ml-auto flex items-center gap-1 text-[11px] text-text-muted hover:text-text-main">
                        <History className="size-3" /> History
                      </button>
                    )}
                  </header>
                  <div className="space-y-4">
                    {slots.map((slot) => {
                      const target = section.slots.find((s) => s.slot_id === slot.slot_id);
                      const key = `${section.section_id}/${slot.slot_id}`;
                      return (
                        <div key={slot.slot_id} data-slot-anchor={slot.slot_id} className="scroll-mt-14">
                          <SlotLabel
                            label={target?.key ? humanize(target.key) : slot.slot_id}
                            instruction={target?.instruction}
                            focus={{ targetSectionId: section.section_id, slotId: slot.slot_id }}
                            onEdit={can.editDrafts && editing !== key ? () => setEditing(key) : undefined}
                          />
                          {editing === key ? (
                            <SlotEditor
                              jobId={job.job_id}
                              targetSectionId={section.section_id}
                              slot={slot}
                              unitChoices={unitChoices(slotPlan, section.section_id, slot.slot_id, index)}
                              index={index}
                              onDone={() => setEditing(null)}
                            />
                          ) : (
                            <SlotDraftView
                              slot={slot}
                              targetSectionId={section.section_id}
                              index={index}
                              palette={palette}
                              issuesByClaim={issuesByClaim}
                              assetBase={assetBase}
                              onOpenIssue={openIssue}
                            />
                          )}
                        </div>
                      );
                    })}
                  </div>
                </section>
              );
            })}
          </div>
        </div>

      </div>

      {history && (
        <DraftVersions
          job={job}
          sectionId={history}
          heading={template.sections.find((s) => s.section_id === history)?.heading ?? history}
          onClose={() => setHistory(null)}
        />
      )}
    </div>
  );
};

const GateSummary: React.FC<{ job: MigrationJob; report?: QualityReport; onShowIssues: () => void }> = ({ job, report, onShowIssues }) => {
  const { success, error } = useToast();
  const { retry } = useJobMutations(job.job_id);
  const can = permissions(job);
  const blocking = blockingIssues(report).length;
  const toCheck = openIssues(report).length - blocking;
  const risk = Object.keys(report?.high_risk_units ?? {}).length;
  const scores = Object.entries(report?.soft_scores ?? {}).filter(([k]) => k !== 'unit_coverage');

  const recheck = () =>
    retry.mutate('VALIDATING', {
      onSuccess: () => success('Validation, assembly and rendering run again on your edits.', 'Re-check started'),
      onError: (e) => error(e.message, 'Re-check not started'),
    });

  return (
    <div className="shrink-0 border-b border-border">
      {job.status === 'MANUALLY_EDITED' && (
        <div className="flex flex-wrap items-center gap-3 border-b border-warning/30 bg-warning/[0.07] px-4 py-2 text-xs">
          <Pencil className="size-3.5 text-warning" />
          <span className="flex-1 text-text-main">
            You edited the draft. The issues below are from before your edits; re-check to validate, assemble and render it again.
          </span>
          <Button size="sm" variant="primary" leftIcon={<RefreshCw className="size-3.5" />} onClick={recheck} isLoading={retry.isPending} disabled={!can.recheck}>
            Re-check and re-render
          </Button>
        </div>
      )}
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 px-4 py-2.5">
        <Metric label="Blocking" value={blocking} tone={blocking ? 'danger' : 'ok'} />
        <Metric label="To check" value={toCheck} tone={toCheck ? 'warning' : 'ok'} />
        <Metric label="Source covered" value={`${Math.round((report?.unit_coverage ?? 0) * 100)}%`} tone={(report?.unit_coverage ?? 0) >= 0.98 ? 'ok' : 'warning'} />
        {risk > 0 && (
          <span className="flex items-center gap-1.5 text-xs text-text-muted">
            <ShieldAlert className="size-3.5 text-warning" /> {risk} high-risk passage(s)
          </span>
        )}
        <div className="flex flex-wrap gap-1">
          {scores.map(([k, v]) => (
            <span key={k} className="chip-muted" title={k}>{humanize(k)}: {v <= 1 && v >= 0 && !k.includes('grade') && !k.includes('flesch') ? `${Math.round(v * 100)}%` : v.toFixed(1)}</span>
          ))}
        </div>
        <Button size="sm" variant="secondary" className="ml-auto" leftIcon={<ListChecks className="size-3.5" />} onClick={onShowIssues}>
          Issues
        </Button>
      </div>
    </div>
  );
};

const Metric: React.FC<{ label: string; value: React.ReactNode; tone: 'ok' | 'warning' | 'danger' }> = ({ label, value, tone }) => (
  <div className="flex items-baseline gap-1.5">
    <span className={clsx('text-lg font-semibold', tone === 'danger' ? 'text-danger' : tone === 'warning' ? 'text-warning' : 'text-primary')}>{value}</span>
    <span className="text-[11px] text-text-muted">{label}</span>
  </div>
);

const SlotLabel: React.FC<{
  label: string;
  instruction?: string;
  focus: { targetSectionId: string; slotId: string };
  onEdit?: () => void;
}> = ({ label, instruction, focus, onEdit }) => {
  const [open, setOpen] = useState(false);
  return (
    <div className="group mb-1 flex flex-wrap items-center gap-1.5 text-[11px] text-text-muted" {...focusProps(focus)}>
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex items-center gap-1 font-medium uppercase tracking-wide hover:text-text-main" title="Template instruction">
        <ChevronRight className={clsx('size-3 transition-transform', open && 'rotate-90')} />
        {label}
      </button>
      {onEdit && (
        <button type="button" onClick={onEdit} className="flex items-center gap-1 rounded px-1.5 py-0.5 opacity-0 hover:bg-white/5 hover:text-text-main group-hover:opacity-100">
          <Pencil className="size-3" /> Edit
        </button>
      )}
      {open && instruction && <p className="basis-full rounded border border-dashed border-border px-2 py-1 normal-case leading-relaxed">{instruction}</p>}
    </div>
  );
};

const SectionJump: React.FC<{ sections: TemplateModel['sections']; container: React.RefObject<HTMLDivElement | null> }> = ({ sections, container }) => (
  <div className="sticky top-0 z-10 flex items-center gap-1 overflow-x-auto border-b border-border bg-app/95 px-4 py-1.5 backdrop-blur">
    {sections.map((s) => (
      <button
        key={s.section_id}
        type="button"
        onClick={() => container.current?.querySelector(`[data-draft-section="${s.section_id}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })}
        className="shrink-0 rounded px-2 py-0.5 text-[11px] text-text-muted hover:bg-white/5 hover:text-text-main"
      >
        {s.number ?? ''} {s.heading.length > 22 ? `${s.heading.slice(0, 20)}…` : s.heading}
      </button>
    ))}
  </div>
);

/** Passages a slot's claims may cite: the slot's own (slot plan) first, then the rest of its section's. */
function unitChoices(slotPlan: SlotPlan | undefined, sectionId: string, slotId: string, index: SourceIndex): string[] {
  const section = slotPlan?.sections.find((s) => s.target_section_id === sectionId);
  const own = section?.slot_mappings.find((m) => m.slot_id === slotId)?.source_unit_ids ?? [];
  const rest = (section?.source_section_ids ?? []).flatMap((id) => index.sections.get(id)?.units.map((u) => u.unit_id) ?? []);
  return [...new Set([...own, ...rest])];
}
