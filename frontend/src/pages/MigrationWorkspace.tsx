import React, { useEffect, useMemo, useRef } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { AlertCircle, FileText, Layers, ListChecks, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { useFocusStore } from '@/features/migrations/focusStore';
import {
  useDrafts,
  useMigrationJob,
  useQualityReport,
  useSectionPlan,
  useSlotPlan,
  useSopRecord,
  useSourceModel,
  useTemplateModel,
} from '@/features/migrations/hooks';
import { defaultStep, isWorking, permissions, stepStates } from '@/features/migrations/status';
import type { MigrationJob } from '@/features/migrations/types';
import { ActivityLog } from '@/features/migrations/components/ActivityLog';
import { DraftReview } from '@/features/migrations/components/DraftReview';
import { DraftSidePane } from '@/features/migrations/components/DraftSidePane';
import { FinalDocument } from '@/features/migrations/components/FinalDocument';
import { JobHeader } from '@/features/migrations/components/JobHeader';
import { JobProgress } from '@/features/migrations/components/JobProgress';
import { ReviewShell } from '@/features/migrations/components/ReviewShell';
import { SectionPlanReview } from '@/features/migrations/components/SectionPlanReview';
import { SlotPlanReview } from '@/features/migrations/components/SlotPlanReview';
import { PaneLoading, SourcePane } from '@/features/migrations/components/SourcePane';
import { StageStepper, type View } from '@/features/migrations/components/StageStepper';
import { TemplatePane } from '@/features/migrations/components/TemplatePane';

/** One migration job: its review steps between the original SOP and the template. */
export const MigrationWorkspace: React.FC = () => {
  const { jobId = '' } = useParams<{ jobId: string }>();
  const job = useMigrationJob(jobId);
  const resetFocus = useFocusStore((s) => s.reset);

  useEffect(() => {
    resetFocus();
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && useFocusStore.getState().pin(null);
    window.addEventListener('keydown', onKey);
    return () => {
      window.removeEventListener('keydown', onKey);
      resetFocus();
    };
  }, [jobId, resetFocus]);

  if (job.isLoading) {
    return (
      <div className="grid h-full place-items-center text-sm text-text-muted">
        <span className="flex items-center gap-2"><Loader2 className="size-4 animate-spin" /> Loading migration…</span>
      </div>
    );
  }
  if (job.error || !job.data) {
    return (
      <div className="content-pane">
        <div className="error-panel flex items-start gap-2 text-sm">
          <AlertCircle className="mt-0.5 size-4 text-danger" />
          <div>
            <div className="font-medium text-text-main">This migration could not be loaded</div>
            <div className="text-xs text-text-muted">{job.error?.message}</div>
          </div>
        </div>
      </div>
    );
  }
  return <Workspace job={job.data} />;
};

const Workspace: React.FC<{ job: MigrationJob }> = ({ job }) => {
  const [params, setParams] = useSearchParams();
  const sop = useSopRecord(job.sop_record_id);
  const source = useSourceModel(job.job_id, job);
  const template = useTemplateModel(job.job_id, job);
  const sectionPlan = useSectionPlan(job.job_id, job);
  const slotPlan = useSlotPlan(job.job_id, job);
  const drafts = useDrafts(job.job_id, job);
  const quality = useQualityReport(job.job_id, job);
  const can = permissions(job);

  // Follow the job to the step that needs the reviewer, unless they picked one.
  const status = useRef(job.status);
  useEffect(() => {
    if (status.current !== job.status) {
      status.current = job.status;
      if (params.get('step')) setParams({}, { replace: true });
    }
  }, [job.status, params, setParams]);

  const states = stepStates(job);
  const requested = params.get('step') as View | null;
  const view: View = requested && (requested === 'activity' || states[requested] !== 'locked') ? requested : defaultStep(job);
  const setView = (v: View) => setParams({ step: v }, { replace: true });

  const unplaced = useMemo(() => {
    if (view !== 'slots' || !slotPlan.plan.data) return undefined;
    return new Map(slotPlan.plan.data.sections.flatMap((s) => s.unplaced_unit_ids.map((u) => [u, 'unplaced'] as const)));
  }, [view, slotPlan.plan.data]);

  const working = isWorking(job);
  const loading = <PaneLoading />;
  let content: React.ReactNode;
  if (view === 'activity') {
    content = <ActivityLog job={job} />;
  } else if (job.status === 'FAILED_TECHNICAL' && states[view] === 'locked') {
    content = <Failed job={job} />;
  } else if (working && (states[view] === 'working' || states[view] === 'locked')) {
    content = <div className="h-full overflow-y-auto"><JobProgress job={job} template={template.data} /></div>;
  } else if (view === 'sections') {
    content = sectionPlan.plan.data && source.data && template.data ? (
      <SectionPlanReview job={job} plan={sectionPlan.plan.data} validation={sectionPlan.validation.data} source={source.data} template={template.data} editable={can.editSectionPlan} />
    ) : loading;
  } else if (view === 'slots') {
    content = slotPlan.plan.data && source.data && template.data ? (
      <SlotPlanReview
        job={job}
        plan={slotPlan.plan.data}
        validation={slotPlan.validation.data}
        sectionPlan={sectionPlan.plan.data}
        source={source.data}
        template={template.data}
        editable={can.editSlotPlan}
      />
    ) : loading;
  } else if (view === 'draft') {
    content = drafts.data && source.data && template.data ? (
      <DraftReview
        job={job}
        drafts={drafts.data}
        report={quality.data}
        slotPlan={slotPlan.plan.data}
        source={source.data}
        template={template.data}
        assetBase={sop.data?.document_Uid ?? source.data.document_id}
      />
    ) : loading;
  } else {
    content = <FinalDocument job={job} report={quality.data} template={template.data} onGoToIssues={() => setView('draft')} />;
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <JobHeader job={job} sop={sop.data} />
      <StageStepper job={job} view={view} onChange={setView} />
      {working && view !== 'activity' && states[view] !== 'working' && states[view] !== 'locked' && (
        <div className="shrink-0 border-b border-info/20 bg-info/[0.06] px-4 py-1.5 text-[11px] text-info">
          The pipeline is still working on a later step; this step is shown read-only.
        </div>
      )}
      <ReviewShell
        roomy={view === 'final' || view === 'activity'}
        left={{
          title: 'Original SOP',
          short: 'SOP',
          icon: <FileText className="size-3.5" />,
          content: <SourcePane jobId={job.job_id} source={source.data} documentUid={sop.data?.document_Uid} unitMarks={unplaced} />,
        }}
        right={
          view === 'draft'
            ? {
                title: 'Issues and template',
                short: 'issues',
                icon: <ListChecks className="size-3.5" />,
                content: <DraftSidePane job={job} report={quality.data} source={source.data} template={template.data} />,
              }
            : { title: 'Template', short: 'template', icon: <Layers className="size-3.5" />, content: <TemplatePane jobId={job.job_id} template={template.data} /> }
        }
      >
        {content}
      </ReviewShell>
    </div>
  );
};

const Failed: React.FC<{ job: MigrationJob }> = ({ job }) => (
  <div className="mx-auto max-w-lg px-6 py-12 text-center">
    <AlertCircle className="mx-auto size-8 text-danger" />
    <h3 className="mt-3 text-sm font-semibold text-text-main">The migration stopped on a technical error</h3>
    {job.error && <p className="mt-2 rounded-md border border-danger/30 bg-danger/[0.05] px-3 py-2 text-left font-mono text-[11px] text-text-muted">{job.error}</p>}
    <p className="mt-3 text-xs text-text-muted">Use <span className="text-text-main">Retry</span> above to run it again from the stage that failed.</p>
    <Button size="sm" variant="ghost" className="mt-3" onClick={() => window.location.reload()}>Reload</Button>
  </div>
);
