import React, { useMemo, useState } from 'react';
import { ArrowDown, ArrowUp, Plus, Save, Trash2, X } from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/ToastStack';
import { apiErrorDetails } from '@/lib/api';
import { focusProps } from '../focusStore';
import { useJobMutations, type SourceIndex } from '../hooks';
import { humanize } from '../status';
import type { Claim, ClaimKind, SlotDraft } from '../types';
import { ChipSelect } from './unitParts';

const KINDS: ClaimKind[] = ['paragraph', 'bullet', 'step', 'table_row', 'caption', 'figure', 'heading'];

interface SlotEditorProps {
  jobId: string;
  targetSectionId: string;
  slot: SlotDraft;
  /** Passages this slot may cite: its slot-plan units first, then the rest of the section's. */
  unitChoices: string[];
  index: SourceIndex;
  onDone: () => void;
}

/**
 * Edit one slot's claims. Claims are plain text (the template gives the formatting); each one must keep
 * citing at least one source passage, so every sentence of the migrated SOP stays traceable.
 */
export const SlotEditor: React.FC<SlotEditorProps> = ({ jobId, targetSectionId, slot, unitChoices, index, onDone }) => {
  const { success, error } = useToast();
  const { saveSlot } = useJobMutations(jobId);
  const [claims, setClaims] = useState<Claim[]>(() => slot.claims.map((c) => ({ ...c })));
  const [serverErrors, setServerErrors] = useState<string[]>([]);

  const problems = useMemo(() => claimProblems(claims), [claims]);
  const changed = JSON.stringify(claims) !== JSON.stringify(slot.claims);

  const update = (i: number, patch: Partial<Claim>) =>
    setClaims((cs) => cs.map((c, j) => (j === i ? { ...c, ...patch } : c)));
  const moveClaim = (i: number, by: number) =>
    setClaims((cs) => {
      const next = [...cs];
      const [c] = next.splice(i, 1);
      next.splice(Math.max(0, Math.min(next.length, i + by)), 0, c);
      return next;
    });
  const addClaim = () =>
    setClaims((cs) => [
      ...cs,
      {
        claim_id: newClaimId(slot.slot_id, cs),
        text: '',
        kind: cs[cs.length - 1]?.kind === 'step' || cs[cs.length - 1]?.kind === 'bullet' ? cs[cs.length - 1].kind : 'paragraph',
        source_unit_ids: [],
        list_level: cs[cs.length - 1]?.list_level ?? 0,
      },
    ]);

  const save = () =>
    saveSlot.mutate(
      { sectionId: targetSectionId, slotId: slot.slot_id, claims: claims.map(clean) },
      {
        onSuccess: (saved) => {
          success(`Saved as draft v${saved.version}. Run "Re-check" when you are done editing.`, 'Slot saved');
          onDone();
        },
        onError: (e) => {
          setServerErrors(apiErrorDetails(e).length ? apiErrorDetails(e) : [e.message]);
          error(e.message, 'Not saved');
        },
      },
    );

  return (
    <div className="rounded-lg border border-primary/40 bg-primary/[0.03] p-2.5">
      <div className="space-y-2">
        {claims.map((claim, i) => (
          <div key={claim.claim_id} className="rounded-md border border-border bg-card p-2">
            <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
              <span className="unit-id">{claim.claim_id}</span>
              {claim.is_gap_marker && <span className="chip border-danger/40 bg-danger/10 text-danger">gap marker</span>}
              <ChipSelect value={claim.kind} onChange={(e) => update(i, { kind: e.target.value as ClaimKind })} aria-label="Kind">
                {KINDS.map((k) => <option key={k} value={k}>{humanize(k)}</option>)}
              </ChipSelect>
              {(claim.kind === 'bullet' || claim.kind === 'step' || claim.kind === 'heading') && (
                <ChipSelect value={claim.list_level ?? 0} onChange={(e) => update(i, { list_level: Number(e.target.value) })} aria-label="Level">
                  {[0, 1, 2, 3].map((l) => <option key={l} value={l}>Level {l + 1}</option>)}
                </ChipSelect>
              )}
              <span className="ml-auto flex items-center gap-0.5">
                <IconButton title="Move up" disabled={i === 0} onClick={() => moveClaim(i, -1)}><ArrowUp className="size-3" /></IconButton>
                <IconButton title="Move down" disabled={i === claims.length - 1} onClick={() => moveClaim(i, 1)}><ArrowDown className="size-3" /></IconButton>
                <IconButton title="Delete" danger onClick={() => setClaims((cs) => cs.filter((_, j) => j !== i))}><Trash2 className="size-3" /></IconButton>
              </span>
            </div>
            <textarea
              value={claim.text}
              onChange={(e) => update(i, { text: e.target.value })}
              rows={Math.min(8, Math.max(2, Math.ceil(claim.text.length / 90)))}
              className="field h-auto resize-y py-1.5 text-[13px] leading-relaxed"
              placeholder={claim.kind === 'table_row' ? 'Cell 1 | Cell 2 | …' : 'Text'}
            />
            {claim.kind !== 'heading' && (
              <div className="mt-1.5 flex flex-wrap items-center gap-1">
                <span className="text-[10px] uppercase tracking-wide text-text-muted">Sources</span>
                {claim.source_unit_ids.map((id) => (
                  <span key={id} className="chip-muted cursor-pointer gap-1 font-mono" {...focusProps({ sourceUnitIds: [id], targetSectionId, slotId: slot.slot_id })}>
                    {id}
                    <button
                      type="button"
                      title="Remove this source"
                      onClick={(e) => {
                        e.stopPropagation();
                        update(i, { source_unit_ids: claim.source_unit_ids.filter((u) => u !== id), spans: claim.spans?.filter((s) => s.unit_id !== id) });
                      }}
                      className="hover:text-danger"
                    >
                      <X className="size-2.5" />
                    </button>
                  </span>
                ))}
                <ChipSelect
                  value=""
                  aria-label="Add a source passage"
                  onChange={(e) => {
                    if (!e.target.value) return;
                    update(i, { source_unit_ids: [...claim.source_unit_ids, e.target.value], is_gap_marker: false });
                  }}
                >
                  <option value="">+ source…</option>
                  {unitChoices.filter((u) => !claim.source_unit_ids.includes(u)).map((id) => (
                    <option key={id} value={id}>{id} · {(index.units.get(id)?.text ?? '').slice(0, 60)}</option>
                  ))}
                </ChipSelect>
              </div>
            )}
          </div>
        ))}
      </div>

      {(problems.length > 0 || serverErrors.length > 0) && (
        <ul className="mt-2 list-disc space-y-0.5 pl-5 text-[11px] text-danger">
          {[...problems, ...serverErrors].map((p) => <li key={p}>{p}</li>)}
        </ul>
      )}

      <div className="mt-2.5 flex flex-wrap items-center gap-2">
        <Button size="sm" variant="ghost" leftIcon={<Plus className="size-3.5" />} onClick={addClaim}>Add a claim</Button>
        <span className="ml-auto" />
        <Button size="sm" variant="ghost" onClick={onDone} disabled={saveSlot.isPending}>Cancel</Button>
        <Button size="sm" variant="primary" leftIcon={<Save className="size-3.5" />} onClick={save} disabled={!changed || problems.length > 0} isLoading={saveSlot.isPending}>
          Save slot
        </Button>
      </div>
    </div>
  );
};

/** The same checks the server makes, so the reviewer sees them before saving. */
function claimProblems(claims: Claim[]): string[] {
  const problems: string[] = [];
  claims.forEach((c, i) => {
    const where = `Claim ${i + 1}`;
    if (!c.text.trim() && c.kind !== 'figure') problems.push(`${where} has no text`);
    if (c.kind === 'heading' && !c.source_section_id) problems.push(`${where}: a heading must come from a source section; use another kind`);
    if (c.kind !== 'heading' && !c.is_gap_marker && !c.source_unit_ids.length) problems.push(`${where} cites no source passage`);
  });
  return problems;
}

/** Drop spans of sources that were removed; a claim that now cites sources is no longer a gap marker. */
function clean(claim: Claim): Claim {
  const spans = claim.spans?.filter((s) => claim.source_unit_ids.includes(s.unit_id));
  return { ...claim, text: claim.text.trim(), spans, is_gap_marker: claim.is_gap_marker && !claim.source_unit_ids.length };
}

function newClaimId(slotId: string, claims: Claim[]): string {
  const taken = new Set(claims.map((c) => c.claim_id));
  let n = claims.length + 1;
  while (taken.has(`${slotId}-R${n}`)) n++;
  return `${slotId}-R${n}`;
}

const IconButton: React.FC<React.ButtonHTMLAttributes<HTMLButtonElement> & { danger?: boolean }> = ({ danger, className, ...props }) => (
  <button
    type="button"
    className={clsx(
      'grid size-6 place-items-center rounded text-text-muted disabled:opacity-30',
      danger ? 'hover:bg-danger/15 hover:text-danger' : 'hover:bg-white/10 hover:text-text-main',
      className,
    )}
    {...props}
  />
);
