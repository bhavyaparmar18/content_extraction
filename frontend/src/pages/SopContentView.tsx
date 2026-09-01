import React, { useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  CheckSquare,
  Languages,
  ArrowRightLeft,
  ChevronLeft,
  ChevronRight,
  Download,
  CheckCircle2,
  AlertCircle,
  Clock,
  RefreshCw,
  Layers,
  FileText,
} from 'lucide-react';
import { api } from '@/lib/api';
import { SectionNav } from '@/components/content/SectionNav';
import { ElementRenderer } from '@/components/content/ElementRenderer';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { FileTypeIcon } from '@/components/ui/FileTypeIcon';
import { Button } from '@/components/ui/Button';
import { getDisplayTitle, getDisplaySubline } from '@/lib/sopDisplay';
import { useToast } from '@/components/ui/ToastStack';

export const SopContentView: React.FC = () => {
  const { recordId } = useParams<{ recordId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { success: toastSuccess, error: toastError } = useToast();

  const [activeSectionIdx, setActiveSectionIdx] = useState(0);

  const numRecordId = parseInt(recordId || '0', 10);

  // 1. Fetch SOP record metadata
  const {
    data: sopRecord,
    isLoading: isLoadingRecord,
    error: recordError,
  } = useQuery({
    queryKey: ['sop', numRecordId],
    queryFn: () => api.getSop(numRecordId),
    enabled: !!numRecordId,
  });

  // 2. Fetch v2 extraction JSON
  const {
    data: v2Content,
    isLoading: isLoadingContent,
    error: contentError,
  } = useQuery({
    queryKey: ['v2Content', sopRecord?.document_Uid],
    queryFn: () => api.getV2Json(sopRecord!.document_Uid),
    enabled: !!sopRecord?.document_Uid,
  });

  // Status update mutation
  const statusMutation = useMutation({
    mutationFn: (newStatus: string) => api.updateSopStatus(numRecordId, newStatus),
    onSuccess: (updated) => {
      toastSuccess(`SOP status set to "${updated.status}".`, 'Status Updated');
      queryClient.invalidateQueries({ queryKey: ['sop', numRecordId] });
      queryClient.invalidateQueries({ queryKey: ['sops'] });
    },
    onError: (err: any) => {
      toastError(err.message || 'Failed to update review status.');
    },
  });

  if (isLoadingRecord || isLoadingContent) {
    return (
      <div className="content-pane flex flex-col items-center justify-center min-h-[60vh]">
        <RefreshCw className="size-8 text-primary animate-spin mb-3" />
        <div className="text-sm font-semibold text-text-main">Loading Document Content...</div>
        <div className="text-xs text-text-muted mt-1">Retrieving extracted structure and AST</div>
      </div>
    );
  }

  if (recordError || !sopRecord) {
    return (
      <div className="content-pane space-y-4">
        <Button variant="ghost" onClick={() => navigate('/')} leftIcon={<ArrowLeft className="size-4" />}>
          Back to Repository
        </Button>
        <div className="dashboard-card p-8 text-center text-red-400">
          <AlertCircle className="size-10 mx-auto mb-3" />
          <h2 className="text-base font-semibold">SOP Record Not Found</h2>
          <p className="text-xs text-text-muted mt-1">The requested document record does not exist.</p>
        </div>
      </div>
    );
  }

  const sections = v2Content?.sections || [];
  const activeSection = sections[activeSectionIdx] || sections[0];
  const title = getDisplayTitle(sopRecord);
  const subline = getDisplaySubline(sopRecord);

  const downloadJson = () => {
    window.open(`/documents/v2/${encodeURIComponent(sopRecord.document_Uid)}/json`, '_blank');
  };

  return (
    <div className="content-pane space-y-6">
      {/* Top Navigation & Status Bar */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between border-b border-border pb-5">
        <div className="flex items-start gap-3">
          <Button
            variant="icon"
            onClick={() => navigate('/')}
            className="shrink-0 mt-1"
            title="Back to Repository"
            aria-label="Back"
          >
            <ArrowLeft className="size-4" />
          </Button>

          <FileTypeIcon fileType={sopRecord.file_type} size="lg" className="shrink-0 mt-0.5" />

          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight text-text-main sm:text-2xl">
                {title}
              </h1>
              <StatusBadge status={sopRecord.status} size="sm" />
            </div>
            <p className="text-xs text-text-muted mt-1">{subline}</p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Status Selectors */}
          <div className="flex items-center rounded-lg border border-border bg-black/10 p-1">
            <button
              type="button"
              onClick={() => statusMutation.mutate('in_review')}
              className={`px-2.5 py-1 text-xs rounded transition font-medium ${
                sopRecord.status === 'in_review'
                  ? 'bg-amber-500/20 text-amber-400 font-semibold'
                  : 'text-text-muted hover:text-text-main'
              }`}
            >
              In Review
            </button>
            <button
              type="button"
              onClick={() => statusMutation.mutate('approved')}
              className={`px-2.5 py-1 text-xs rounded transition font-medium ${
                sopRecord.status === 'approved'
                  ? 'bg-emerald-500/20 text-emerald-400 font-semibold'
                  : 'text-text-muted hover:text-text-main'
              }`}
            >
              Approve
            </button>
            <button
              type="button"
              onClick={() => statusMutation.mutate('rejected')}
              className={`px-2.5 py-1 text-xs rounded transition font-medium ${
                sopRecord.status === 'rejected'
                  ? 'bg-red-500/20 text-red-400 font-semibold'
                  : 'text-text-muted hover:text-text-main'
              }`}
            >
              Reject
            </button>
          </div>

          <Button
            variant="secondary"
            size="sm"
            onClick={downloadJson}
            leftIcon={<Download className="size-3.5" />}
          >
            JSON
          </Button>

          <Button
            variant="primary"
            size="sm"
            onClick={() => navigate(`/review/${sopRecord.id}?mode=review`)}
            leftIcon={<CheckSquare className="size-3.5" />}
          >
            Open Review
          </Button>
        </div>
      </div>

      {/* Main Content Layout: 2 Columns */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-12">
        {/* Left Section Navigation (4 cols) */}
        <div className="lg:col-span-4">
          <SectionNav
            sections={sections}
            activeSectionIdx={activeSectionIdx}
            onSelectSection={setActiveSectionIdx}
          />
        </div>

        {/* Right Section Content Pane (8 cols) */}
        <div className="lg:col-span-8 space-y-6">
          {activeSection ? (
            <div className="dashboard-card p-6 sm:p-8 space-y-6">
              {/* Section Header */}
              <div className="border-b border-border pb-4">
                <div className="flex items-center gap-2 text-xs font-mono font-semibold text-primary uppercase">
                  <span>SECTION {activeSection.section_number}</span>
                  <span>•</span>
                  <span>Pages {activeSection.page_start}–{activeSection.page_end}</span>
                </div>
                <h2 className="text-2xl font-bold text-text-main mt-1">
                  {activeSection.title || `Section ${activeSection.section_number}`}
                </h2>
              </div>

              {/* Elements Rendering */}
              <div className="space-y-4">
                {activeSection.elements?.length > 0 ? (
                  activeSection.elements.map((el, idx) => (
                    <ElementRenderer
                      key={idx}
                      element={el}
                      documentId={sopRecord.document_Uid}
                      index={idx}
                    />
                  ))
                ) : (
                  <div className="text-xs text-text-muted italic p-4 text-center">
                    No structured elements parsed in this section.
                  </div>
                )}
              </div>

              {/* Section Pagination Stepper Footer */}
              <div className="flex items-center justify-between border-t border-border pt-6 mt-8">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={activeSectionIdx === 0}
                  onClick={() => setActiveSectionIdx((prev) => Math.max(prev - 1, 0))}
                  leftIcon={<ChevronLeft className="size-4" />}
                >
                  Previous Section
                </Button>

                <span className="text-xs font-mono text-text-muted">
                  Section {activeSectionIdx + 1} of {sections.length}
                </span>

                <Button
                  variant="secondary"
                  size="sm"
                  disabled={activeSectionIdx >= sections.length - 1}
                  onClick={() => setActiveSectionIdx((prev) => Math.min(prev + 1, sections.length - 1))}
                  rightIcon={<ChevronRight className="size-4" />}
                >
                  Next Section
                </Button>
              </div>
            </div>
          ) : (
            <div className="dashboard-card p-8 text-center text-text-muted">
              <FileText className="size-10 mx-auto mb-2 opacity-40" />
              <p className="text-sm font-medium">No sections found in this document extraction.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
