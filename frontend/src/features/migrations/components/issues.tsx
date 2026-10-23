import React, { useState } from 'react';
import { AlertOctagon, CheckCircle2, ChevronDown, ChevronRight, ShieldAlert } from 'lucide-react';
import { clsx } from 'clsx';
import { focusProps, useActiveFocus } from '../focusStore';
import { openIssues, sortIssues, splitNote } from '../report';
import { SEVERITY_CLASSES, humanize } from '../status';
import type { QualityReport, Severity, ValidationIssue } from '../types';

export const SeverityChip: React.FC<{ severity: Severity }> = ({ severity }) => (
  <span className={clsx('chip uppercase tracking-wide', SEVERITY_CLASSES[severity])}>{severity}</span>
);

export const IssueRow: React.FC<{
  issue: ValidationIssue;
  where?: string;
  actions?: React.ReactNode;
  compact?: boolean;
}> = ({ issue, where, actions, compact }) => {
  const focus = useActiveFocus();
  const active = focus?.issueId === issue.issue_id;
  return (
    <div
      data-issue-id={issue.issue_id}
      {...focusProps({
        issueId: issue.issue_id,
        targetSectionId: issue.target_section_id,
        slotId: issue.slot_id,
        sourceUnitIds: issue.unit_ids?.length ? issue.unit_ids : undefined,
        claimId: issue.claim_ids?.[0],
      })}
      className={clsx(
        'cursor-pointer rounded-md border px-2.5 py-2 text-xs transition-colors',
        active ? 'border-primary/50 bg-primary/[0.07]' : 'border-border hover:bg-white/[0.03]',
        issue.resolved && 'opacity-60',
      )}
    >
      <div className="flex flex-wrap items-center gap-1.5">
        {issue.gate ? <AlertOctagon className="size-3.5 text-danger" /> : null}
        <SeverityChip severity={issue.severity} />
        {issue.gate && <span className="chip border-danger/40 bg-danger/10 text-danger">blocks: {humanize(issue.gate)}</span>}
        <span className="chip-muted">{humanize(issue.category)}</span>
        {issue.source && issue.source !== 'deterministic' && <span className="chip-muted">{issue.source}</span>}
        {where && <span className="truncate text-[11px] text-text-muted">{where}</span>}
        {issue.resolved && (
          <span className="ml-auto flex items-center gap-1 text-[11px] text-primary">
            <CheckCircle2 className="size-3" /> resolved
          </span>
        )}
      </div>
      <p className={clsx('mt-1 leading-relaxed text-text-main', compact && 'line-clamp-2')}>{issue.message}</p>
      {issue.resolution_note && <ResolutionNote note={issue.resolution_note} />}
      {actions && <div className="mt-2 flex items-center gap-2">{actions}</div>}
    </div>
  );
};

/** A plan's validation: a one-line summary that opens the full list. */
export const ValidationStrip: React.FC<{ report?: QualityReport | null; where?: (i: ValidationIssue) => string | undefined }> = ({
  report,
  where,
}) => {
  const issues = sortIssues(openIssues(report));
  const blocking = issues.filter((i) => i.gate).length;
  const [open, setOpen] = useState(blocking > 0);
  if (!report) return null;

  return (
    <div className={clsx('rounded-lg border', blocking ? 'border-danger/30 bg-danger/[0.04]' : issues.length ? 'border-warning/25 bg-warning/[0.03]' : 'border-primary/25 bg-primary/[0.04]')}>
      <button type="button" onClick={() => setOpen((o) => !o)} disabled={!issues.length} className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs">
        {issues.length ? (open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />) : <CheckCircle2 className="size-3.5 text-primary" />}
        {blocking > 0 && <ShieldAlert className="size-3.5 text-danger" />}
        <span className="font-medium text-text-main">
          {issues.length === 0
            ? 'Validation passed'
            : `${blocking ? `${blocking} blocking · ` : ''}${issues.length - blocking} to check`}
        </span>
        <span className="text-text-muted">· validation v{report.version}</span>
      </button>
      {open && issues.length > 0 && (
        <div className="max-h-64 space-y-1.5 overflow-y-auto border-t border-border px-3 py-2">
          {issues.map((issue) => (
            <IssueRow key={issue.issue_id} issue={issue} where={where?.(issue)} compact />
          ))}
        </div>
      )}
    </div>
  );
};

export const ResolutionNote: React.FC<{ note: string }> = ({ note }) => {
  const { actor, text } = splitNote(note);
  return (
    <p className="mt-1 text-[11px] text-text-muted">
      {actor && <span className="font-medium not-italic text-text-main/80">{actor}: </span>}
      <span className="italic">{text}</span>
    </p>
  );
};
