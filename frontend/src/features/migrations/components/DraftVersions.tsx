import React, { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { History, Loader2, X } from 'lucide-react';
import { clsx } from 'clsx';
import { DiffText } from '@/components/review/CompareView';
import { diffWords } from '@/lib/diff';
import { formatDate } from '@/lib/format';
import { migrationsApi } from '../api';
import { migrationKeys } from '../hooks';
import { actorName } from '../report';
import type { Claim, MigrationJob, SectionDraft } from '../types';

const ORIGIN: Record<string, string> = { llm: 'Drafted', repair: 'Repaired', reconcile: 'Reconciled', human: 'Reviewer edit' };

/** Every saved version of a section's draft, and what changed between two of them, claim by claim. */
export const DraftVersions: React.FC<{ job: MigrationJob; sectionId: string; heading: string; onClose: () => void }> = ({
  job,
  sectionId,
  heading,
  onClose,
}) => {
  const versions = useMemo(
    () => job.artifacts.filter((a) => a.kind === 'section_draft' && a.scope === sectionId).sort((a, b) => b.version - a.version),
    [job.artifacts, sectionId],
  );
  const [after, setAfter] = useState(versions[0]?.version ?? 1);
  const [before, setBefore] = useState(versions[1]?.version ?? versions[0]?.version ?? 1);

  const load = (version: number) => ({
    queryKey: migrationKeys.part(job.job_id, 'draft_version', sectionId, version),
    queryFn: () => migrationsApi.draftVersion(job.job_id, sectionId, version),
    staleTime: Infinity,
  });
  const a = useQuery(load(before));
  const b = useQuery(load(after));

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" onMouseDown={onClose}>
      <div className="dashboard-card flex max-h-[85vh] w-full max-w-4xl flex-col" onMouseDown={(e) => e.stopPropagation()}>
        <div className="panel-header">
          <div className="flex items-center gap-2 text-sm font-semibold text-text-main">
            <History className="size-4 text-primary" /> Versions of {heading}
          </div>
          <button type="button" onClick={onClose} className="grid size-7 place-items-center rounded text-text-muted hover:bg-white/5">
            <X className="size-4" />
          </button>
        </div>
        <div className="flex min-h-0 flex-1">
          <ul className="w-56 shrink-0 space-y-1 overflow-y-auto border-r border-border p-2">
            {versions.map((v) => (
              <li key={v.version} className={clsx('rounded-md border px-2.5 py-2 text-xs', v.version === after ? 'border-primary/50 bg-primary/[0.06]' : v.version === before ? 'border-info/40' : 'border-border')}>
                <div className="flex items-center justify-between font-medium text-text-main">v{v.version}</div>
                <div className="text-[11px] text-text-muted">{v.created_at ? formatDate(v.created_at) : ''} · {actorName(v.created_by)}</div>
                <div className="mt-1.5 flex gap-1">
                  <button type="button" onClick={() => setBefore(v.version)} className={clsx('pane-tab', v.version === before && 'pane-tab-active')}>Before</button>
                  <button type="button" onClick={() => setAfter(v.version)} className={clsx('pane-tab', v.version === after && 'pane-tab-active')}>After</button>
                </div>
              </li>
            ))}
          </ul>
          <div className="min-w-0 flex-1 overflow-y-auto p-4">
            {a.data && b.data ? (
              <VersionDiff before={a.data} after={b.data} />
            ) : (
              <div className="flex items-center gap-2 text-xs text-text-muted"><Loader2 className="size-4 animate-spin" /> Loading versions…</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

const VersionDiff: React.FC<{ before: SectionDraft; after: SectionDraft }> = ({ before, after }) => {
  const rows = useMemo(() => diffClaims(before, after), [before, after]);
  const changed = rows.filter((r) => r.state !== 'same');
  return (
    <div className="space-y-3 text-xs">
      <div className="text-text-muted">
        v{before.version} ({ORIGIN[before.origin] ?? before.origin}) → v{after.version} ({ORIGIN[after.origin] ?? after.origin}):{' '}
        <span className="text-text-main">{changed.length ? `${changed.length} claim(s) changed` : 'no claim changed'}</span>
      </div>
      {changed.map((row) => (
        <div key={row.id} className="rounded-md border border-border p-2.5">
          <div className="mb-1 flex items-center gap-1.5">
            <span className="unit-id">{row.id}</span>
            <span className={clsx('chip', row.state === 'added' ? 'border-primary/40 bg-primary/10 text-primary' : row.state === 'removed' ? 'border-danger/40 bg-danger/10 text-danger' : 'border-warning/40 bg-warning/10 text-warning')}>
              {row.state}
            </span>
          </div>
          {row.state === 'changed' ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <p><DiffText parts={row.parts!} side="before" /></p>
              <p><DiffText parts={row.parts!} side="after" /></p>
            </div>
          ) : (
            <p className={row.state === 'removed' ? 'text-text-muted line-through' : 'text-text-main'}>{row.text}</p>
          )}
        </div>
      ))}
    </div>
  );
};

function diffClaims(before: SectionDraft, after: SectionDraft) {
  const all = (d: SectionDraft) => new Map<string, Claim>(d.slots.flatMap((s) => s.claims.map((c) => [c.claim_id, c] as const)));
  const a = all(before);
  const b = all(after);
  const ids = [...new Set([...b.keys(), ...a.keys()])];
  return ids.map((id) => {
    const x = a.get(id);
    const y = b.get(id);
    if (!x) return { id, state: 'added' as const, text: y!.text };
    if (!y) return { id, state: 'removed' as const, text: x.text };
    if (x.text === y.text) return { id, state: 'same' as const, text: y.text };
    return { id, state: 'changed' as const, text: y.text, parts: diffWords(x.text, y.text) };
  });
}
