import React, { useEffect, useRef } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import { AlertCircle, Loader2 } from 'lucide-react';
import { useMigrationJob, useSopRecord, useTemplateModel } from '@/features/migrations/hooks';
import { ActivityView } from '@/features/migrations/components/ActivityLog';
import { StepBar } from '@/features/migrations/components/StageStepper';
import { getDisplayTitle } from '@/lib/sopDisplay';
import { TRANSLATION_LABELS } from '@/features/translations/activity';
import { useTranslationAudit, useTranslationJob, useTranslationValidation } from '@/features/translations/hooks';
import {
  TRANSLATION_STEPS,
  defaultTranslationStep,
  isTranslationWorking,
  translationStepStates,
  type TranslationStep,
} from '@/features/translations/status';
import type { TranslationJob } from '@/features/translations/types';
import { ReviewBar } from '@/features/translations/components/ReviewBar';
import { TranslationFinal } from '@/features/translations/components/TranslationFinal';
import { TranslationHeader } from '@/features/translations/components/TranslationHeader';
import { StepSummary, TranslationFailed, TranslationProgress } from '@/features/translations/components/TranslationProgress';
import { SegmentReview } from '@/features/translations/components/SegmentReview';

type View = TranslationStep | 'activity';

/** One translation job: its progress, the segment review, the final document. */
export const TranslationWorkspace: React.FC = () => {
  const { jobId = '' } = useParams<{ jobId: string }>();
  const job = useTranslationJob(jobId);
  if (job.isLoading) {
    return (
      <div className="grid h-full place-items-center text-sm text-text-muted">
        <span className="flex items-center gap-2"><Loader2 className="size-4 animate-spin" /> Loading translation…</span>
      </div>
    );
  }
  if (job.error || !job.data) {
    return (
      <div className="content-pane">
        <div className="error-panel flex items-start gap-2 text-sm">
          <AlertCircle className="mt-0.5 size-4 text-danger" />
          <div>
            <div className="font-medium text-text-main">This translation could not be loaded</div>
            <div className="text-xs text-text-muted">{job.error?.message}</div>
          </div>
        </div>
      </div>
    );
  }
  return <Workspace job={job.data} />;
};

const Workspace: React.FC<{ job: TranslationJob }> = ({ job }) => {
  const [params, setParams] = useSearchParams();
  const migration = useMigrationJob(job.migration_job_id);
  const sop = useSopRecord(migration.data?.sop_record_id);
  const template = useTemplateModel(job.migration_job_id, migration.data);
  const validation = useTranslationValidation(job);
  const audit = useTranslationAudit(job);

  // Follow the job to the step that needs the reviewer, unless they picked one.
  const status = useRef(job.status);
  useEffect(() => {
    if (status.current !== job.status) {
      const was = status.current;
      status.current = job.status;
      // A re-render keeps the reviewer where they are; anything else follows the job.
      const rerender = (was === 'REVIEW_PENDING' && job.status === 'RENDERING') || (was === 'RENDERING' && job.status === 'REVIEW_PENDING');
      if (!rerender && params.get('step')) {
        const next = new URLSearchParams(params);
        next.delete('step');
        setParams(next, { replace: true });
      }
    }
  }, [job.status, params, setParams]);

  const states = translationStepStates(job);
  const requested = params.get('step') as View | null;
  const view: View = requested && (requested === 'activity' || states[requested] !== 'locked') ? requested : defaultTranslationStep(job);
  const go = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    Object.entries(changes).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    setParams(next, { replace: true });
  };
  const setView = (v: View) => go({ step: v });
  const openSegment = (segmentId: string) => go({ step: 'review', segment: segmentId, section: null });
  const openIssue = (issueId: string) => go({ step: 'review', issue: issueId, segment: null, section: null });

  const working = isTranslationWorking(job);
  const reviewWorking = job.status === 'RENDERING' || (job.running && job.status === 'REVIEW_PENDING');
  let content: React.ReactNode;
  if (view === 'activity') {
    content = <ActivityView events={audit.data} loading={audit.isLoading} labels={TRANSLATION_LABELS} />;
  } else if ((job.status === 'FAILED_TECHNICAL' || job.status === 'CANCELLED') && states[view] === 'locked') {
    content = <TranslationFailed job={job} />;
  } else if (working && !reviewWorking && (states[view] === 'working' || states[view] === 'locked')) {
    content = <div className="h-full overflow-y-auto"><TranslationProgress job={job} /></div>;
  } else if (view === 'prepare' || view === 'translate') {
    content = <StepSummary job={job} step={view} />;
  } else if (view === 'review') {
    content = <SegmentReview job={job} report={validation.data} template={template.data} />;
  } else {
    content = <TranslationFinal job={job} onOpenSegment={openSegment} />;
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <TranslationHeader job={job} sopTitle={sop.data ? getDisplayTitle(sop.data) : undefined} />
      <StepBar steps={TRANSLATION_STEPS} states={states} view={view} onChange={setView} />
      {(view === 'review' || view === 'final') && (
        <ReviewBar job={job} report={validation.data} onSelectIssue={openIssue} onApproved={() => setView('final')} />
      )}
      <div className="min-h-0 flex-1 overflow-hidden">{content}</div>
    </div>
  );
};
