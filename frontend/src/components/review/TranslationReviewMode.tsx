import React, { useState } from 'react';
import { DocxMigrationOutput, AISuggestion, Issue } from '@/types';
import { SectionNav } from '@/components/content/SectionNav';
import { GlossaryPanel } from './GlossaryPanel';
import { TranslationQaPanel } from './TranslationQaPanel';
import { AISuggestionPanel } from '@/components/ai/AISuggestionPanel';
import { Languages, Sparkles, BookOpen, ShieldCheck, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/Button';

interface TranslationReviewModeProps {
  documentUid: string;
  v2Content: DocxMigrationOutput | null;
  targetLocale?: string;
  suggestions: AISuggestion[];
  onAcceptSuggestion: (sug: AISuggestion) => void;
  onRejectSuggestion: (sug: AISuggestion) => void;
  onGenerateSuggestion: (prompt: string) => void;
}

export const TranslationReviewMode: React.FC<TranslationReviewModeProps> = ({
  documentUid,
  v2Content,
  targetLocale = 'fr',
  suggestions,
  onAcceptSuggestion,
  onRejectSuggestion,
  onGenerateSuggestion,
}) => {
  const [activeSectionIdx, setActiveSectionIdx] = useState(0);
  const [rightTab, setRightTab] = useState<'ai' | 'glossary' | 'qa'>('ai');

  const sections = v2Content?.sections || [];
  const currentSection = sections[activeSectionIdx] || sections[0];

  // Dummy translations for display
  const sourceText = currentSection?.elements?.map((e) => e.text).filter(Boolean).join('\n\n') || 'No section text.';
  const [targetText, setTargetText] = useState(
    `[TRADUCTION FRANCुAISE] : ${currentSection?.title || 'Section'}\n\nCette section a été traduite avec préservation de la terminologie GxP et des identifiants d'origine.`
  );

  React.useEffect(() => {
    setTargetText(
      `[TRADUCTION FRANCुAISE] : ${currentSection?.title || 'Section'}\n\nCette section a été traduite avec préservation de la terminologie GxP et des identifiants d'origine.`
    );
  }, [currentSection]);

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

      {/* Column 2: Source vs. Translated Content (6 cols ~ 54%) */}
      <div className="xl:col-span-6 flex flex-col h-full overflow-hidden space-y-3">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 flex-1 overflow-hidden">
          {/* Source Language Pane (English) */}
          <div className="dashboard-card flex flex-col h-full overflow-hidden">
            <div className="flex items-center justify-between border-b border-border bg-card/60 px-4 py-2.5 text-xs font-semibold">
              <span className="text-text-main flex items-center gap-1.5">
                <Languages className="size-3.5 text-sky-400" /> Source (English)
              </span>
              <span className="text-[10px] text-text-muted">Read-only</span>
            </div>
            <div className="flex-1 p-4 overflow-y-auto font-sans text-xs leading-relaxed text-text-muted whitespace-pre-wrap">
              {sourceText}
            </div>
          </div>

          {/* Target Language Pane (French / Translated) */}
          <div className="dashboard-card flex flex-col h-full overflow-hidden">
            <div className="flex items-center justify-between border-b border-border bg-card/60 px-4 py-2.5 text-xs font-semibold">
              <span className="text-primary flex items-center gap-1.5">
                <Languages className="size-3.5" /> Target ({targetLocale.toUpperCase()})
              </span>
              <span className="rounded bg-primary/10 text-primary px-1.5 py-0.2 text-[10px]">
                Editable Draft
              </span>
            </div>
            <textarea
              value={targetText}
              onChange={(e) => setTargetText(e.target.value)}
              className="flex-1 p-4 resize-none bg-transparent font-sans text-xs leading-relaxed text-text-main focus:outline-none"
              placeholder="Translated content..."
            />
          </div>
        </div>
      </div>

      {/* Column 3: AI, Glossary & QA Tools (3 cols ~ 25%) */}
      <div className="xl:col-span-3 flex flex-col h-full overflow-hidden">
        {/* Sub-tabs */}
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
            onClick={() => setRightTab('glossary')}
            className={`flex-1 py-1 rounded font-medium transition ${
              rightTab === 'glossary' ? 'bg-primary/20 text-primary' : 'text-text-muted'
            }`}
          >
            Glossary
          </button>
          <button
            type="button"
            onClick={() => setRightTab('qa')}
            className={`flex-1 py-1 rounded font-medium transition ${
              rightTab === 'qa' ? 'bg-primary/20 text-primary' : 'text-text-muted'
            }`}
          >
            QA Checks
          </button>
        </div>

        <div className="flex-1 overflow-hidden">
          {rightTab === 'ai' && (
            <AISuggestionPanel
              suggestions={suggestions}
              onAccept={onAcceptSuggestion}
              onReject={onRejectSuggestion}
              onGenerateSuggestion={onGenerateSuggestion}
            />
          )}
          {rightTab === 'glossary' && <GlossaryPanel />}
          {rightTab === 'qa' && <TranslationQaPanel />}
        </div>
      </div>
    </div>
  );
};
