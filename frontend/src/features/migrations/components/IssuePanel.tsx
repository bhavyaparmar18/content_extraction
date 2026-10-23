import React, { useMemo, useState } from 'react';
import { CheckCircle2, ShieldAlert } from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/ToastStack';
import { focusProps } from '../focusStore';
import { useJobMutations, type SourceIndex } from '../hooks';
import { humanize, statusInfo } from '../status';
import type { QualityReport, TemplateModel, ValidationIssue } from '../types';
import { sortIssues, unitText } from '../report';
import { IssueRow } from './issues';
import { JustifyDialog } from './JustifyDialog';

type Filter = 'open' | 'blocking' | 'resolved' | 'risk';

interface IssuePanelProps {
  jobId: string;
  report: QualityReport;
  template?: TemplateModel;
  index: SourceIndex;
  canResolve: boolean;
}

/** The quality report: blocking issues first, then what to check; each resolvable with a note. */
export const IssuePanel: React.FC<IssuePanelProps> = ({ jobId, report, template, index, canResolve }) => {
  const { success, error } = useToast();
  const { resolveIssue } = useJobMutations(jobId);
  const [filter, setFilter] = useState<Filter>(() => (report.issues.some((i) => i.gate && !i.resolved) ? 'blocking' : 'open'));
  const [section, setSection] = useState('');
  const [resolving, setResolving] = useState<ValidationIssue | null>(null);

  const headings = useMemo(() => new Map(template?.sections.map((s) => [s.section_id, `${s.number ? `${s.number} ` : ''}${s.heading}`]) ?? []), [template]);
  const slots = useMemo(() => new Map(template?.sections.flatMap((s) => s.slots.map((x) => [x.slot_id, x.key ? humanize(x.key) : x.slot_id] as const)) ?? []), [template]);
  const counts = {
    open: report.issues.filter((i) => !i.resolved).length,
    blocking: report.issues.filter((i) => i.gate && !i.resolved).length,
    resolved: report.issues.filter((i) => i.resolved).length,
    risk: Object.keys(report.high_risk_units ?? {}).length,
  };

  const shown = sortIssues(
    report.issues.filter(
      (i) =>
        (filter === 'open' ? !i.resolved : filter === 'blocking' ? i.gate && !i.resolved : i.resolved) &&
        (!section || i.target_section_id === section),
    ),
  );

  const where = (i: ValidationIssue) =>
    [i.target_section_id && headings.get(i.target_section_id), i.slot_id && slots.get(i.slot_id)].filter(Boolean).join(' › ') || undefined;

  const resolve = (note: string) => {
    if (!resolving) return;
    resolveIssue.mutate(
      { issueId: resolving.issue_id, note },
      {
        onSuccess: (res) => {
          success(
            res.gates_passed ? `No blocking issue left: the job is ${statusInfo(res.status).label.toLowerCase()}.` : 'Saved in the quality report and the audit trail.',
            resolving.gate === 'missing_slot' ? 'Gap accepted as N/A' : 'Issue resolved',
          );
          setResolving(null);
        },
        onError: (e) => error(e.message, 'Not resolved'),
      },
    );
  };

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 space-y-2 border-b border-border px-3 py-2.5">
        <div className="flex flex-wrap gap-1">
          {(['blocking', 'open', 'resolved', 'risk'] as Filter[]).map((f) => (
            <button key={f} type="button" onClick={() => setFilter(f)} className={clsx('filter-chip h-7 px-2 text-[11px]', filter === f && 'filter-chip-active')}>
              {f === 'blocking' ? 'Blocking' : f === 'open' ? 'All open' : f === 'resolved' ? 'Resolved' : 'High risk'}
              <span className="font-semibold">{counts[f]}</span>
            </button>
          ))}
        </div>
        {filter !== 'risk' && (
          <select value={section} onChange={(e) => setSection(e.target.value)} className="field h-7 py-0 text-[11px]">
            <option value="">All sections</option>
            {template?.sections.map((s) => <option key={s.section_id} value={s.section_id}>{headings.get(s.section_id)}</option>)}
          </select>
        )}
      </div>

      <div className="min-h-0 flex-1 space-y-1.5 overflow-y-auto p-3">
        {filter === 'risk' ? (
          <HighRisk report={report} index={index} />
        ) : shown.length === 0 ? (
          <div className="flex flex-col items-center gap-2 py-10 text-center text-xs text-text-muted">
            <CheckCircle2 className="size-6 text-primary" />
            {filter === 'blocking' ? 'Nothing blocks the export.' : filter === 'resolved' ? 'No issue resolved yet.' : 'No open issue.'}
          </div>
        ) : (
          shown.map((issue) => (
            <IssueRow
              key={issue.issue_id}
              issue={issue}
              where={where(issue)}
              actions={
                canResolve && !issue.resolved ? (
                  <Button size="sm" variant={issue.gate ? 'primary' : 'secondary'} className="h-6 px-2 text-[11px]" onClick={(e) => {
                    e.stopPropagation();
                    setResolving(issue);
                  }}>
                    {issue.gate === 'missing_slot' ? 'Accept as N/A…' : 'Resolve…'}
                  </Button>
                ) : undefined
              }
            />
          ))
        )}
        {!canResolve && filter !== 'risk' && counts.open > 0 && (
          <p className="pt-1 text-[11px] text-text-muted">Issues can be resolved once the job has finished its run.</p>
        )}
      </div>

      <JustifyDialog
        open={!!resolving}
        title={resolving?.gate === 'missing_slot' ? 'Accept this gap as not applicable?' : 'Resolve this issue?'}
        description={
          resolving?.gate === 'missing_slot'
            ? 'The slot and its instruction are removed from the final document. Say why the SOP has nothing for it.'
            : `${resolving?.message ?? ''} — say what you checked or changed.`
        }
        confirmLabel={resolving?.gate === 'missing_slot' ? 'Accept as N/A' : 'Resolve'}
        busy={resolveIssue.isPending}
        onCancel={() => setResolving(null)}
        onConfirm={resolve}
      />
    </div>
  );
};

const HighRisk: React.FC<{ report: QualityReport; index: SourceIndex }> = ({ report, index }) => {
  const entries = Object.entries(report.high_risk_units ?? {});
  if (!entries.length) return <p className="py-10 text-center text-xs text-text-muted">No high-risk passage in this SOP.</p>;
  return (
    <>
      <p className="mb-1 flex items-start gap-1.5 text-[11px] text-text-muted">
        <ShieldAlert className="mt-0.5 size-3.5 shrink-0 text-warning" />
        Approvals, deadlines, limits and prohibitions: check that the draft keeps their meaning exactly.
      </p>
      {entries.map(([unitId, tags]) => {
        const unit = index.units.get(unitId);
        return (
          <div
            key={unitId}
            {...focusProps({ sourceUnitIds: [unitId], sourceSectionIds: unit ? [unit.section_id] : undefined })}
            className="cursor-pointer rounded-md border border-border px-2.5 py-2 text-xs hover:bg-white/[0.03]"
          >
            <div className="mb-1 flex flex-wrap items-center gap-1">
              <span className="unit-id">{unitId}</span>
              {tags.map((t) => <span key={t} className="chip border-warning/40 bg-warning/10 text-warning">{humanize(t)}</span>)}
            </div>
            <p className="line-clamp-3 text-text-main/90">{unit ? unitText(unit) : ''}</p>
          </div>
        );
      })}
    </>
  );
};
