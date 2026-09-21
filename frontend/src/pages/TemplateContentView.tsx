import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Download,
  Sparkles,
  RefreshCw,
  AlertCircle,
  FileText,
  Tag,
  X,
} from 'lucide-react';
import { api } from '@/lib/api';
import { SectionNav } from '@/components/content/SectionNav';
import { ElementRenderer } from '@/components/content/ElementRenderer';
import { StatusBadge } from '@/components/ui/StatusBadge';
import { FileTypeIcon } from '@/components/ui/FileTypeIcon';
import { Button } from '@/components/ui/Button';
import { useToast } from '@/components/ui/ToastStack';
import { AnimatePresence, motion } from 'framer-motion';

export const TemplateContentView: React.FC = () => {
  const { templateId } = useParams<{ templateId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { success: toastSuccess, error: toastError, info: toastInfo } = useToast();

  const [activeSectionIdx, setActiveSectionIdx] = useState(0);
  const [isGlobalRulesOpen, setIsGlobalRulesOpen] = useState(false);

  // 1. Fetch template record
  const {
    data: templateRecord,
    isLoading: isLoadingRecord,
    error: recordError,
  } = useQuery({
    queryKey: ['template', templateId],
    queryFn: () => (templateId ? api.getTemplate(templateId) : null),
    enabled: !!templateId,
  });

  // 2. Fetch template extraction output JSON
  const {
    data: templateContent,
    isLoading: isLoadingContent,
    error: contentError,
  } = useQuery({
    queryKey: ['templateContent', templateId],
    queryFn: () => (templateId ? api.getTemplateContent(templateId) : null),
    enabled: !!templateId,
  });

  // Re-extraction mutation
  const extractMutation = useMutation({
    mutationFn: (tId: string) => api.extractTemplate(tId),
    onMutate: () => {
      toastInfo(`Running extraction pipeline on template '${templateId}'...`, 'Extracting');
    },
    onSuccess: (res) => {
      toastSuccess(
        `Extracted ${res.total_sections} sections, ${res.total_instructions} instructions, ${res.total_icons} icons.`,
        'Template Updated'
      );
      queryClient.invalidateQueries({ queryKey: ['template', templateId] });
      queryClient.invalidateQueries({ queryKey: ['templateContent', templateId] });
      queryClient.invalidateQueries({ queryKey: ['templates'] });
    },
    onError: (err: any) => {
      toastError(err.message || 'Extraction failed.');
    },
  });

  if (isLoadingRecord || isLoadingContent) {
    return (
      <div className="content-pane flex flex-col items-center justify-center min-h-[60vh]">
        <RefreshCw className="size-8 text-primary animate-spin mb-3" />
        <div className="text-sm font-semibold text-text-main">Loading Template Content...</div>
        <div className="text-xs text-text-muted mt-1">Retrieving sections, tables, and icons</div>
      </div>
    );
  }

  if (recordError || !templateRecord) {
    return (
      <div className="content-pane space-y-4">
        <Button variant="ghost" onClick={() => navigate('/templates')} leftIcon={<ArrowLeft className="size-4" />}>
          Back to Templates
        </Button>
        <div className="dashboard-card p-8 text-center text-red-400">
          <AlertCircle className="size-10 mx-auto mb-3" />
          <h2 className="text-base font-semibold">Template Not Found</h2>
          <p className="text-xs text-text-muted mt-1">The requested template '{templateId}' does not exist.</p>
        </div>
      </div>
    );
  }

  if (contentError || !templateContent) {
    const errMsg = (contentError as any)?.message || 'Extraction output not available.';
    return (
      <div className="content-pane space-y-4">
        <Button variant="ghost" onClick={() => navigate('/templates')} leftIcon={<ArrowLeft className="size-4" />}>
          Back to Templates
        </Button>
        <div className="dashboard-card p-8 text-center text-amber-400">
          <AlertCircle className="size-10 mx-auto mb-3" />
          <h2 className="text-base font-semibold">Template Extraction Required</h2>
          <p className="text-xs text-text-muted mt-1 max-w-sm mx-auto">
            This template has been uploaded but its structured content has not been extracted yet.
          </p>
          <p className="text-xs font-mono text-amber-400/80 mt-3 bg-black/20 rounded px-3 py-1.5 inline-block">
            {errMsg}
          </p>
          <div className="mt-5">
            <Button
              variant="primary"
              isLoading={extractMutation.isPending}
              onClick={() => templateId && extractMutation.mutate(templateId)}
              leftIcon={<Sparkles className="size-4" />}
            >
              Run Extraction
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const sections = templateContent.sections || [];
  const activeSection = sections[activeSectionIdx] || sections[0];
  const globalRules = templateContent.global_rules?.instructions || [];

  const downloadJson = () => {
    window.open(api.getDownloadTemplateJsonUrl(templateRecord.template_uid), '_blank');
  };

  return (
    <div className="content-pane space-y-6">
      {/* Top Navigation & Status Bar */}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between border-b border-border pb-5">
        <div className="flex items-start gap-3">
          <Button
            variant="icon"
            onClick={() => navigate('/templates')}
            className="shrink-0 mt-1"
            title="Back to Templates"
            aria-label="Back"
          >
            <ArrowLeft className="size-4" />
          </Button>

          <FileTypeIcon fileType={templateRecord.file_type || 'docx'} size="lg" className="shrink-0 mt-0.5" />

          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-bold tracking-tight text-text-main sm:text-2xl">
                {templateRecord.template_name || templateContent.template_name || templateId}
              </h1>
              <span className="rounded bg-surface px-2 py-0.5 text-xs font-mono font-medium text-text-main border border-border">
                v{templateRecord.template_version}
              </span>
              <StatusBadge status={templateRecord.status} size="sm" />
            </div>
            <div className="text-xs text-text-muted mt-1 flex flex-wrap items-center gap-2.5 font-mono">
              <span>Sections: {sections.length}</span>
              <span>•</span>
              <span className="text-sky-400">Instructions: {templateContent.total_instructions || 0}</span>
              <span>•</span>
              <span className="text-purple-400">Icons: {templateContent.total_icons || 0}</span>
              {templateRecord.file_size_bytes && (
                <>
                  <span>•</span>
                  <span>{(templateRecord.file_size_bytes / 1024).toFixed(1)} KB</span>
                </>
              )}
            </div>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2.5">
          {globalRules.length > 0 && (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => setIsGlobalRulesOpen(true)}
              leftIcon={<Sparkles className="size-3.5 text-sky-400" />}
            >
              Global Rules ({globalRules.length})
            </Button>
          )}

          <Button
            variant="secondary"
            size="sm"
            onClick={downloadJson}
            leftIcon={<Download className="size-3.5" />}
          >
            Download JSON
          </Button>

          <Button
            variant="secondary"
            size="sm"
            isLoading={extractMutation.isPending}
            onClick={() => templateId && extractMutation.mutate(templateId)}
            leftIcon={<RefreshCw className="size-3.5 text-primary" />}
          >
            Re-extract
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
            title="Template Sections"
          />
        </div>

        {/* Right Section Content Pane (8 cols) */}
        <div className="lg:col-span-8 space-y-6">
          {activeSection ? (
            <div className="dashboard-card p-6 sm:p-8 space-y-6">
              {/* Section Header */}
              <div className="border-b border-border pb-4">
                <div className="flex items-center gap-2 text-xs font-mono font-semibold text-primary uppercase">
                  <span>
                    SECTION{' '}
                    {activeSection.section_number !== undefined && activeSection.section_number !== null
                      ? activeSection.section_number
                      : activeSectionIdx}
                  </span>
                  <span>•</span>
                  <span>
                    Pages {activeSection.page_start}–{activeSection.page_end}
                  </span>
                  {activeSection.instructions && activeSection.instructions.length > 0 && (
                    <>
                      <span>•</span>
                      <span className="text-sky-400 font-medium lowercase">
                        {activeSection.instructions.length} instructions
                      </span>
                    </>
                  )}
                </div>
                <h2 className="text-2xl font-bold text-text-main mt-1">
                  {activeSection.title || `Section ${activeSection.section_number || activeSectionIdx}`}
                </h2>
              </div>

              {/* Elements Rendering */}
              <div className="space-y-4">
                {activeSection.elements?.length > 0 ? (
                  activeSection.elements.map((el, idx) => (
                    <ElementRenderer
                      key={idx}
                      element={el}
                      documentId={templateRecord.template_uid}
                      isTemplate={true}
                      index={idx}
                    />
                  ))
                ) : (
                  <div className="text-xs text-text-muted italic p-6 text-center bg-black/10 rounded-lg border border-border/50">
                    No structured body elements parsed in this section.
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
              <p className="text-sm font-medium">No sections found in this template extraction.</p>
            </div>
          )}
        </div>
      </div>

      {/* Global Rules Modal Drawer */}
      <AnimatePresence>
        {isGlobalRulesOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/75 backdrop-blur-sm"
              onClick={() => setIsGlobalRulesOpen(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 15 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 15 }}
              className="relative w-full max-w-2xl max-h-[80vh] rounded-2xl border border-border bg-card shadow-2xl z-10 flex flex-col overflow-hidden"
            >
              <div className="p-4 border-b border-border bg-card/80 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-2.5 text-sky-400 font-bold text-sm">
                  <Sparkles className="size-4" />
                  <span>Document-Wide Global Rules ({globalRules.length})</span>
                </div>
                <button
                  onClick={() => setIsGlobalRulesOpen(false)}
                  className="text-text-muted hover:text-text-main p-1.5 rounded-lg hover:bg-surface transition"
                >
                  <X className="size-4" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-5 space-y-3 bg-app">
                <p className="text-xs text-text-muted leading-relaxed">
                  These instructions were written in blue font before the first section heading. They
                  specify global document requirements, formatting, or scope applicable to the entire
                  migrated SOP.
                </p>

                <div className="space-y-2.5 mt-2">
                  {globalRules.map((rule, rIdx) => (
                    <div
                      key={rIdx}
                      className="p-3 rounded-xl border border-sky-500/20 bg-sky-500/5 text-xs text-sky-200 flex items-start gap-3"
                    >
                      <span className="size-5 shrink-0 rounded-full bg-sky-500/20 text-sky-300 font-mono text-[10px] grid place-items-center">
                        {rIdx + 1}
                      </span>
                      <div className="flex-1">
                        <p className="font-medium text-sky-100 leading-relaxed">{rule.text}</p>
                        {rule.font_color_hex && (
                          <div className="mt-1 text-[10px] text-sky-400/70 font-mono">
                            Color: #{rule.font_color_hex}
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};
