import React, { useMemo, useState } from 'react';
import { AlertOctagon, AlertTriangle, ArrowRightLeft, Image as ImageIcon } from 'lucide-react';
import { clsx } from 'clsx';
import { api } from '@/lib/api';
import { diffWords } from '@/lib/diff';
import { DiffText } from '@/components/review/CompareView';
import { focusProps, useActiveFocus, useFocusStore } from '../focusStore';
import type { SourceIndex } from '../hooks';
import { SEVERITY_ORDER } from '../status';
import type { CalloutStyle, Claim, SlotDraft, ValidationIssue } from '../types';
import { unitText } from '../report';

interface SlotDraftViewProps {
  slot: SlotDraft;
  targetSectionId: string;
  index: SourceIndex;
  palette: Map<string, CalloutStyle>;
  issuesByClaim: Map<string, ValidationIssue[]>;
  /** The SOP's document UID: figures are served under it. */
  assetBase: string;
  onOpenIssue: (issue: ValidationIssue) => void;
}

/** A drafted slot, laid out roughly as the Word document will show it. */
export const SlotDraftView: React.FC<SlotDraftViewProps> = (props) => {
  const { slot } = props;
  const groups = useMemo(() => groupClaims(slot.claims), [slot.claims]);
  if (!slot.claims.length) return <p className="text-xs italic text-text-muted">Nothing drafted for this slot.</p>;
  return (
    <div className="space-y-1.5">
      {groups.map((group, i) =>
        group.kind === 'table' ? (
          <TableGroup key={i} claims={group.claims} {...props} />
        ) : group.kind === 'callout' ? (
          <CalloutGroup key={i} claims={group.claims} {...props} />
        ) : group.kind === 'list' ? (
          <ListGroup key={i} claims={group.claims} ordered={group.ordered} {...props} />
        ) : (
          <ClaimView key={i} claim={group.claims[0]} {...props} />
        ),
      )}
    </div>
  );
};

type Group = { kind: 'table' | 'callout' | 'list' | 'single'; claims: Claim[]; ordered?: boolean };

function groupClaims(claims: Claim[]): Group[] {
  const groups: Group[] = [];
  for (const claim of claims) {
    const kind: Group['kind'] = claim.callout_kind
      ? 'callout'
      : claim.kind === 'table_row'
        ? 'table'
        : claim.kind === 'bullet' || claim.kind === 'step'
          ? 'list'
          : 'single';
    const last = groups[groups.length - 1];
    const joins =
      last &&
      kind !== 'single' &&
      last.kind === kind &&
      (kind !== 'callout' || last.claims[0].callout_kind === claim.callout_kind) &&
      (kind !== 'list' || last.ordered === (claim.kind === 'step'));
    if (joins) last.claims.push(claim);
    else groups.push({ kind, claims: [claim], ordered: claim.kind === 'step' });
  }
  return groups;
}

type ClaimProps = Omit<SlotDraftViewProps, 'slot'> & { slotId?: string };

/** One claim: hover shows its source passages in the SOP pane; its issues show as a badge. */
const ClaimView: React.FC<ClaimProps & { claim: Claim; as?: 'p' | 'li' | 'div'; compact?: boolean }> = ({
  claim,
  targetSectionId,
  index,
  issuesByClaim,
  assetBase,
  onOpenIssue,
  as = 'div',
  compact,
}) => {
  const focus = useActiveFocus();
  const pinnedClaim = useFocusStore((s) => s.pinned?.claimId);
  const [comparing, setComparing] = useState(false);
  const active = focus?.claimId === claim.claim_id;
  const issues = issuesByClaim.get(claim.claim_id) ?? [];
  const worst = [...issues].sort((a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity))[0];
  const sourceText = claim.source_unit_ids.map((id) => index.units.get(id)).filter(Boolean).map((u) => unitText(u!)).join(' ');
  const Tag = as;

  const body = claim.is_gap_marker ? (
    <span className="flex items-start gap-1.5 rounded border border-dashed border-danger/50 bg-danger/[0.06] px-2 py-1 text-danger">
      <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
      {claim.text}
    </span>
  ) : claim.kind === 'figure' ? (
    <FigureClaim claim={claim} index={index} assetBase={assetBase} />
  ) : claim.kind === 'heading' ? (
    <span className={clsx('font-semibold text-text-main', (claim.list_level ?? 0) === 0 ? 'text-[13px]' : 'text-xs')}>{claim.text}</span>
  ) : claim.kind === 'caption' ? (
    <span className="text-[11px] italic text-text-muted">{claim.text}</span>
  ) : (
    <span>{claim.text}</span>
  );

  return (
    <Tag
      data-claim-id={claim.claim_id}
      {...focusProps({
        claimId: claim.claim_id,
        targetSectionId,
        sourceUnitIds: claim.source_unit_ids.length ? claim.source_unit_ids : undefined,
        sourceSectionIds: claim.source_section_id ? [claim.source_section_id] : undefined,
        spans: claim.spans,
      })}
      className={clsx(
        'group relative cursor-pointer rounded px-1.5 py-0.5 text-[13px] leading-relaxed text-text-main/95 transition-colors',
        active ? 'bg-primary/10 ring-1 ring-primary/50' : 'hover:bg-white/[0.04]',
        pinnedClaim === claim.claim_id && 'ring-2 ring-primary',
        worst?.gate && 'underline decoration-danger/70 decoration-wavy underline-offset-4',
        compact && 'py-0',
      )}
    >
      {body}
      <span className="absolute -right-1 top-0.5 flex translate-x-full items-center gap-0.5 pl-1">
        {worst && (
          <button
            type="button"
            title={issues.map((i) => i.message).join('\n')}
            onClick={(e) => {
              e.stopPropagation();
              onOpenIssue(worst);
            }}
            className={clsx(
              'grid h-5 min-w-5 place-items-center rounded-full px-1 text-[10px] font-semibold',
              worst.gate ? 'bg-danger/20 text-danger' : worst.severity === 'high' ? 'bg-danger/10 text-danger' : 'bg-warning/15 text-warning',
            )}
          >
            {worst.gate ? <AlertOctagon className="size-3" /> : issues.length}
          </button>
        )}
        {!claim.is_gap_marker && sourceText && claim.kind !== 'figure' && claim.kind !== 'heading' && (
          <button
            type="button"
            title="Compare with the source"
            onClick={(e) => {
              e.stopPropagation();
              setComparing((c) => !c);
            }}
            className={clsx('grid size-5 place-items-center rounded text-text-muted hover:bg-white/10 hover:text-text-main', comparing ? 'text-primary' : 'opacity-0 group-hover:opacity-100')}
          >
            <ArrowRightLeft className="size-3" />
          </button>
        )}
      </span>
      {comparing && <ClaimCompare before={sourceText} after={claim.text} />}
    </Tag>
  );
};

const ClaimCompare: React.FC<{ before: string; after: string }> = ({ before, after }) => {
  const parts = useMemo(() => diffWords(before, after), [before, after]);
  const same = parts.every((p) => p.type === 'same');
  return (
    <span className="mt-1.5 block rounded-md border border-border bg-black/10 p-2 text-[11px]" onClick={(e) => e.stopPropagation()}>
      {same ? (
        <span className="text-primary">Same wording as the source.</span>
      ) : (
        <span className="grid gap-2 sm:grid-cols-2">
          <span>
            <span className="mb-0.5 block text-[10px] uppercase tracking-wide text-text-muted">Source</span>
            <DiffText parts={parts} side="before" />
          </span>
          <span>
            <span className="mb-0.5 block text-[10px] uppercase tracking-wide text-text-muted">Draft</span>
            <DiffText parts={parts} side="after" />
          </span>
        </span>
      )}
    </span>
  );
};

const FigureClaim: React.FC<{ claim: Claim; index: SourceIndex; assetBase: string }> = ({ claim, index, assetBase }) => {
  const unit = claim.source_unit_ids.map((id) => index.units.get(id)).find((u) => u?.assets?.some((a) => a.kind === 'figure'));
  const asset = unit?.assets?.find((a) => a.kind === 'figure');
  return (
    <span className="block">
      {asset?.path ? (
        <img
          src={api.getAssetUrl(assetBase, api.assetFileName(asset.path))}
          alt={claim.text || 'Figure'}
          className="max-h-64 rounded border border-border bg-white object-contain"
          loading="lazy"
        />
      ) : (
        <span className="flex items-center gap-1.5 text-text-muted"><ImageIcon className="size-4" /> Figure</span>
      )}
    </span>
  );
};

const ListGroup: React.FC<ClaimProps & { claims: Claim[]; ordered?: boolean }> = ({ claims, ordered, ...props }) => {
  const counters: number[] = [];
  return (
    <ul className="space-y-0.5">
      {claims.map((claim) => {
        const level = claim.list_level ?? 0;
        counters.length = level + 1;
        counters[level] = (counters[level] ?? 0) + 1;
        return (
          <li key={claim.claim_id} className="flex gap-1.5" style={{ paddingLeft: level * 18 }}>
            <span className="mt-0.5 w-6 shrink-0 text-right text-[12px] text-text-muted">
              {ordered ? `${counters.slice(0, level + 1).map((n) => n ?? 1).join('.')}.` : '•'}
            </span>
            <div className="min-w-0 flex-1">
              <ClaimView claim={claim} {...props} compact />
            </div>
          </li>
        );
      })}
    </ul>
  );
};

const TableGroup: React.FC<ClaimProps & { claims: Claim[] }> = ({ claims, ...props }) => {
  const firstUnit = claims.flatMap((c) => c.source_unit_ids).map((id) => props.index.units.get(id)).find((u) => u?.table_ref);
  const headers = firstUnit?.table_ref?.header_cells ?? [];
  return (
    <div className="overflow-x-auto rounded-md border border-border">
      <table className="w-full border-collapse text-[12px]">
        {headers.length > 0 && (
          <thead>
            <tr>
              {headers.map((h, i) => (
                <th key={i} className="border-b border-border bg-black/10 px-2 py-1 text-left font-semibold text-text-main">{h}</th>
              ))}
            </tr>
          </thead>
        )}
        <tbody>
          {claims.map((claim) => (
            <TableRowClaim key={claim.claim_id} claim={claim} {...props} />
          ))}
        </tbody>
      </table>
    </div>
  );
};

const TableRowClaim: React.FC<ClaimProps & { claim: Claim }> = ({ claim, targetSectionId, issuesByClaim, onOpenIssue }) => {
  const focus = useActiveFocus();
  const issues = issuesByClaim.get(claim.claim_id) ?? [];
  const cells = claim.text.split(' | ');
  return (
    <tr
      data-claim-id={claim.claim_id}
      {...focusProps({ claimId: claim.claim_id, targetSectionId, sourceUnitIds: claim.source_unit_ids, spans: claim.spans })}
      className={clsx('cursor-pointer border-b border-border last:border-b-0', focus?.claimId === claim.claim_id ? 'bg-primary/10' : 'hover:bg-white/[0.03]')}
    >
      {cells.map((cell, i) => (
        <td key={i} className="px-2 py-1 align-top text-text-main/95">
          {cell}
          {i === cells.length - 1 && issues.length > 0 && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onOpenIssue(issues[0]);
              }}
              className="ml-1.5 rounded-full bg-warning/15 px-1.5 text-[10px] font-semibold text-warning"
              title={issues.map((x) => x.message).join('\n')}
            >
              {issues.length}
            </button>
          )}
        </td>
      ))}
    </tr>
  );
};

const CalloutGroup: React.FC<ClaimProps & { claims: Claim[] }> = ({ claims, palette, ...props }) => {
  const style = palette.get(claims[0].callout_kind!);
  return (
    <div
      className="rounded-md border-l-4 px-2 py-1.5"
      style={{ borderLeftColor: style ? `#${style.fill_hex}` : undefined, backgroundColor: style ? `#${style.fill_hex}26` : undefined }}
    >
      <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wide text-text-muted">{style?.label ?? claims[0].callout_kind}</div>
      {claims.map((claim) => (
        <ClaimView key={claim.claim_id} claim={claim} palette={palette} {...props} compact />
      ))}
    </div>
  );
};
