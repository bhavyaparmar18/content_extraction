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
} from 'lucide-react';
import { DocxMigrationOutput, AISuggestion, MigrationPlan } from '@/types';
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
  onTriggerMigration?: () => void;
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
  const fileInputRef = useRef<HTMLInputElement>(null);

  const sections = v2Content?.sections || [];
  const currentSection = sections[activeSectionIdx] || sections[0];

  // Fetch LLM-generated Migration Plan if it has already run
  const { data: migrationPlan, isLoading: isLoadingPlan } = useQuery<MigrationPlan | null>({
    queryKey: ['migrationPlan', documentUid],
    queryFn: () => (documentUid ? api.getMigrationPlan(documentUid) : null),
    enabled: !!documentUid,
    retry: false,
  });

  // Find matching SectionPlan for the currently active section
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

    return `[TARGET TEMPLATE FORMAT]\n\n${currentSection?.title || 'Section'}\n\n${sourceText}`;
  }, [matchingSectionPlan, currentSection, sourceText]);

  const [migratedText, setMigratedText] = useState(initialMigratedText);

  useEffect(() => {
    setMigratedText(initialMigratedText);
  }, [initialMigratedText]);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && onSelectTemplateFile) {
      onSelectTemplateFile(file);
    }
  };

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 h-[calc(100vh-145px)] overflow-hidden p-4">
      {/* Column 1: Section Navigation (3 cols ~ 21%) */}
      <div className="xl:col-span-3 h-full overflow-hidden flex flex-col space-y-3">
        {/* Template Selector Card */}
        <div className="dashboard-card p-3 space-y-2 border border-border bg-card/80">
          <div className="flex items-center justify-between text-xs font-semibold text-text-main">
            <span className="flex items-center gap-1.5">
              <FileCode className="size-3.5 text-primary" /> Template Engine
            </span>
            {customTemplateFile ? (
              <span className="rounded bg-primary/20 text-primary px-1.5 py-0.5 text-[10px] font-mono">
                Custom
              </span>
            ) : (
              <span className="rounded bg-white/10 text-text-muted px-1.5 py-0.5 text-[10px] font-mono">
                Default
              </span>
            )}
          </div>

          <div className="text-[11px] text-text-muted leading-tight">
            {customTemplateFile
              ? customTemplateFile.name
              : 'Default GP-DAT Corporate .docx Template'}
          </div>

          <div className="flex items-center gap-2 pt-1">
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
              {customTemplateFile ? 'Change .docx' : 'Upload Custom .docx'}
            </Button>
            {customTemplateFile && onSelectTemplateFile && (
              <Button
                variant="icon"
                size="sm"
                onClick={() => onSelectTemplateFile(null)}
                title="Revert to default template"
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

      {/* Column 2: Current vs. Migrated Format Side-by-Side (6 cols ~ 54%) */}
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

          {/* New Corporate Template Structure */}
          <div className="dashboard-card flex flex-col h-full overflow-hidden">
            <div className="flex items-center justify-between border-b border-border bg-card/60 px-4 py-2.5 text-xs font-semibold">
              <span className="text-primary flex items-center gap-1.5">
                <ArrowRightLeft className="size-3.5" />
                {matchingSectionPlan ? matchingSectionPlan.template_section_heading : 'Target Template'}
              </span>
              {matchingSectionPlan ? (
                <span className="rounded bg-emerald-500/15 text-emerald-400 px-1.5 py-0.5 text-[10px] font-mono flex items-center gap-1">
                  <CheckCircle2 className="size-2.5" /> {matchingSectionPlan.elements.length} mapped
                </span>
              ) : (
                <span className="rounded bg-primary/10 text-primary px-1.5 py-0.5 text-[10px]">
                  Editable Output
                </span>
              )}
            </div>
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
              onTriggerMigration={onTriggerMigration}
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
