import React from 'react';
import { Loader2 } from 'lucide-react';
import { IssueRow } from '@/features/migrations/components/issues';
import { openIssues, sortIssues } from '@/features/migrations/report';
import type { TemplateModel } from '@/features/migrations/types';
import type { QualityReport, TranslationJob } from '../types';

/** ③ The review (T8b: the open QA issues; the segment grid follows in T8c). */
export const SegmentReview: React.FC<{ job: TranslationJob; report?: QualityReport; template?: TemplateModel }> = ({ report }) => {
  if (!report) return <div className="p-6"><Loader2 className="size-4 animate-spin text-text-muted" /></div>;
  const issues = sortIssues(openIssues(report));
  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl space-y-1.5 px-6 py-6">
        <h2 className="mb-2 text-sm font-semibold text-text-main">{issues.length} open issue(s) · checks v{report.version}</h2>
        {issues.map((i) => <IssueRow key={i.issue_id} issue={i} where={i.segment_ids?.join(', ')} />)}
      </div>
    </div>
  );
};
