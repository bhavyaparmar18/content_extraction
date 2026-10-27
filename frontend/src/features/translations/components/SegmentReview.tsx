import React, { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ListChecks, ListTree, Loader2 } from 'lucide-react';
import { ReviewShell } from '@/features/migrations/components/ReviewShell';
import { PaneTabs } from '@/features/migrations/components/paneParts';
import { openIssues } from '@/features/migrations/report';
import type { TemplateModel } from '@/features/migrations/types';
import { useLanguageNames, useSegments, useTranslationRenderReport } from '../hooks';
import { groupByScope, issuesBySegment, keptInEnglish, scopeOf, sectionOrder } from '../segments';
import { translationPermissions } from '../status';
import type { QualityReport, TranslationJob, ValidationIssue } from '../types';
import { SegmentGrid, TranslationSectionNav } from './SegmentGrid';
import { FindReplacePanel, JobGlossaryPanel, TranslationIssuePanel } from './ReviewPanels';

type Tool = 'issues' | 'glossary' | 'replace';

/**
 * ③ The review: sections on the left, the selected section's segments (English and translation) in the middle,
 * the issues, glossary and find and replace on the right. ``?section=``, ``?segment=`` and ``?issue=`` say what is
 * selected, so links from the issues, the matches and the final document land on their segment.
 */
export const SegmentReview: React.FC<{ job: TranslationJob; report?: QualityReport; template?: TemplateModel }> = ({ job, report, template }) => {
  const [params, setParams] = useSearchParams();
  const names = useLanguageNames();
  const segments = useSegments(job);
  const render = useTranslationRenderReport(job);
  const can = translationPermissions(job);
  const [tool, setTool] = useState<Tool>('issues');
  const [replaceFind, setReplaceFind] = useState<{ find: string; n: number } | null>(null);

  const all = useMemo(() => segments.data?.segments ?? [], [segments.data]);
  const byScope = useMemo(() => groupByScope(all), [all]);
  const scopeOfSegment = useMemo(() => new Map(all.map((s) => [s.segment_id, scopeOf(s)] as const)), [all]);
  const sections = useMemo(() => sectionOrder([...byScope.keys()], template?.sections), [byScope, template]);
  const open = useMemo(() => issuesBySegment(openIssues(report)), [report]);
  const english = useMemo(() => keptInEnglish(render.data), [render.data]);

  const issueParam = params.get('issue');
  const issue = issueParam ? report?.issues.find((i) => i.issue_id === issueParam) : undefined;
  const selected = params.get('segment') ?? issue?.segment_ids?.[0] ?? null;
  const scope = params.get('section') ?? (selected ? scopeOfSegment.get(selected) : undefined) ?? sections[0]?.scope ?? '';
  const section = sections.find((s) => s.scope === scope);
  const headingOf = (s: string) => {
    const entry = sections.find((x) => x.scope === s);
    return entry ? `${entry.number ? `${entry.number} ` : ''}${entry.heading}` : s;
  };

  const go = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    setParams(next, { replace: true });
  };
  const selectSegment = (segmentId: string, inScope?: string) => go({ segment: segmentId, section: inScope ?? scopeOfSegment.get(segmentId) ?? null, issue: null });
  const selectIssue = (i: ValidationIssue) => {
    setTool('issues');
    const first = i.segment_ids?.[0];
    go({ issue: i.issue_id, segment: first ?? null, section: first ? scopeOfSegment.get(first) ?? null : null });
  };

  const readOnlyReason = can.edit
    ? undefined
    : job.status === 'APPROVED'
      ? 'Approved: the translation is final and read-only.'
      : job.running || job.status === 'RENDERING'
        ? 'The document is being rendered; editing opens again when it is done.'
        : 'Read-only: the job is not waiting for review.';

  if (segments.isLoading) return <div className="p-6"><Loader2 className="size-4 animate-spin text-text-muted" /></div>;
  if (segments.error) return <p className="p-6 text-sm text-danger">{segments.error.message}</p>;

  // The shell fills a flex column (its flex-1 needs one), so only its panes scroll, never the page around them.
  return (
    <div className="flex h-full flex-col">
      <ReviewShell
        storageKey="translation-review-panes"
        left={{
          title: 'Sections',
          short: 'sections',
          icon: <ListTree className="size-3.5" />,
          content: <TranslationSectionNav sections={sections} byScope={byScope} open={open} current={scope} onSelect={(s) => go({ section: s, segment: null, issue: null })} />,
        }}
        right={{
          title: 'Review tools',
          short: 'tools',
          icon: <ListChecks className="size-3.5" />,
          content: (
            <div className="flex h-full flex-col">
              <PaneTabs
                value={tool}
                onChange={(v) => setTool(v as Tool)}
                tabs={[
                  { id: 'issues', label: `Issues${report ? ` (${openIssues(report).length})` : ''}` },
                  { id: 'glossary', label: 'Terms' },
                  { id: 'replace', label: 'Find & replace' },
                ]}
              />
              <div className="min-h-0 flex-1">
                {tool === 'issues' && (
                  <TranslationIssuePanel jobId={job.job_id} report={report} canResolve={can.edit} scope={scope} scopeOf={scopeOfSegment}
                    headingOf={headingOf} active={issueParam} onSelect={selectIssue} />
                )}
                {tool === 'glossary' && (
                  <JobGlossaryPanel job={job} selected={all.find((s) => s.segment_id === selected)}
                    onReplace={(find) => { setReplaceFind((r) => ({ find, n: (r?.n ?? 0) + 1 })); setTool('replace'); }} />
                )}
                {tool === 'replace' && (
                  <FindReplacePanel key={replaceFind?.n ?? 0} job={job} scope={scope} scopeLabel={headingOf(scope)} editable={can.edit}
                    initialFind={replaceFind?.find} onSelectSegment={selectSegment} />
                )}
              </div>
            </div>
          ),
        }}
      >
        <SegmentGrid
          key={scope}
          jobId={job.job_id}
          section={section}
          segments={byScope.get(scope) ?? []}
          all={all}
          open={open}
          english={english}
          languageName={names(job.language)}
          selected={selected}
          editable={can.edit}
          readOnlyReason={readOnlyReason}
          onSelect={(id) => selectSegment(id, scope)}
          onSelectIssue={selectIssue}
        />
      </ReviewShell>
    </div>
  );
};
