import React, { useState } from 'react';
import { MigrationElement } from '@/types';
import { SaveStatus } from '@/lib/useAutosave';
import { CheckCircle2, RefreshCw, AlertTriangle, Edit3, Type, List, Table } from 'lucide-react';
import { clsx } from 'clsx';

interface ContentEditorProps {
  element: MigrationElement | null;
  saveStatus?: SaveStatus;
  onSave?: (updatedText: string) => void;
  onSelectEntity?: (element: MigrationElement) => void;
}

export const ContentEditor: React.FC<ContentEditorProps> = ({
  element,
  saveStatus = 'saved',
  onSave,
  onSelectEntity,
}) => {
  const [editText, setEditText] = useState(element?.text || '');

  React.useEffect(() => {
    setEditText(element?.text || '');
  }, [element]);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    setEditText(val);
    onSave?.(val);
  };

  if (!element) {
    return (
      <div className="dashboard-card flex flex-col items-center justify-center p-8 text-center text-text-muted h-full min-h-[350px]">
        <Edit3 className="size-8 opacity-40 mb-2" />
        <div className="text-sm font-semibold">Select an entity to review and edit</div>
        <div className="text-xs text-text-muted mt-1">Click any section or element on the left</div>
      </div>
    );
  }

  return (
    <div className="dashboard-card flex flex-col h-full overflow-hidden">
      {/* Editor Header */}
      <div className="flex items-center justify-between border-b border-border bg-card/60 px-4 py-2.5 text-xs">
        <div className="flex items-center gap-2 font-medium text-text-main">
          {element.element_type === 'heading' && <Type className="size-3.5 text-primary" />}
          {element.element_type === 'paragraph' && <Edit3 className="size-3.5 text-sky-400" />}
          {element.element_type === 'list' && <List className="size-3.5 text-amber-400" />}
          {element.element_type === 'table' && <Table className="size-3.5 text-emerald-400" />}
          <span className="capitalize font-semibold">{element.element_type} Editor</span>
          {element.page && (
            <span className="rounded bg-white/5 border border-border px-1.5 py-0.2 text-[10px] text-text-muted">
              Page {element.page}
            </span>
          )}
        </div>

        {/* Autosave Status Indicator */}
        <div className="flex items-center gap-1.5 text-[11px]">
          {saveStatus === 'saving' && (
            <span className="flex items-center gap-1 text-sky-400">
              <RefreshCw className="size-3 animate-spin" /> Saving...
            </span>
          )}
          {saveStatus === 'saved' && (
            <span className="flex items-center gap-1 text-emerald-400">
              <CheckCircle2 className="size-3" /> Saved (800ms)
            </span>
          )}
          {saveStatus === 'unsaved' && (
            <span className="flex items-center gap-1 text-amber-400">
              <AlertTriangle className="size-3" /> Unsaved
            </span>
          )}
          {saveStatus === 'conflict' && (
            <span className="flex items-center gap-1 text-red-400 font-semibold">
              <AlertTriangle className="size-3" /> Version Conflict (409)
            </span>
          )}
        </div>
      </div>

      {/* Editor Body */}
      <div className="flex-1 p-4 overflow-y-auto space-y-4">
        <div>
          <label className="field-label">Content Text</label>
          <textarea
            value={editText}
            onChange={handleChange}
            rows={10}
            className="field min-h-[220px] resize-y font-sans leading-relaxed text-sm p-3 bg-black/20"
            placeholder="Edit extracted structured text..."
          />
        </div>

        {/* Metadata info */}
        {element.section_name && (
          <div className="rounded border border-border bg-black/10 p-3 text-xs space-y-1">
            <div className="text-text-muted">Parent Section: <strong className="text-text-main">{element.section_name}</strong></div>
            {element.level && <div className="text-text-muted">Heading Level: <strong className="text-text-main">H{element.level}</strong></div>}
          </div>
        )}
      </div>
    </div>
  );
};
