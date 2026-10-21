import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, CheckCircle2, Info, Loader2, ShieldAlert, Wand2, X } from 'lucide-react';
import { clsx } from 'clsx';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/ToastStack';
import type { RegionDecision, TemplateReadinessReport, TemplateRecord } from '@/types';

const STATUS: Record<TemplateReadinessReport['status'], { label: string; hint: string; tone: string }> = {
  ready: { label: 'Ready for migration', hint: 'SOPs can be migrated onto this template.', tone: 'border-primary/30 bg-primary/10 text-primary' },
  needs_normalization: {
    label: 'Not prepared yet',
    hint: 'Prepare it: every instruction slot gets a marker the migration fills.',
    tone: 'border-warning/30 bg-warning/10 text-warning',
  },
  needs_review: {
    label: 'Needs your decisions',
    hint: 'Decide the regions below, then prepare it again.',
    tone: 'border-warning/30 bg-warning/10 text-warning',
  },
};

const DECISIONS: { value: RegionDecision; label: string; hint: string }[] = [
  { value: 'fixed', label: 'Fixed text', hint: 'kept as it is in every SOP' },
  { value: 'instruction', label: 'Instruction', hint: 'guidance for the author: followed, then removed' },
  { value: 'slot', label: 'Content slot', hint: 'filled with content from the SOP' },
  { value: 'conditional', label: 'Conditional', hint: 'kept, removed or completed depending on the SOP' },
];

/** Readiness badge for the Templates table; opens the dialog. */
export const ReadinessBadge: React.FC<{ template: TemplateRecord; onOpen: () => void }> = ({ template, onOpen }) => {
  if (template.status !== 'ready') return <span className="text-[11px] text-text-muted">Extract first</span>;
  const info = template.readiness_status ? STATUS[template.readiness_status] : null;
  return (
    <button
      type="button"
      onClick={onOpen}
      title="Readiness for migration"
      className={clsx(
        'inline-flex items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[10px] font-medium transition hover:brightness-110',
        info ? info.tone : 'border-slate-500/30 bg-slate-500/10 text-slate-400',
      )}
    >
      {template.readiness_status === 'ready' ? <CheckCircle2 className="size-3" /> : <AlertTriangle className="size-3" />}
      {info ? info.label : 'Not prepared'}
    </button>
  );
};

/**
 * Prepares a template for migration: detects its instruction slots, writes the normalized template the
 * migration fills, and shows what still blocks it (with the region decisions a reviewer can take here).
 */
export const TemplateReadinessDialog: React.FC<{ template: TemplateRecord | null; onClose: () => void }> = ({ template, onClose }) => {
  if (!template) return null;
  return <Dialog key={template.template_uid} template={template} onClose={onClose} />;
};

const Dialog: React.FC<{ template: TemplateRecord; onClose: () => void }> = ({ template, onClose }) => {
  const id = template.template_uid;
  const client = useQueryClient();
  const { success, error } = useToast();
  const [decisions, setDecisions] = useState<Record<string, RegionDecision>>({});
  const [result, setResult] = useState<{ wrapped: number; skipped: { slot_id: string; reason: string }[] } | null>(null);

  const readiness = useQuery({ queryKey: ['templateReadiness', id], queryFn: () => api.getTemplateReadiness(id) });
  const report = readiness.data;

  const prepare = useMutation({
    mutationFn: async (chosen: Record<string, RegionDecision>) => {
      if (Object.keys(chosen).length) {
        const config = await api.getTemplateSlotConfig(id);
        await api.saveTemplateSlotConfig(id, { ...config, regions: { ...config.regions, ...chosen } });
      }
      return api.normalizeTemplate(id);
    },
    onSuccess: (res) => {
      setDecisions({});
      setResult({ wrapped: res.wrapped_slots, skipped: res.skipped_slots });
      client.setQueryData(['templateReadiness', id], res.readiness);
      client.invalidateQueries({ queryKey: ['templates'] });
      client.invalidateQueries({ queryKey: ['readyTemplates'] });
      if (res.readiness_status === 'ready') success(`${res.wrapped_slots} slots prepared. SOPs can now be migrated onto it.`, 'Template ready');
      else error('Some points still block migration; see the dialog.', 'Template not ready yet');
    },
    onError: (e) => error(e instanceof Error ? e.message : String(e), 'Preparation failed'),
  });

  const blocking = (report?.issues ?? []).filter((i) => i.severity !== 'warning' && i.code !== 'ambiguous_region');
  const warnings = (report?.issues ?? []).filter((i) => i.severity === 'warning');
  const undecided = (report?.ambiguous_regions ?? []).filter((r) => !r.decision);
  const decided = (report?.ambiguous_regions ?? []).filter((r) => r.decision);
  const status = report ? STATUS[report.status] : null;
  const prepared = template.readiness_status != null || result != null;

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/60 p-4 backdrop-blur-sm" onMouseDown={onClose}>
      <div className="dashboard-card flex max-h-[85vh] w-full max-w-2xl flex-col" onMouseDown={(e) => e.stopPropagation()}>
        <div className="panel-header">
          <div>
            <div className="flex items-center gap-2 text-sm font-semibold text-text-main">
              <Wand2 className="size-4 text-primary" /> Prepare for migration
            </div>
            <div className="mt-0.5 text-[11px] text-text-muted">
              {template.template_name} · {id} v{template.template_version}
            </div>
          </div>
          <button type="button" onClick={onClose} className="grid size-7 place-items-center rounded text-text-muted hover:bg-white/5">
            <X className="size-4" />
          </button>
        </div>

        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5 text-xs">
          {readiness.isLoading || !report || !status ? (
            <div className="flex items-center gap-2 text-text-muted">
              <Loader2 className="size-4 animate-spin" /> Checking the template…
            </div>
          ) : (
            <>
              <div className={clsx('rounded-lg border px-3 py-2.5', status.tone)}>
                <div className="flex items-center gap-2 font-semibold">
                  {report.status === 'ready' ? <CheckCircle2 className="size-4" /> : <ShieldAlert className="size-4" />}
                  {prepared ? status.label : 'Not prepared yet'}
                </div>
                <p className="mt-0.5 text-text-main/80">
                  {prepared ? status.hint : 'Preparing detects every instruction slot and marks it, so the migration knows where each part of an SOP goes.'}
                </p>
                <p className="mt-1 text-[11px] text-text-muted">
                  {report.slot_count} instruction slots detected
                  {result && ` · ${result.wrapped} slot and region markers placed`}
                  {result && result.skipped.length > 0 && ` · ${result.skipped.length} skipped`}
                </p>
              </div>

              {undecided.length > 0 && (
                <section>
                  <h4 className="mb-1 font-semibold text-text-main">Decide what these parts of the template are ({undecided.length})</h4>
                  <p className="mb-2 text-[11px] text-text-muted">
                    The detector could not tell whether this text is fixed, guidance or a place for content. The suggestion is preselected.
                  </p>
                  <div className="space-y-2">
                    {undecided.map((region) => (
                      <div key={region.region_id} className="rounded-md border border-border p-2.5">
                        <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[10px] text-text-muted">
                          <span className="font-mono">{region.region_id}</span>
                          <span>· {region.kind}</span>
                          {region.section_key && <span>· {region.section_key}</span>}
                        </div>
                        <p className="mb-2 line-clamp-3 text-text-main">{region.text}</p>
                        <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-4">
                          {DECISIONS.map((d) => {
                            const chosen = (decisions[region.region_id] ?? region.suggestion) === d.value;
                            return (
                              <button
                                key={d.value}
                                type="button"
                                title={d.hint}
                                onClick={() => setDecisions((all) => ({ ...all, [region.region_id]: d.value }))}
                                className={clsx(
                                  'rounded border px-2 py-1 text-[11px] transition',
                                  chosen ? 'border-primary/60 bg-primary/10 text-primary' : 'border-border text-text-muted hover:bg-white/5',
                                )}
                              >
                                {d.label}
                                {region.suggestion === d.value && <span className="ml-1 opacity-70">(suggested)</span>}
                              </button>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {prepared && blocking.length > 0 && (
                <section>
                  <h4 className="mb-1.5 font-semibold text-text-main">Still blocking ({blocking.length})</h4>
                  <ul className="space-y-1">
                    {blocking.map((issue, i) => (
                      <li key={i} className="flex gap-2 rounded-md border border-danger/25 bg-danger/[0.04] px-2.5 py-1.5">
                        <AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-danger" />
                        <span>
                          {issue.ref && <span className="mr-1 font-mono text-[10px] text-text-muted">{issue.ref}</span>}
                          {issue.message}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {result && result.skipped.length > 0 && (
                <section>
                  <h4 className="mb-1.5 font-semibold text-text-main">Slots that could not be marked</h4>
                  <ul className="space-y-1 text-text-muted">
                    {result.skipped.map((s) => <li key={s.slot_id}><span className="font-mono text-[10px]">{s.slot_id}</span>: {s.reason}</li>)}
                  </ul>
                </section>
              )}

              {decided.length > 0 && (
                <section>
                  <h4 className="mb-1.5 font-semibold text-text-main">Decisions already taken</h4>
                  <ul className="space-y-0.5 text-text-muted">
                    {decided.map((r) => (
                      <li key={r.region_id}>
                        <span className="font-mono text-[10px]">{r.region_id}</span> → {DECISIONS.find((d) => d.value === r.decision)?.label ?? r.decision}:{' '}
                        <span className="text-text-main/80">{r.text.slice(0, 90)}{r.text.length > 90 ? '…' : ''}</span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {warnings.length > 0 && (
                <details className="text-text-muted">
                  <summary className="cursor-pointer select-none">{warnings.length} note(s) that do not block migration</summary>
                  <ul className="mt-1.5 list-disc space-y-0.5 pl-5">{warnings.map((w, i) => <li key={i}>{w.message}</li>)}</ul>
                </details>
              )}

              <p className="flex gap-1.5 text-[11px] text-text-muted">
                <Info className="mt-0.5 size-3 shrink-0" />
                Decisions are saved in data/template_config/{id}.json. Prepare again after re-extracting or replacing the template.
              </p>
            </>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-3">
          <Button variant="ghost" size="sm" onClick={onClose}>Close</Button>
          <Button
            variant="primary"
            size="sm"
            leftIcon={<Wand2 className="size-3.5" />}
            isLoading={prepare.isPending}
            disabled={!report}
            onClick={() => {
              // Undecided regions take the suggestion unless the reviewer chose otherwise.
              prepare.mutate(Object.fromEntries(undecided.map((r) => [r.region_id, decisions[r.region_id] ?? r.suggestion])));
            }}
          >
            {prepared ? 'Prepare again' : 'Prepare for migration'}
          </Button>
        </div>
      </div>
    </div>
  );
};
