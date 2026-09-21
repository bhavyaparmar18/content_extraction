import React, { useState, useMemo, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowRightLeft,
  Sparkles,
  Layers,
  FileText,
  Upload,
  CheckCircle2,
  RefreshCw,
  FileCode,
  X,
  Info,
  Tag,
  ChevronDown,
} from 'lucide-react';
import {
  DocxMigrationOutput,
  AISuggestion,
  MigrationPlan,
  TemplateRecord,
  TemplateExtractionOutput,
  TemplateSection,
} from '@/types';
import { api } from '@/lib/api';
import { SectionNav } from '@/components/content/SectionNav';
import { MigrationValidationPanel } from './MigrationValidationPanel';
import { AISuggestionPanel } from '@/components/ai/AISuggestionPanel';
import { Button } from '@/components/ui/Button';

interface MigrationReviewModeProps {
  documentUid: string;
  v2Content: DocxMigrationOutput | null;
  suggestions: AISuggestion[];
  onAcceptSuggestion: (sug: AISuggestion) => void;
  onRejectSuggestion: (sug: AISuggestion) => void;
  onGenerateSuggestion: (prompt: string) => void;
  customTemplateFile?: File | null;
  onSelectTemplateFile?: (file: File | null) => void;
  isMigrating?: boolean;
  onTriggerMigration?: (templateId?: string) => void;
}

export const MigrationReviewMode: React.FC<MigrationReviewModeProps> = ({
  documentUid,
  v2Content,
  suggestions,
  onAcceptSuggestion,
  onRejectSuggestion,
  onGenerateSuggestion,
  customTemplateFile,
  onSelectTemplateFile,
  isMigrating = false,
  onTriggerMigration,
}) => {
  const [activeSectionIdx, setActiveSectionIdx] = useState(0);
  const [rightTab, setRightTab] = useState<'validation' | 'ai'>('validation');
  const [selectedTemplateUid, setSelectedTemplateUid] = useState<string>('');
  const [showGlobalRules, setShowGlobalRules] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const sections = v2Content?.sections || [];
  const currentSection = sections[activeSectionIdx] || sections[0];

  // 1. Fetch all registered ready templates for the dropdown
  const { data: readyTemplates = [] } = useQuery<TemplateRecord[]>({
    queryKey: ['readyTemplates'],
    queryFn: () => api.getTemplates('ready'),
    staleTime: 10000,
  });

  // Auto-select first template if none selected and templates exist
  useEffect(() => {
    if (!selectedTemplateUid && readyTemplates.length > 0) {
      setSelectedTemplateUid(readyTemplates[0].template_uid);
    }
  }, [readyTemplates, selectedTemplateUid]);

  // 2. Fetch selected template's extracted content
  const { data: targetTemplateContent } = useQuery<TemplateExtractionOutput | null>({
    queryKey: ['targetTemplateContent', selectedTemplateUid],
    queryFn: () => (selectedTemplateUid ? api.getTemplateContent(selectedTemplateUid) : null),
    enabled: !!selectedTemplateUid,
  });

  // 3. Fetch LLM-generated Migration Plan if available
  const { data: migrationPlan } = useQuery<MigrationPlan | null>({
    queryKey: ['migrationPlan', documentUid],
    queryFn: () => (documentUid ? api.getMigrationPlan(documentUid) : null),
    enabled: !!documentUid,
    retry: false,
  });

  // Find matching SectionPlan for the currently active source section
  const matchingSectionPlan = useMemo(() => {
    if (!migrationPlan?.section_plans || !currentSection) return null;
    return (
      migrationPlan.section_plans.find(
        (sp) =>
          sp.source_sections_mapped.includes(currentSection.title) ||
          sp.template_section_heading.toLowerCase().includes(currentSection.title.toLowerCase()) ||
          currentSection.title.toLowerCase().includes(sp.template_section_heading.toLowerCase())
      ) || null
    );
  }, [migrationPlan, currentSection]);

  // Find matching section in the selected target template
  const matchingTemplateSection = useMemo<TemplateSection | null>(() => {
    if (!targetTemplateContent?.sections || !currentSection) return null;
    const curTitleLower = currentSection.title.toLowerCase();
    const curNum = currentSection.section_number;

    // Exact number or title match first
    return (
      targetTemplateContent.sections.find((ts) => {
        if (curNum && ts.section_number && curNum === ts.section_number) return true;
        const tTitleLower = ts.title.toLowerCase();
        return tTitleLower.includes(curTitleLower) || curTitleLower.includes(tTitleLower);
      }) ||
      targetTemplateContent.sections[activeSectionIdx] ||
      null
    );
  }, [targetTemplateContent, currentSection, activeSectionIdx]);

  const sourceText =
    currentSection?.elements?.map((e) => e.text).filter(Boolean).join('\n\n') || 'Source content';

  // Compute preview of migrated text
  const initialMigratedText = useMemo(() => {
    if (matchingSectionPlan) {
      const heading = matchingSectionPlan.template_section_heading;
      const elementsSummary =
        matchingSectionPlan.elements.length > 0
          ? matchingSectionPlan.elements
              .map(
                (el, i) =>
                  `[Element ${i + 1} (${el.source_element_type}) -> ${el.action}]\n${
                    currentSection?.elements?.[el.source_element_index]?.text || ''
                  }`
              )
              .join('\n\n')
          : sourceText;

      return `[TARGET TEMPLATE: ${heading}]\n\n${elementsSummary}`;
    }

    if (matchingTemplateSection) {
      return `[TARGET TEMPLATE: ${matchingTemplateSection.title}]\n\n${sourceText}`;
    }

    return `[TARGET TEMPLATE FORMAT]\n\n${currentSection?.title || 'Section'}\n\n${sourceText}`;
  }, [matchingSectionPlan, matchingTemplateSection, currentSection, sourceText]);

  const [migratedText, setMigratedText] = useState(initialMigratedText);

  useEffect(() => {
    setMigratedText(initialMigratedText);
  }, [initialMigratedText]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && onSelectTemplateFile) {
      onSelectTemplateFile(file);
      setSelectedTemplateUid('');
    }
  };

  const selectedTemplateRecord = useMemo(() => {
    return readyTemplates.find((t) => t.template_uid === selectedTemplateUid);
  }, [readyTemplates, selectedTemplateUid]);

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 h-[calc(100vh-145px)] overflow-hidden p-4">
      {/* Column 1: Section Navigation & Template Selector (3 cols ~ 25%) */}
      <div className="xl:col-span-3 h-full overflow-hidden flex flex-col space-y-3">
        {/* Template Selector Card */}
        <div className="dashboard-card p-3 space-y-2.5 border border-border bg-card/80">
          <div className="flex items-center justify-between text-xs font-semibold text-text-main">
            <span className="flex items-center gap-1.5">
              <FileCode className="size-3.5 text-primary" /> Target Template
            </span>
            {customTemplateFile ? (
              <span className="rounded bg-primary/20 text-primary px-1.5 py-0.5 text-[10px] font-mono">
                Custom Upload
              </span>
            ) : selectedTemplateRecord ? (
              <span className="rounded bg-emerald-500/20 text-emerald-400 px-1.5 py-0.5 text-[10px] font-mono">
                v{selectedTemplateRecord.template_version}
              </span>
            ) : (
              <span className="rounded bg-white/10 text-text-muted px-1.5 py-0.5 text-[10px] font-mono">
                Default
              </span>
            )}
          </div>

          {/* Registered Template Dropdown */}
          <div>
            <label className="block text-[10px] font-semibold text-text-muted uppercase tracking-wider mb-1">
              Select Registered Template
            </label>
            <div className="relative">
              <select
                value={customTemplateFile ? '' : selectedTemplateUid}
                onChange={(e) => {
                  setSelectedTemplateUid(e.target.value);
                  if (onSelectTemplateFile) {
                    onSelectTemplateFile(null);
                  }
                }}
                className="w-full appearance-none rounded-lg border border-border bg-surface px-3 py-2 pr-8 text-xs text-text-main font-medium focus:border-primary focus:outline-none transition"
              >
                {readyTemplates.length === 0 ? (
                  <option value="">No registered templates (using default)</option>
                ) : (
                  readyTemplates.map((tpl) => (
                    <option key={tpl.id} value={tpl.template_uid}>
                      {tpl.template_name} (v{tpl.template_version})
                    </option>
                  ))
                )}
              </select>
              <ChevronDown className="pointer-events-none absolute right-2.5 top-2.5 size-3.5 text-text-muted" />
            </div>
          </div>

          {/* Quick stats for selected template */}
          {selectedTemplateRecord && (
            <div className="text-[10px] text-text-muted flex items-center justify-between font-mono bg-surface/60 rounded-md p-1.5 border border-border/50">
              <span>Sec: {selectedTemplateRecord.total_sections}</span>
              <span>•</span>
              <span className="text-sky-400">Rules: {selectedTemplateRecord.total_instructions}</span>
              <span>•</span>
              <span className="text-purple-400">Icons: {selectedTemplateRecord.total_icons}</span>
            </div>
          )}

          {/* Ad-hoc file upload alternative */}
          <div className="flex items-center gap-2 pt-0.5">
            <input
              ref={fileInputRef}
              type="file"
              accept=".docx"
              onChange={handleFileChange}
              className="hidden"
            />
            <Button
              variant="secondary"
              size="sm"
              className="w-full text-xs"
              onClick={() => fileInputRef.current?.click()}
              leftIcon={<Upload className="size-3" />}
            >
              {customTemplateFile ? 'Change File' : 'Or Upload .docx'}
            </Button>
            {customTemplateFile && onSelectTemplateFile && (
              <Button
                variant="icon"
                size="sm"
                onClick={() => onSelectTemplateFile(null)}
                title="Revert to registered template"
              >
                <X className="size-3 text-red-400" />
              </Button>
            )}
          </div>
        </div>

        {/* Section Navigation */}
        <div className="flex-1 overflow-hidden">
          <SectionNav
            sections={sections}
            activeSectionIdx={activeSectionIdx}
            onSelectSection={setActiveSectionIdx}
          />
        </div>
      </div>

      {/* Column 2: Current vs. Migrated Format Side-by-Side (6 cols ~ 50%) */}
      <div className="xl:col-span-6 flex flex-col h-full overflow-hidden space-y-3">
        {isMigrating && (
          <div className="rounded-lg border border-primary/40 bg-primary/10 px-4 py-2.5 flex items-center justify-between text-xs text-primary animate-pulse">
            <span className="flex items-center gap-2 font-medium">
              <RefreshCw className="size-3.5 animate-spin text-primary" />
              AI Migration in Progress — Aligning sections with Corporate Template & generating DOCX...
            </span>
            <span className="text-[10px] font-mono">~15-20s</span>
          </div>
        )}

        {/* Global Rules Banner if present */}
        {targetTemplateContent?.global_rules?.instructions &&
          targetTemplateContent.global_rules.instructions.length > 0 && (
            <div className="rounded-lg border border-sky-500/30 bg-sky-500/10 p-2.5">
              <div className="flex items-center justify-between">
                <span className="text-[11px] font-semibold text-sky-300 flex items-center gap-1.5">
                  <Sparkles className="size-3.5 text-sky-400" />
                  Template Global Rules ({targetTemplateContent.global_rules.instructions.length} blue instructions)
                </span>
                <button
                  onClick={() => setShowGlobalRules(!showGlobalRules)}
                  className="text-[10px] text-sky-400 hover:text-sky-300 font-mono transition"
                >
                  {showGlobalRules ? 'Collapse ▲' : 'View ▼'}
                </button>
              </div>

              {showGlobalRules && (
                <div className="mt-2 space-y-1.5 pt-2 border-t border-sky-500/20 max-h-32 overflow-y-auto">
                  {targetTemplateContent.global_rules.instructions.map((inst, idx) => (
                    <div key={idx} className="text-xs text-sky-200 pl-2.5 border-l-2 border-sky-400/50">
                      {inst.text}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 flex-1 overflow-hidden">
          {/* Legacy / Current Extracted Format */}
          <div className="dashboard-card flex flex-col h-full overflow-hidden">
            <div className="flex items-center justify-between border-b border-border bg-card/60 px-4 py-2.5 text-xs font-semibold">
              <span className="text-text-main flex items-center gap-1.5">
                <FileText className="size-3.5 text-amber-400" /> Original Source Structure
              </span>
              <span className="text-[10px] text-text-muted">Legacy</span>
            </div>
            <div className="flex-1 p-4 overflow-y-auto font-sans text-xs leading-relaxed text-text-muted whitespace-pre-wrap">
              {sourceText}
            </div>
          </div>

          {/* Target Corporate Template Structure & Blue Instructions */}
          <div className="dashboard-card flex flex-col h-full overflow-hidden">
            <div className="flex items-center justify-between border-b border-border bg-card/60 px-4 py-2.5 text-xs font-semibold">
              <span className="text-primary flex items-center gap-1.5 truncate">
                <ArrowRightLeft className="size-3.5 shrink-0" />
                <span className="truncate">
                  {matchingTemplateSection?.title ||
                    (matchingSectionPlan ? matchingSectionPlan.template_section_heading : 'Target Template')}
                </span>
              </span>
              {matchingSectionPlan ? (
                <span className="rounded bg-emerald-500/15 text-emerald-400 px-1.5 py-0.5 text-[10px] font-mono flex items-center gap-1 shrink-0">
                  <CheckCircle2 className="size-2.5" /> {matchingSectionPlan.elements.length} mapped
                </span>
              ) : (
                <span className="rounded bg-primary/10 text-primary px-1.5 py-0.5 text-[10px] shrink-0">
                  Target Output
                </span>
              )}
            </div>

            {/* Target Template Section Instructions Callout */}
            {matchingTemplateSection?.instructions && matchingTemplateSection.instructions.length > 0 && (
              <div className="bg-sky-500/10 border-b border-sky-500/20 p-3 space-y-1 shrink-0 max-h-40 overflow-y-auto">
                <div className="text-[10px] font-bold uppercase tracking-wider text-sky-400 flex items-center gap-1">
                  <Sparkles className="size-3" /> Authoring Guidelines (Blue Font)
                </div>
                {matchingTemplateSection.instructions.map((inst, i) => (
                  <div key={i} className="text-xs text-sky-200 leading-snug pl-2 border-l border-sky-400/50">
                    {inst.text}
                  </div>
                ))}
              </div>
            )}

            {/* Target Template Icons for this section */}
            {matchingTemplateSection?.elements?.some((el) => el.icons && el.icons.length > 0) && (
              <div className="bg-purple-500/5 border-b border-purple-500/20 px-3 py-1.5 flex items-center gap-2 text-[10px] text-purple-300 shrink-0 overflow-x-auto">
                <Tag className="size-3 text-purple-400 shrink-0" />
                <span>Template Icons:</span>
                {matchingTemplateSection.elements.flatMap((el) =>
                  (el.icons || []).map((icon, idx) => (
                    <span
                      key={idx}
                      className="rounded bg-purple-500/10 px-1.5 py-0.5 font-mono text-purple-300 border border-purple-500/20"
                    >
                      {icon.semantic_meaning || 'icon'}
                    </span>
                  ))
                )}
              </div>
            )}

            <textarea
              value={migratedText}
              onChange={(e) => setMigratedText(e.target.value)}
              className="flex-1 p-4 resize-none bg-transparent font-sans text-xs leading-relaxed text-text-main focus:outline-none"
              placeholder="Migrated structured content..."
            />
          </div>
        </div>
      </div>

      {/* Column 3: AI Suggestions & Template Validation (3 cols ~ 25%) */}
      <div className="xl:col-span-3 flex flex-col h-full overflow-hidden">
        <div className="flex items-center rounded-lg border border-border bg-card/60 p-1 mb-2 text-xs">
          <button
            type="button"
            onClick={() => setRightTab('validation')}
            className={`flex-1 py-1 rounded font-medium transition ${
              rightTab === 'validation' ? 'bg-primary/20 text-primary' : 'text-text-muted'
            }`}
          >
            Template Validation
          </button>
          <button
            type="button"
            onClick={() => setRightTab('ai')}
            className={`flex-1 py-1 rounded font-medium transition ${
              rightTab === 'ai' ? 'bg-primary/20 text-primary' : 'text-text-muted'
            }`}
          >
            AI Suggestions
          </button>
        </div>

        <div className="flex-1 overflow-hidden">
          {rightTab === 'validation' ? (
            <MigrationValidationPanel
              documentId={documentUid}
              isMigrating={isMigrating}
              onTriggerMigration={() => onTriggerMigration?.(selectedTemplateUid || undefined)}
            />
          ) : (
            <AISuggestionPanel
              suggestions={suggestions}
              onAccept={onAcceptSuggestion}
              onReject={onRejectSuggestion}
              onGenerateSuggestion={onGenerateSuggestion}
            />
          )}
        </div>
      </div>
    </div>
  );
};
