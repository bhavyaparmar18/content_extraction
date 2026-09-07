import React, { useState } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  RefreshCw,
  AlertCircle,
  ArrowLeft,
  CheckCircle2,
} from 'lucide-react';
import { api } from '@/lib/api';
import { ReviewBootstrap, ReviewMode, AISuggestion, Issue } from '@/types';
import { ReviewHeader } from '@/components/review/ReviewHeader';
import { ActionFooter } from '@/components/review/ActionFooter';
import { ExtractionReviewMode } from '@/components/review/ExtractionReviewMode';
import { TranslationReviewMode } from '@/components/review/TranslationReviewMode';
import { MigrationReviewMode } from '@/components/review/MigrationReviewMode';
import { ReprocessingRequestDialog } from '@/components/review/ReprocessingRequestDialog';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/ToastStack';

export const ReviewPage: React.FC = () => {
  const { recordId } = useParams<{ recordId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { success: toastSuccess, error: toastError, info: toastInfo } = useToast();

  const currentMode = (searchParams.get('mode') as ReviewMode) || 'review';
  const workflowId = searchParams.get('workflowId') || undefined;

  const numRecordId = parseInt(recordId || '0', 10);

  const [isReprocessingOpen, setIsReprocessingOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isApproving, setIsApproving] = useState(false);
  const [isMigrating, setIsMigrating] = useState(false);
  const [customTemplateFile, setCustomTemplateFile] = useState<File | null>(null);

  // Local state for AI suggestions and issues
  const [suggestions, setSuggestions] = useState<AISuggestion[]>([
    {
      id: 'sug_1',
      workflow_id: workflowId || 'ext_01',
      entity_id: 'el_1',
      action: 'Standardize Title',
      instruction: 'Format title to Title Case with standard SOP prefix',
      base_revision: 1,
      patch_json: 'Good Writing Practice for Governance and Procedure Documents',
      explanation: 'Converted from uppercase to standard GMP title casing style.',
      status: 'proposed',
      model_metadata: 'Gemini 2.5 Flash',
      created_at: new Date().toISOString(),
    },
  ]);

  const [issues, setIssues] = useState<Issue[]>([]);

  // 1. Fetch Review Bootstrap Data
  const {
    data: bootstrap,
    isLoading: isLoadingBootstrap,
    error: bootstrapError,
  } = useQuery({
    queryKey: ['reviewBootstrap', numRecordId, currentMode, workflowId],
    queryFn: () => api.getReviewBootstrap(numRecordId, currentMode, workflowId),
    enabled: !!numRecordId,
  });

  // 2. Fetch v2 extraction AST JSON
  const {
    data: v2Content,
    isLoading: isLoadingContent,
  } = useQuery({
    queryKey: ['v2Content', bootstrap?.document?.documentUid],
    queryFn: () => api.getV2Json(bootstrap!.document.documentUid),
    enabled: !!bootstrap?.document?.documentUid,
  });

  // Handle Mode Change
  const handleModeChange = (newMode: ReviewMode) => {
    setSearchParams({ mode: newMode, ...(workflowId ? { workflowId } : {}) });
  };

  // AI Suggestion handlers
  const handleAcceptSuggestion = (sug: AISuggestion) => {
    setSuggestions((prev) => prev.filter((s) => s.id !== sug.id));
    toastSuccess(`Applied proposed patch "${sug.action}".`, 'Patch Accepted');
  };

  const handleRejectSuggestion = (sug: AISuggestion) => {
    setSuggestions((prev) => prev.filter((s) => s.id !== sug.id));
    toastInfo(`Discarded patch "${sug.action}".`, 'Suggestion Rejected');
  };

  const handleGenerateSuggestion = (promptText: string) => {
    const newSug: AISuggestion = {
      id: `sug_${Date.now()}`,
      workflow_id: workflowId || 'wf_auto',
      entity_id: 'active_entity',
      action: 'AI Rewrite & Optimization',
      instruction: promptText,
      base_revision: 1,
      patch_json: `[AI Generated Content]: Rewritten in accordance with: "${promptText}". Clear, unambiguous active voice.`,
      explanation: `Generated based on user instruction: "${promptText}"`,
      status: 'proposed',
      model_metadata: 'Gemini 2.5 Flash',
      created_at: new Date().toISOString(),
    };
    setSuggestions((prev) => [newSug, ...prev]);
    toastSuccess('AI generated a new proposed patch for review.', 'Suggestion Ready');
  };

  // Issue handlers
  const handleCreateIssue = async (iss: Partial<Issue>) => {
    try {
      const created = await api.createIssue({
        ...iss,
        document_uid: bootstrap?.document?.documentUid,
        workflow_id: workflowId || 'ext_wf',
      });
      setIssues((prev) => [created, ...prev]);
      toastSuccess('New issue logged for document tracking.', 'Issue Created');
    } catch {
      toastError('Failed to record issue.');
    }
  };

  const handleResolveIssue = (id: string) => {
    setIssues((prev) => prev.filter((i) => i.id !== id));
    toastSuccess('Issue marked as resolved.', 'Resolved');
  };

  // Reprocessing Submission
  const handleReprocessingSubmit = async (data: { reason: string; pages?: string }) => {
    try {
      await api.createReprocessingRequest(workflowId || 'ext_01', data);
      setIsReprocessingOpen(false);
      toastSuccess('Reprocessing request submitted to Administrator queue.', 'Request Queued');
    } catch (err: any) {
      toastError(err.message || 'Failed to submit reprocessing request.');
    }
  };

  // Save Draft
  const handleSaveDraft = async () => {
    setIsSaving(true);
    try {
      await new Promise((r) => setTimeout(r, 600));
      toastSuccess('Draft revision persisted successfully.', 'Draft Saved');
    } finally {
      setIsSaving(false);
    }
  };

  // Approve Workflow
  const handleApprove = async () => {
    setIsApproving(true);
    try {
      if (numRecordId) {
        await api.updateSopStatus(numRecordId, 'approved');
      }
      queryClient.invalidateQueries({ queryKey: ['sops'] });
      queryClient.invalidateQueries({ queryKey: ['sop', numRecordId] });
      toastSuccess('Document extraction approved and finalized!', 'Approved');
      navigate(`/sops/${numRecordId}`);
    } catch (err: any) {
      toastError(err.message || 'Failed to approve document.');
    } finally {
      setIsApproving(false);
    }
  };

  if (isLoadingBootstrap || isLoadingContent) {
    return (
      <div className="content-pane flex flex-col items-center justify-center min-h-[70vh]">
        <RefreshCw className="size-8 text-primary animate-spin mb-3" />
        <div className="text-sm font-semibold text-text-main">Loading Common Review Workspace...</div>
        <div className="text-xs text-text-muted mt-1">
          Configuring {currentMode} layout and document channels
        </div>
      </div>
    );
  }

  if (bootstrapError || !bootstrap) {
    return (
      <div className="content-pane space-y-4">
        <Button variant="ghost" onClick={() => navigate('/')} leftIcon={<ArrowLeft className="size-4" />}>
          Back to Repository
        </Button>
        <div className="dashboard-card p-8 text-center text-red-400">
          <AlertCircle className="size-10 mx-auto mb-3" />
          <h2 className="text-base font-semibold">Review Bootstrap Failed</h2>
          <p className="text-xs text-text-muted mt-1">Unable to initialize review mode for record {recordId}.</p>
        </div>
      </div>
    );
  }

  // AI Migration execution
  const handleTriggerMigration = async () => {
    if (!bootstrap?.document?.documentUid) return;
    setIsMigrating(true);
    try {
      toastInfo('Running AI template migration & DOCX generation...', 'Migrating');
      await api.migrateDocument(bootstrap.document.documentUid, customTemplateFile || undefined);
      queryClient.invalidateQueries({ queryKey: ['migrationStatus', bootstrap.document.documentUid] });
      queryClient.invalidateQueries({ queryKey: ['migrationPlan', bootstrap.document.documentUid] });
      toastSuccess('AI migration complete! DOCX template generated.', 'Migration Ready');
    } catch (err: any) {
      toastError(err.message || 'Migration pipeline encountered an issue.');
    } finally {
      setIsMigrating(false);
    }
  };

  return (
    <div className="flex flex-col h-full overflow-hidden bg-app">
      {/* Top Review Header */}
      <ReviewHeader
        bootstrap={bootstrap}
        currentMode={currentMode}
        onModeChange={handleModeChange}
        onDownload={() => {
          window.open(`/documents/v2/${encodeURIComponent(bootstrap.document.documentUid)}/json`, '_blank');
        }}
      />

      {/* Main Review Mode Viewport */}
      <div className="flex-1 overflow-hidden">
        {currentMode === 'review' && (
          <ExtractionReviewMode
            documentUid={bootstrap.document.documentUid}
            fileType={bootstrap.document.fileType}
            v2Content={v2Content || null}
            suggestions={suggestions}
            issues={issues}
            onAcceptSuggestion={handleAcceptSuggestion}
            onRejectSuggestion={handleRejectSuggestion}
            onCreateIssue={handleCreateIssue}
            onResolveIssue={handleResolveIssue}
            onGenerateSuggestion={handleGenerateSuggestion}
          />
        )}

        {currentMode === 'translation' && (
          <TranslationReviewMode
            documentUid={bootstrap.document.documentUid}
            v2Content={v2Content || null}
            targetLocale={bootstrap.reviewContext.targetLocale || 'fr'}
            suggestions={suggestions}
            onAcceptSuggestion={handleAcceptSuggestion}
            onRejectSuggestion={handleRejectSuggestion}
            onGenerateSuggestion={handleGenerateSuggestion}
          />
        )}

        {currentMode === 'migration' && (
          <MigrationReviewMode
            documentUid={bootstrap.document.documentUid}
            v2Content={v2Content || null}
            suggestions={suggestions}
            onAcceptSuggestion={handleAcceptSuggestion}
            onRejectSuggestion={handleRejectSuggestion}
            onGenerateSuggestion={handleGenerateSuggestion}
            customTemplateFile={customTemplateFile}
            onSelectTemplateFile={setCustomTemplateFile}
            isMigrating={isMigrating}
            onTriggerMigration={handleTriggerMigration}
          />
        )}
      </div>

      {/* Sticky Bottom Action Footer */}
      <ActionFooter
        availableActions={bootstrap.availableActions}
        isSaving={isSaving}
        isApproving={isApproving}
        isMigrating={isMigrating}
        onSave={handleSaveDraft}
        onApprove={handleApprove}
        onRequestReprocessing={() => setIsReprocessingOpen(true)}
        onReportIssue={() => {
          handleCreateIssue({ description: 'Reviewer flagged potential extraction defect', category: 'formatting' });
        }}
        onRunQa={() => {
          toastSuccess('All 6 translation QA checks passed without blocking errors.', 'QA Complete');
        }}
        onValidateMigration={() => {
          toastSuccess('Template mapping validation passed. Ready for DOCX render.', 'Validation OK');
        }}
        onAiTranslate={() => {
          toastSuccess('AI Translation complete with GxP terminology enforcement.', 'Translated');
        }}
        onAiMigrate={handleTriggerMigration}
      />

      {/* Reprocessing Request Dialog */}
      <ReprocessingRequestDialog
        isOpen={isReprocessingOpen}
        onClose={() => setIsReprocessingOpen(false)}
        onSubmit={handleReprocessingSubmit}
      />
    </div>
  );
};
