import React, { useState } from 'react';
import { DocxMigrationOutput, MigrationElement, MigrationSection, AISuggestion, Issue } from '@/types';
import { OriginalDocumentViewer } from './OriginalDocumentViewer';
import { ContentEditor } from './ContentEditor';
import { AISuggestionPanel } from '@/components/ai/AISuggestionPanel';
import { CompareView } from './CompareView';
import { SectionNav } from '@/components/content/SectionNav';
import { IssuePanel } from './IssuePanel';
import { Layers, AlertTriangle } from 'lucide-react';

interface ExtractionReviewModeProps {
  documentUid: string;
  fileType?: string;
  v2Content: DocxMigrationOutput | null;
  suggestions: AISuggestion[];
  issues: Issue[];
  onAcceptSuggestion: (sug: AISuggestion) => void;
  onRejectSuggestion: (sug: AISuggestion) => void;
  onCreateIssue: (iss: Partial<Issue>) => void;
  onResolveIssue: (id: string) => void;
  onGenerateSuggestion: (prompt: string) => void;
}

export const ExtractionReviewMode: React.FC<ExtractionReviewModeProps> = ({
  documentUid,
  fileType = 'pdf',
  v2Content,
  suggestions,
  issues,
  onAcceptSuggestion,
  onRejectSuggestion,
  onCreateIssue,
  onResolveIssue,
  onGenerateSuggestion,
}) => {
  const [activeSectionIdx, setActiveSectionIdx] = useState(0);
  const [selectedElement, setSelectedElement] = useState<MigrationElement | null>(null);
  const [highlightBbox, setHighlightBbox] = useState<number[] | null>(null);
  const [rightTab, setRightTab] = useState<'ai' | 'issues' | 'compare'>('ai');

  const sections = v2Content?.sections || [];
  const currentSection = sections[activeSectionIdx] || sections[0];

  const handleSelectElement = (el: MigrationElement) => {
    setSelectedElement(el);
    if (el.raw_bbox) {
      setHighlightBbox(el.raw_bbox);
    }
  };

  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-4 h-[calc(100vh-145px)] overflow-hidden p-4">
      {/* Column 1: Original SOP Document Viewer (4 cols ~ 34%) */}
      <div className="xl:col-span-4 h-full overflow-hidden">
        <OriginalDocumentViewer
          documentId={documentUid}
          fileType={fileType}
          currentPage={selectedElement?.page || 1}
          highlightBbox={highlightBbox}
        />
      </div>

      {/* Column 2: Extracted Content & Section Editor (5 cols ~ 42%) */}
      <div className="xl:col-span-5 flex flex-col h-full overflow-hidden space-y-3">
        {/* Section Pill bar */}
        <div className="dashboard-card p-2 overflow-x-auto flex items-center gap-1.5 shrink-0">
          {sections.map((sec, idx) => (
            <button
              key={idx}
              type="button"
              onClick={() => {
                setActiveSectionIdx(idx);
                if (sec.elements?.[0]) setSelectedElement(sec.elements[0]);
              }}
              className={`px-2.5 py-1 text-xs rounded font-medium whitespace-nowrap transition ${
                idx === activeSectionIdx
                  ? 'bg-primary/20 text-primary border border-primary/30'
                  : 'text-text-muted hover:bg-white/5'
              }`}
            >
              §{sec.section_number} {sec.title || `Section ${idx}`}
            </button>
          ))}
        </div>

        {/* Selected Element Editor / Section Content List */}
        <div className="flex-1 overflow-hidden">
          <ContentEditor
            element={selectedElement || (currentSection?.elements?.[0] ?? null)}
            onSave={(text) => {
              if (selectedElement) {
                selectedElement.text = text;
              }
            }}
          />
        </div>
      </div>

      {/* Column 3: AI Suggestions, Warnings & Issue Tracking (3 cols ~ 24%) */}
      <div className="xl:col-span-3 flex flex-col h-full overflow-hidden">
        {/* Tab switch */}
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
            onClick={() => setRightTab('issues')}
            className={`flex-1 py-1 rounded font-medium transition ${
              rightTab === 'issues' ? 'bg-primary/20 text-primary' : 'text-text-muted'
            }`}
          >
            Issues ({issues.length})
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
            <IssuePanel
              issues={issues}
              onCreateIssue={onCreateIssue}
              onResolveIssue={onResolveIssue}
            />
          )}
        </div>
      </div>
    </div>
  );
};
