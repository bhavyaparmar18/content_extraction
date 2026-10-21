import React from 'react';
import { clsx } from 'clsx';
import { useReviewUi } from '../focusStore';
import { useSourceIndex } from '../hooks';
import { openIssues } from '../report';
import { permissions } from '../status';
import type { MigrationJob, QualityReport, SourceDocument, TemplateModel } from '../types';
import { IssuePanel } from './IssuePanel';
import { TemplatePane } from './TemplatePane';

/** The right pane on the draft step: the job's issues, or the template (one click apart). */
export const DraftSidePane: React.FC<{
  job: MigrationJob;
  report?: QualityReport;
  source?: SourceDocument;
  template?: TemplateModel;
}> = ({ job, report, source, template }) => {
  const tab = useReviewUi((s) => s.rightTab);
  const setTab = useReviewUi((s) => s.setRightTab);
  const index = useSourceIndex(source);
  const open = openIssues(report);
  const blocking = open.filter((i) => i.gate).length;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="grid shrink-0 grid-cols-2 gap-1 border-b border-border p-1.5">
        {(['issues', 'template'] as const).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={clsx(
              'flex items-center justify-center gap-1.5 rounded-md py-1.5 text-xs font-medium transition',
              tab === t ? 'bg-primary/10 text-primary' : 'text-text-muted hover:bg-white/5 hover:text-text-main',
            )}
          >
            {t === 'issues' ? 'Issues' : 'Template'}
            {t === 'issues' && open.length > 0 && (
              <span className={clsx('rounded-full px-1.5 text-[10px] font-semibold', blocking ? 'bg-danger/20 text-danger' : 'bg-warning/15 text-warning')}>
                {open.length}
              </span>
            )}
          </button>
        ))}
      </div>
      <div className="min-h-0 flex-1">
        {tab === 'issues' ? (
          report ? (
            <IssuePanel jobId={job.job_id} report={report} template={template} index={index} canResolve={permissions(job).resolveIssues} />
          ) : (
            <p className="p-4 text-xs text-text-muted">No quality report yet.</p>
          )
        ) : (
          <TemplatePane jobId={job.job_id} template={template} />
        )}
      </div>
    </div>
  );
};
