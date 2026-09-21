import React, { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Layers,
  Upload,
  RefreshCw,
  Trash2,
  FileCode,
  CheckCircle2,
  AlertCircle,
  Clock,
  Eye,
  ChevronDown,
  ChevronRight,
  Info,
  Sparkles,
  Table as TableIcon,
  Image as ImageIcon,
  Tag,
  X,
  FileText,
  BookOpen,
  ExternalLink,
} from 'lucide-react';
import { api } from '@/lib/api';
import { TemplateRecord, TemplateExtractionOutput, TemplateSection, TemplateElement } from '@/types';
import { ElementRenderer } from '@/components/content/ElementRenderer';
import { Button } from '@/components/ui/Button';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/ToastStack';

export const TemplateManagement: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { success: toastSuccess, error: toastError, info: toastInfo } = useToast();

  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [customName, setCustomName] = useState('');
  const [isUploading, setIsUploading] = useState(false);

  const [extractingId, setExtractingId] = useState<string | null>(null);
  const [templateToDelete, setTemplateToDelete] = useState<TemplateRecord | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);

  // Inspector modal state
  const [inspectTemplateId, setInspectTemplateId] = useState<string | null>(null);
  const [inspectorTab, setInspectorTab] = useState<'sections' | 'global_rules' | 'icons'>('sections');
  const [expandedSections, setExpandedSections] = useState<Record<number, boolean>>({ 0: true });

  // 1. Fetch templates
  const {
    data: templates = [],
    isLoading,
    isRefetching,
    refetch,
  } = useQuery<TemplateRecord[]>({
    queryKey: ['templates'],
    queryFn: () => api.getTemplates(),
    staleTime: 4000,
  });

  // 2. Fetch inspection content if a template is selected
  const {
    data: inspectedContent,
    isLoading: isLoadingContent,
  } = useQuery<TemplateExtractionOutput | null>({
    queryKey: ['templateContent', inspectTemplateId],
    queryFn: () => (inspectTemplateId ? api.getTemplateContent(inspectTemplateId) : null),
    enabled: !!inspectTemplateId,
  });

  // Stats calculation
  const stats = useMemo(() => {
    const total = templates.length;
    const ready = templates.filter((t) => t.status === 'ready').length;
    const instructions = templates.reduce((acc, t) => acc + (t.total_instructions || 0), 0);
    const icons = templates.reduce((acc, t) => acc + (t.total_icons || 0), 0);
    return { total, ready, instructions, icons };
  }, [templates]);

  // Handle File Upload
  const handleUploadSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      toastError('Please select a .docx template file.');
      return;
    }
    if (!selectedFile.name.toLowerCase().endsWith('.docx')) {
      toastError('Only .docx template documents are supported.');
      return;
    }

    setIsUploading(true);
    try {
      const resp = await api.uploadTemplate(selectedFile, customName.trim() || undefined);
      toastSuccess(resp.message || 'Template uploaded successfully!', 'Upload Complete');
      setIsUploadOpen(false);
      setSelectedFile(null);
      setCustomName('');
      queryClient.invalidateQueries({ queryKey: ['templates'] });

      // Automatically offer extraction if newly uploaded
      if (resp.template_id) {
        handleExtract(resp.template_id);
      }
    } catch (err: any) {
      toastError(err.message || 'Failed to upload template.');
    } finally {
      setIsUploading(false);
    }
  };

  // Handle Extraction Trigger
  const handleExtract = async (templateUid: string) => {
    setExtractingId(templateUid);
    toastInfo(`Running extraction pipeline on template '${templateUid}'...`, 'Extracting Template');
    try {
      const res = await api.extractTemplate(templateUid);
      toastSuccess(
        `Extracted ${res.total_sections} sections, ${res.total_instructions} blue instructions, ${res.total_icons} icons.`,
        'Template Ready'
      );
      queryClient.invalidateQueries({ queryKey: ['templates'] });
      if (inspectTemplateId === templateUid) {
        queryClient.invalidateQueries({ queryKey: ['templateContent', templateUid] });
      }
    } catch (err: any) {
      toastError(err.message || 'Extraction failed for template.');
      queryClient.invalidateQueries({ queryKey: ['templates'] });
    } finally {
      setExtractingId(null);
    }
  };

  // Handle Delete
  const handleDeleteConfirm = async () => {
    if (!templateToDelete) return;
    setIsDeleting(true);
    try {
      await api.deleteTemplate(templateToDelete.template_uid);
      toastSuccess(`Template '${templateToDelete.template_name}' removed.`, 'Deleted');
      setTemplateToDelete(null);
      if (inspectTemplateId === templateToDelete.template_uid) {
        setInspectTemplateId(null);
      }
      queryClient.invalidateQueries({ queryKey: ['templates'] });
    } catch (err: any) {
      toastError(err.message || 'Failed to delete template.');
    } finally {
      setIsDeleting(false);
    }
  };

  const toggleSectionExpand = (idx: number) => {
    setExpandedSections((prev) => ({ ...prev, [idx]: !prev[idx] }));
  };

  return (
    <div className="flex flex-col min-h-screen p-6 max-w-7xl mx-auto space-y-6">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-border pb-6">
        <div>
          <div className="flex items-center gap-2.5">
            <div className="grid size-9 place-items-center rounded-xl bg-primary/10 border border-primary/30 text-primary shadow-glow">
              <Layers className="size-5" />
            </div>
            <h1 className="text-xl font-bold tracking-tight text-text-main">
              SOP Template Management
            </h1>
          </div>
          <p className="mt-1 text-xs text-text-muted max-w-2xl leading-relaxed">
            Upload, inspect, and extract corporate SOP templates. Identifies blue-font authoring
            instructions, isolates global document rules, and co-locates icons with section content.
          </p>
        </div>

        <div className="flex items-center gap-2.5 shrink-0">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => refetch()}
            isLoading={isRefetching}
            leftIcon={<RefreshCw className="size-3.5" />}
          >
            Refresh
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={() => setIsUploadOpen(true)}
            leftIcon={<Upload className="size-3.5" />}
          >
            Upload Template (.docx)
          </Button>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="dashboard-card p-4 border border-border bg-card/60">
          <div className="text-[11px] font-semibold text-text-muted uppercase tracking-wider">
            Total Templates
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-2xl font-black tracking-tight text-text-main">
              {stats.total}
            </span>
            <span className="text-[10px] text-text-muted font-mono">DOCX only</span>
          </div>
        </div>

        <div className="dashboard-card p-4 border border-emerald-500/20 bg-emerald-500/5">
          <div className="text-[11px] font-semibold text-emerald-400 uppercase tracking-wider flex items-center gap-1.5">
            <CheckCircle2 className="size-3.5" /> Ready for Migration
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-2xl font-black tracking-tight text-emerald-400">
              {stats.ready}
            </span>
            <span className="text-[10px] text-emerald-500/80 font-mono">Active</span>
          </div>
        </div>

        <div className="dashboard-card p-4 border border-sky-500/20 bg-sky-500/5">
          <div className="text-[11px] font-semibold text-sky-400 uppercase tracking-wider flex items-center gap-1.5">
            <Sparkles className="size-3.5" /> Blue Instructions
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-2xl font-black tracking-tight text-sky-400">
              {stats.instructions}
            </span>
            <span className="text-[10px] text-sky-400/80 font-mono">Detected</span>
          </div>
        </div>

        <div className="dashboard-card p-4 border border-purple-500/20 bg-purple-500/5">
          <div className="text-[11px] font-semibold text-purple-400 uppercase tracking-wider flex items-center gap-1.5">
            <Tag className="size-3.5" /> Extracted Icons
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-2xl font-black tracking-tight text-purple-400">
              {stats.icons}
            </span>
            <span className="text-[10px] text-purple-400/80 font-mono">Mapped</span>
          </div>
        </div>
      </div>

      {/* Templates Table Card */}
      <div className="dashboard-card border border-border bg-card/70 overflow-hidden">
        <div className="px-5 py-3.5 border-b border-border bg-card/80 flex items-center justify-between">
          <h2 className="text-xs font-bold uppercase tracking-wider text-text-muted flex items-center gap-2">
            <FileCode className="size-4 text-primary" /> Registered Templates
          </h2>
          <span className="text-[11px] text-text-muted font-mono">
            {templates.length} record{templates.length === 1 ? '' : 's'}
          </span>
        </div>

        {isLoading ? (
          <div className="p-12 flex flex-col items-center justify-center text-text-muted">
            <RefreshCw className="size-7 animate-spin text-primary mb-3" />
            <span className="text-xs font-medium">Loading templates...</span>
          </div>
        ) : templates.length === 0 ? (
          <div className="p-12 text-center text-text-muted">
            <Layers className="size-10 mx-auto mb-3 text-text-muted/40" />
            <h3 className="text-sm font-semibold text-text-main">No Templates Registered</h3>
            <p className="text-xs mt-1 max-w-sm mx-auto">
              Upload your first SOP template .docx file to extract section structures, blue instruction
              rules, and icons for migration.
            </p>
            <Button
              variant="primary"
              size="sm"
              className="mt-4"
              onClick={() => setIsUploadOpen(true)}
              leftIcon={<Upload className="size-3.5" />}
            >
              Upload Template (.docx)
            </Button>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="border-b border-border bg-surface/40 text-[11px] font-semibold text-text-muted">
                  <th className="py-3 px-4">Template Name</th>
                  <th className="py-3 px-4">Version</th>
                  <th className="py-3 px-4">Status</th>
                  <th className="py-3 px-4 text-center">Sections</th>
                  <th className="py-3 px-4 text-center">Instructions (Blue)</th>
                  <th className="py-3 px-4 text-center">Icons</th>
                  <th className="py-3 px-4">Registered Date</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {templates.map((tpl) => {
                  const isExtracting = extractingId === tpl.template_uid || tpl.status === 'extracting';

                  return (
                    <tr
                      key={tpl.id}
                      className="hover:bg-card-hover/40 transition group"
                    >
                      <td className="py-3.5 px-4">
                        <div
                          className={`font-semibold text-text-main transition ${
                            tpl.status === 'ready' ? 'cursor-pointer hover:text-primary' : ''
                          }`}
                          onClick={() => tpl.status === 'ready' && navigate(`/templates/${tpl.template_uid}`)}
                          title={tpl.status === 'ready' ? 'Click to view full template content' : undefined}
                        >
                          {tpl.template_name}
                        </div>
                        <div className="text-[10px] text-text-muted font-mono mt-0.5">
                          UID: {tpl.template_uid}
                        </div>
                      </td>

                      <td className="py-3.5 px-4 font-mono">
                        <span className="rounded bg-surface px-1.5 py-0.5 text-[10px] font-medium text-text-main border border-border">
                          v{tpl.template_version}
                        </span>
                      </td>

                      <td className="py-3.5 px-4">
                        {tpl.status === 'ready' && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                            <CheckCircle2 className="size-3" /> Ready
                          </span>
                        )}
                        {tpl.status === 'extracting' && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-sky-500/10 text-sky-400 border border-sky-500/30 animate-pulse">
                            <RefreshCw className="size-3 animate-spin" /> Extracting
                          </span>
                        )}
                        {tpl.status === 'uploaded' && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-500/10 text-slate-400 border border-slate-500/30">
                            <Clock className="size-3" /> Uploaded
                          </span>
                        )}
                        {tpl.status === 'failed' && (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-red-500/10 text-red-400 border border-red-500/30">
                            <AlertCircle className="size-3" /> Failed
                          </span>
                        )}
                      </td>

                      <td className="py-3.5 px-4 text-center font-mono font-medium text-text-main">
                        {tpl.total_sections || 0}
                      </td>

                      <td className="py-3.5 px-4 text-center">
                        <span className="inline-flex items-center gap-1 rounded bg-sky-500/10 px-2 py-0.5 text-[11px] font-mono text-sky-400 border border-sky-500/20">
                          {tpl.total_instructions || 0}
                        </span>
                      </td>

                      <td className="py-3.5 px-4 text-center">
                        <span className="inline-flex items-center gap-1 rounded bg-purple-500/10 px-2 py-0.5 text-[11px] font-mono text-purple-400 border border-purple-500/20">
                          {tpl.total_icons || 0}
                        </span>
                      </td>

                      <td className="py-3.5 px-4 text-text-muted text-[11px]">
                        {new Date(tpl.created_at).toLocaleDateString(undefined, {
                          year: 'numeric',
                          month: 'short',
                          day: 'numeric',
                        })}
                      </td>

                      <td className="py-3.5 px-4 text-right">
                        <div className="flex items-center justify-end gap-1.5">
                          {tpl.status === 'ready' && (
                            <>
                              <Button
                                variant="primary"
                                size="sm"
                                onClick={() => navigate(`/templates/${tpl.template_uid}`)}
                                leftIcon={<BookOpen className="size-3.5" />}
                                title="View full template document with sections, tables, and icons"
                              >
                                View
                              </Button>
                              <Button
                                variant="secondary"
                                size="sm"
                                onClick={() => {
                                  setInspectTemplateId(tpl.template_uid);
                                  setInspectorTab('sections');
                                }}
                                leftIcon={<Eye className="size-3.5" />}
                                title="Inspect template sections and instructions in drawer"
                              >
                                Inspect
                              </Button>
                            </>
                          )}

                          <Button
                            variant="secondary"
                            size="sm"
                            isLoading={isExtracting}
                            onClick={() => handleExtract(tpl.template_uid)}
                            leftIcon={<Sparkles className="size-3.5 text-primary" />}
                            title="Run or re-run template extraction"
                          >
                            {tpl.status === 'ready' ? 'Re-extract' : 'Extract'}
                          </Button>

                          <Button
                            variant="icon"
                            size="sm"
                            onClick={() => setTemplateToDelete(tpl)}
                            title="Delete template record"
                          >
                            <Trash2 className="size-3.5 text-red-400 hover:text-red-300 transition" />
                          </Button>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Upload Modal */}
      <AnimatePresence>
        {isUploadOpen && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/70 backdrop-blur-sm"
              onClick={() => !isUploading && setIsUploadOpen(false)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 10 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 10 }}
              className="relative w-full max-w-lg rounded-xl border border-border bg-card p-6 shadow-panel z-10"
            >
              <div className="flex items-center justify-between border-b border-border pb-3">
                <div className="flex items-center gap-2">
                  <div className="grid size-8 place-items-center rounded-lg bg-primary/10 text-primary">
                    <Upload className="size-4" />
                  </div>
                  <h3 className="text-base font-bold text-text-main">Upload SOP Template</h3>
                </div>
                <button
                  onClick={() => setIsUploadOpen(false)}
                  disabled={isUploading}
                  className="text-text-muted hover:text-text-main p-1"
                >
                  <X className="size-4" />
                </button>
              </div>

              <form onSubmit={handleUploadSubmit} className="space-y-4 mt-4">
                {/* Drag and Drop Zone */}
                <div>
                  <label className="block text-xs font-semibold text-text-muted mb-1.5">
                    Template Document (.docx)
                  </label>
                  <label className="flex flex-col items-center justify-center border-2 border-dashed border-border hover:border-primary/50 bg-surface/50 hover:bg-surface/80 rounded-xl p-6 cursor-pointer transition">
                    <FileCode className="size-8 text-primary mb-2" />
                    {selectedFile ? (
                      <div className="text-center">
                        <div className="text-xs font-semibold text-text-main">
                          {selectedFile.name}
                        </div>
                        <div className="text-[10px] text-text-muted mt-0.5">
                          {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB
                        </div>
                      </div>
                    ) : (
                      <div className="text-center">
                        <div className="text-xs font-medium text-text-main">
                          Click to browse or drag & drop template file
                        </div>
                        <div className="text-[10px] text-text-muted mt-0.5">
                          Only Microsoft Word (.docx) files supported
                        </div>
                      </div>
                    )}
                    <input
                      type="file"
                      accept=".docx"
                      className="hidden"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) setSelectedFile(file);
                      }}
                    />
                  </label>
                </div>

                {/* Optional Name */}
                <div>
                  <label className="block text-xs font-semibold text-text-muted mb-1.5">
                    Template Display Name (Optional)
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. Standard GP SOP Template 2026"
                    value={customName}
                    onChange={(e) => setCustomName(e.target.value)}
                    className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-xs text-text-main placeholder:text-text-muted focus:border-primary focus:outline-none"
                  />
                  <div className="text-[10px] text-text-muted mt-1">
                    If left blank, the original filename stem will be used.
                  </div>
                </div>

                <div className="rounded-lg border border-sky-500/20 bg-sky-500/5 p-3 text-[11px] text-sky-300 flex items-start gap-2">
                  <Info className="size-4 shrink-0 text-sky-400 mt-0.5" />
                  <div>
                    Blue font paragraphs inside the template will automatically be tagged as
                    authoring instructions during extraction.
                  </div>
                </div>

                <div className="flex items-center justify-end gap-2.5 pt-2">
                  <Button
                    type="button"
                    variant="secondary"
                    onClick={() => setIsUploadOpen(false)}
                    disabled={isUploading}
                  >
                    Cancel
                  </Button>
                  <Button
                    type="submit"
                    variant="primary"
                    isLoading={isUploading}
                    leftIcon={<Upload className="size-3.5" />}
                  >
                    Upload & Extract
                  </Button>
                </div>
              </form>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Inspector Modal / Drawer */}
      <AnimatePresence>
        {inspectTemplateId && (
          <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 bg-black/75 backdrop-blur-sm"
              onClick={() => setInspectTemplateId(null)}
            />
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 15 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 15 }}
              className="relative w-full max-w-4xl h-[85vh] rounded-2xl border border-border bg-card shadow-2xl z-10 flex flex-col overflow-hidden"
            >
              {/* Modal Header */}
              <div className="p-4 border-b border-border bg-card/80 flex items-center justify-between shrink-0">
                <div className="flex items-center gap-3">
                  <div className="grid size-9 place-items-center rounded-xl bg-primary/10 border border-primary/30 text-primary">
                    <FileCode className="size-5" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-text-main flex items-center gap-2">
                      {inspectedContent?.template_name || inspectTemplateId}
                      <span className="rounded bg-surface px-1.5 py-0.5 text-[10px] font-mono text-text-muted border border-border">
                        {inspectedContent?.version ? `v${inspectedContent.version}` : 'DOCX'}
                      </span>
                    </h3>
                    <div className="text-[11px] text-text-muted mt-0.5 flex items-center gap-3 font-mono">
                      <span>Sections: {inspectedContent?.sections?.length || 0}</span>
                      <span>•</span>
                      <span>Instructions: {inspectedContent?.total_instructions || 0}</span>
                      <span>•</span>
                      <span>Icons: {inspectedContent?.total_icons || 0}</span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <div className="flex rounded-lg border border-border bg-surface p-0.5 text-xs font-semibold">
                    <button
                      onClick={() => setInspectorTab('sections')}
                      className={`px-3 py-1 rounded-md transition ${
                        inspectorTab === 'sections'
                          ? 'bg-primary text-slate-950 font-bold'
                          : 'text-text-muted hover:text-text-main'
                      }`}
                    >
                      Sections ({inspectedContent?.sections?.length || 0})
                    </button>
                    <button
                      onClick={() => setInspectorTab('global_rules')}
                      className={`px-3 py-1 rounded-md transition ${
                        inspectorTab === 'global_rules'
                          ? 'bg-primary text-slate-950 font-bold'
                          : 'text-text-muted hover:text-text-main'
                      }`}
                    >
                      Global Rules ({inspectedContent?.global_rules?.instructions?.length || 0})
                    </button>
                    <button
                      onClick={() => setInspectorTab('icons')}
                      className={`px-3 py-1 rounded-md transition ${
                        inspectorTab === 'icons'
                          ? 'bg-primary text-slate-950 font-bold'
                          : 'text-text-muted hover:text-text-main'
                      }`}
                    >
                      Icons ({inspectedContent?.total_icons || 0})
                    </button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={() => {
                        if (inspectTemplateId) {
                          navigate(`/templates/${inspectTemplateId}`);
                          setInspectTemplateId(null);
                        }
                      }}
                      leftIcon={<ExternalLink className="size-3.5 text-primary" />}
                      title="Open full page reading view"
                    >
                      Full View
                    </Button>
                  </div>
                  <button
                    onClick={() => setInspectTemplateId(null)}
                    className="text-text-muted hover:text-text-main p-1.5 rounded-lg hover:bg-surface transition"
                  >
                    <X className="size-5" />
                  </button>
                </div>
              </div>

              {/* Modal Body */}
              <div className="flex-1 overflow-y-auto p-6 bg-app space-y-4">
                {isLoadingContent ? (
                  <div className="py-20 flex flex-col items-center justify-center text-text-muted">
                    <RefreshCw className="size-8 animate-spin text-primary mb-3" />
                    <span className="text-xs font-medium">Loading extracted template content...</span>
                  </div>
                ) : !inspectedContent ? (
                  <div className="py-20 text-center text-text-muted">
                    <AlertCircle className="size-10 mx-auto mb-2 text-amber-400" />
                    <span className="text-sm font-semibold text-text-main">
                      No extracted content available
                    </span>
                    <p className="text-xs mt-1">Please run extraction on this template first.</p>
                  </div>
                ) : inspectorTab === 'global_rules' ? (
                  /* Global Rules View */
                  <div className="space-y-4">
                    <div className="rounded-xl border border-sky-500/30 bg-sky-500/10 p-4">
                      <div className="flex items-center gap-2 text-sky-300 font-semibold text-xs">
                        <Sparkles className="size-4 text-sky-400" />
                        Document-Wide Global Rules
                      </div>
                      <p className="text-[11px] text-text-muted mt-1 leading-relaxed">
                        These instructions were written in blue font before the first section heading.
                        They specify global formatting, document scope, or authoring rules that govern
                        the entire migrated SOP.
                      </p>
                    </div>

                    {inspectedContent.global_rules?.instructions?.length === 0 ? (
                      <div className="p-8 text-center text-xs text-text-muted bg-card rounded-xl border border-border">
                        No pre-section blue instructions detected.
                      </div>
                    ) : (
                      <div className="space-y-2.5">
                        {inspectedContent.global_rules.instructions.map((rule, idx) => (
                          <div
                            key={idx}
                            className="p-3.5 rounded-xl border border-sky-500/30 bg-sky-500/5 text-xs text-sky-200 leading-relaxed flex items-start gap-3"
                          >
                            <span className="size-5 shrink-0 rounded-full bg-sky-500/20 text-sky-300 font-mono text-[10px] grid place-items-center">
                              {idx + 1}
                            </span>
                            <div className="flex-1">
                              <p className="font-medium text-sky-100">{rule.text}</p>
                              {rule.font_color_hex && (
                                <div className="mt-1 text-[10px] text-sky-400/80 font-mono">
                                  Color Hex: #{rule.font_color_hex}
                                </div>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ) : inspectorTab === 'icons' ? (
                  /* Icons View */
                  <div className="space-y-4">
                    <div className="rounded-xl border border-purple-500/30 bg-purple-500/10 p-4">
                      <div className="flex items-center gap-2 text-purple-300 font-semibold text-xs">
                        <Tag className="size-4 text-purple-400" />
                        Template Extracted Icons
                      </div>
                      <p className="text-[11px] text-text-muted mt-1 leading-relaxed">
                        Visual warning, notice, PPE, or guideline icons extracted from the template.
                        Icons are automatically bound to their neighboring section text.
                      </p>
                    </div>

                    {inspectedContent.total_icons === 0 ? (
                      <div className="p-8 text-center text-xs text-text-muted bg-card rounded-xl border border-border">
                        No embedded icons extracted in this template.
                      </div>
                    ) : (
                      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
                        {inspectedContent.sections.flatMap((sec) =>
                          sec.elements.flatMap((el) =>
                            (el.icons || []).map((icon, iconIdx) => (
                              <div
                                key={`${sec.title}-${icon.icon_id}-${iconIdx}`}
                                className="dashboard-card p-3 border border-border bg-card flex flex-col items-center text-center space-y-2"
                              >
                                <div className="size-12 rounded-lg bg-surface border border-border grid place-items-center p-1">
                                  <img
                                    src={
                                      icon.image_path.startsWith('/templates/')
                                        ? icon.image_path
                                        : api.getTemplateAssetUrl(
                                            inspectedContent.template_id,
                                            api.assetFileName(icon.image_path)
                                          )
                                    }
                                    alt={icon.semantic_meaning || 'Icon'}
                                    className="max-h-full max-w-full object-contain"
                                    onError={(e) => {
                                      // Fallback icon visual
                                      e.currentTarget.style.display = 'none';
                                    }}
                                  />
                                </div>
                                <div className="min-w-0 w-full">
                                  <div className="text-[11px] font-semibold text-text-main capitalize truncate">
                                    {icon.semantic_meaning || 'Icon'}
                                  </div>
                                  <div className="text-[9px] text-text-muted font-mono truncate mt-0.5">
                                    Section: {icon.section_context || sec.title}
                                  </div>
                                  {icon.associated_text && (
                                    <div
                                      className="text-[9px] text-sky-300/80 line-clamp-2 mt-1 italic text-left bg-surface/50 p-1 rounded border border-border/40"
                                      title={icon.associated_text}
                                    >
                                      "{icon.associated_text}"
                                    </div>
                                  )}
                                </div>
                              </div>
                            ))
                          )
                        )}
                      </div>
                    )}
                  </div>
                ) : (
                  /* Section-Wise View */
                  <div className="space-y-3">
                    {inspectedContent.sections.map((section: TemplateSection, sIdx: number) => {
                      const isExpanded = !!expandedSections[sIdx];
                      const instructions = section.instructions || [];

                      return (
                        <div
                          key={sIdx}
                          className="rounded-xl border border-border bg-card overflow-hidden transition-all duration-200"
                        >
                          <button
                            onClick={() => toggleSectionExpand(sIdx)}
                            className="w-full p-4 flex items-center justify-between text-left hover:bg-surface/50 transition-colors"
                          >
                            <div className="flex items-center gap-2.5">
                              {isExpanded ? (
                                <ChevronDown className="size-4 text-primary" />
                              ) : (
                                <ChevronRight className="size-4 text-text-muted" />
                              )}
                              <span className="font-medium text-text-main text-sm">
                                {section.title}
                              </span>
                              {section.section_number && (
                                <span className="rounded bg-surface px-1.5 py-0.5 text-[10px] font-mono text-text-muted border border-border">
                                  Sec {section.section_number}
                                </span>
                              )}
                            </div>

                            <div className="flex items-center gap-3 text-[10px] font-mono">
                              {instructions.length > 0 && (
                                <span className="rounded bg-sky-500/10 text-sky-400 px-2 py-0.5 border border-sky-500/20">
                                  {instructions.length} instruction{instructions.length === 1 ? '' : 's'}
                                </span>
                              )}
                              <span className="text-text-muted">
                                {section.elements.length} element{section.elements.length === 1 ? '' : 's'}
                              </span>
                            </div>
                          </button>

                          {isExpanded && (
                            <div className="p-4 space-y-3 bg-card/40">
                              {/* Section Blue Instructions Callout */}
                              {instructions.length > 0 && (
                                <div className="rounded-lg border border-sky-500/30 bg-sky-500/10 p-3 space-y-2">
                                  <div className="text-[11px] font-semibold text-sky-300 flex items-center gap-1.5">
                                    <Sparkles className="size-3.5 text-sky-400" /> Section Instructions (Blue Font)
                                  </div>
                                  <div className="space-y-1.5">
                                    {instructions.map((inst, iIdx) => (
                                      <div
                                        key={iIdx}
                                        className="text-xs text-sky-200 pl-3 border-l-2 border-sky-400/60 leading-relaxed font-sans flex flex-col gap-1.5"
                                      >
                                        <div className="flex items-start gap-2">
                                          {inst.icons && inst.icons.length > 0 && (
                                            <div className="flex items-center gap-1.5 shrink-0 mt-0.5">
                                              {inst.icons.map((ic, icIdx) => (
                                                <span
                                                  key={icIdx}
                                                  className="inline-flex items-center gap-1 rounded bg-purple-500/20 text-purple-300 px-1.5 py-0.5 text-[10px] border border-purple-500/30"
                                                  title={`Icon: ${ic.semantic_meaning || 'Icon'}`}
                                                >
                                                  <Tag className="size-2.5 text-purple-400" />
                                                  {ic.semantic_meaning || 'Icon'}
                                                </span>
                                              ))}
                                            </div>
                                          )}
                                          <span>{inst.text}</span>
                                        </div>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Section Elements with full tables, images, and cell icons */}
                              <div className="space-y-3 pt-1">
                                {section.elements.map((el: TemplateElement, eIdx: number) => (
                                  <ElementRenderer
                                    key={eIdx}
                                    element={el}
                                    documentId={inspectedContent.template_id}
                                    isTemplate={true}
                                    index={eIdx}
                                  />
                                ))}
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Confirm Delete Dialog */}
      <ConfirmDialog
        isOpen={!!templateToDelete}
        title="Delete Template Record"
        message={`Are you sure you want to delete '${templateToDelete?.template_name}'? This will permanently remove its uploaded document and extracted JSON data.`}
        confirmLabel="Delete Template"
        isDangerous={true}
        isLoading={isDeleting}
        onConfirm={handleDeleteConfirm}
        onCancel={() => setTemplateToDelete(null)}
      />
    </div>
  );
};
