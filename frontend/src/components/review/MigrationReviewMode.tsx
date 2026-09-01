import React, { useState } from 'react';
import { DocxMigrationOutput, AISuggestion } from '@/types';
import { SectionNav } from '@/components/content/SectionNav';
import { MigrationValidationPanel } from './MigrationValidationPanel';
import { AISuggestionPanel } from '@/components/ai/AISuggestionPanel';
import { ArrowRightLeft, Sparkles, Layers, FileText } from 'lucide-react';

interface MigrationReviewModeProps {
  documentUid: string;
  v2Content: DocxMigrationOutput | null;
  suggestions: AISuggestion[];
  onAcceptSuggestion: (sug: AISuggestion) => void;
  onRejectSuggestion: (sug: AISuggestion) => void;
  onGenerateSuggestion: (prompt: string) => void;
}

export const MigrationReviewMode: React.FC<MigrationReviewModeProps> = ({
  documentUid,
  v2Content,
  suggestions,
  onAcceptSuggestion,
  onRejectSuggestion,
  onGenerateSuggestion,
}) => {
  const [activeSectionIdx, setActiveSectionIdx] = useState(0);
  const [rightTab, setRightTab] = useState<'ai' | 'validation'>('ai');

  const sections = v2Content?.sections || [];
  const currentSection = sections[activeSectionIdx] || sections[0];

  const sourceText = currentSection?.elements?.map((e) => e.text).filter(Boolean).join('\n\n') || 'Source content';
  const [migratedText, setMigratedText] = useState(
    `[MIGRATED FORMAT - TEMPLATE v2.1]\n\n${currentSection?.title || 'Section'}\n\n${sourceText}`
  );

  React.useEffect(() => {
    setMigratedText(
      `[MIGRATED FORMAT - TEMPLATE v2.1]\n\n${currentSection?.title || 'Section'}\n\n${sourceText}`
    );
  }, [currentSection, sourceText]);

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 h-[calc(100vh-145px)] overflow-hidden p-4">
      {/* Column 1: Section Navigation (3 cols ~ 21%) */}
      <div className="xl:col-span-3 h-full overflow-hidden">
        <SectionNav
          sections={sections}
          activeSectionIdx={activeSectionIdx}
          onSelectSection={setActiveSectionIdx}
        />
      </div>

      {/* Column 2: Current vs. Migrated Format Side-by-Side (6 cols ~ 54%) */}
      <div className="xl:col-span-6 flex flex-col h-full overflow-hidden space-y-3">
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
                <ArrowRightLeft className="size-3.5" /> Target Template (v2.1)
              </span>
              <span className="rounded bg-primary/10 text-primary px-1.5 py-0.2 text-[10px]">
                Editable Output
              </span>
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
            onClick={() => setRightTab('ai')}
            className={`flex-1 py-1 rounded font-medium transition ${
              rightTab === 'ai' ? 'bg-primary/20 text-primary' : 'text-text-muted'
            }`}
          >
            AI Suggestions
          </button>
          <button
            type="button"
            onClick={() => setRightTab('validation')}
            className={`flex-1 py-1 rounded font-medium transition ${
              rightTab === 'validation' ? 'bg-primary/20 text-primary' : 'text-text-muted'
            }`}
          >
            Template Validation
          </button>
        </div>

        <div className="flex-1 overflow-hidden">
          {rightTab === 'ai' ? (
            <AISuggestionPanel
              suggestions={suggestions}
              onAccept={onAcceptSuggestion}
              onReject={onRejectSuggestion}
              onGenerateSuggestion={onGenerateSuggestion}
            />
          ) : (
            <MigrationValidationPanel documentId={documentUid} />
          )}
        </div>
      </div>
    </div>
  );
};
