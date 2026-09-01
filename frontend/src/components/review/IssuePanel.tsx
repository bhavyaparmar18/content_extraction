import React, { useState } from 'react';
import { AlertCircle, Plus, CheckCircle2, MessageSquare, Tag, X } from 'lucide-react';
import { Issue } from '@/types';
import { Button } from '@/components/ui/Button';
import { formatDate } from '@/lib/format';

interface IssuePanelProps {
  issues: Issue[];
  onCreateIssue: (issue: Partial<Issue>) => void;
  onResolveIssue?: (issueId: string) => void;
}

export const IssuePanel: React.FC<IssuePanelProps> = ({
  issues,
  onCreateIssue,
  onResolveIssue,
}) => {
  const [isCreating, setIsCreating] = useState(false);
  const [description, setDescription] = useState('');
  const [category, setCategory] = useState('formatting');
  const [expectedValue, setExpectedValue] = useState('');

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!description.trim()) return;

    onCreateIssue({
      description,
      category,
      expected_value: expectedValue,
      status: 'open',
    });

    setDescription('');
    setExpectedValue('');
    setIsCreating(false);
  };

  return (
    <div className="dashboard-card flex flex-col h-full overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-border bg-card/60 px-4 py-2.5 text-xs">
        <div className="flex items-center gap-1.5 font-semibold text-text-main">
          <AlertCircle className="size-3.5 text-amber-400" />
          <span>Reported Issues ({issues.length})</span>
        </div>

        <Button
          variant="secondary"
          size="sm"
          onClick={() => setIsCreating((prev) => !prev)}
          leftIcon={isCreating ? <X className="size-3" /> : <Plus className="size-3" />}
        >
          {isCreating ? 'Cancel' : 'New Issue'}
        </Button>
      </div>

      {/* Body */}
      <div className="flex-1 p-3 overflow-y-auto space-y-3">
        {/* Create Issue Form */}
        {isCreating && (
          <form onSubmit={handleCreate} className="rounded-lg border border-primary/30 bg-primary/[0.04] p-3 space-y-2 text-xs">
            <div>
              <label className="field-label">Category</label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                className="field h-8 text-xs"
              >
                <option value="formatting">Formatting / Layout</option>
                <option value="missing_text">Missing Text or Table</option>
                <option value="table_structure">Table Structure / Merge Error</option>
                <option value="ocr_error">OCR / Character Recognition</option>
                <option value="image_icon">Image or Icon Extraction</option>
              </select>
            </div>

            <div>
              <label className="field-label">Issue Description</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Describe the discrepancy..."
                rows={2}
                className="field text-xs p-2 resize-none"
                required
              />
            </div>

            <div>
              <label className="field-label">Expected Value (Optional)</label>
              <input
                type="text"
                value={expectedValue}
                onChange={(e) => setExpectedValue(e.target.value)}
                placeholder="What should it look like?"
                className="field h-8 text-xs"
              />
            </div>

            <div className="flex justify-end gap-2 pt-1">
              <Button type="button" variant="ghost" size="sm" onClick={() => setIsCreating(false)}>
                Cancel
              </Button>
              <Button type="submit" variant="primary" size="sm">
                Submit Issue
              </Button>
            </div>
          </form>
        )}

        {/* Issue List */}
        {issues.length === 0 && !isCreating ? (
          <div className="rounded-lg border border-dashed border-border p-6 text-center text-xs text-text-muted">
            <CheckCircle2 className="size-6 text-emerald-400 mx-auto mb-1.5 opacity-60" />
            <span>No open issues recorded for this workflow run.</span>
          </div>
        ) : (
          issues.map((iss) => (
            <div
              key={iss.id}
              className="rounded-lg border border-border bg-card p-3 space-y-1.5 text-xs"
            >
              <div className="flex items-center justify-between">
                <span className="rounded bg-amber-500/15 border border-amber-500/30 px-1.5 py-0.2 text-[10px] font-semibold text-amber-400 uppercase">
                  {iss.category}
                </span>
                <span className="text-[10px] text-text-muted">
                  {formatDate(iss.created_at)}
                </span>
              </div>

              <p className="text-text-main font-medium leading-relaxed">
                {iss.description}
              </p>

              {iss.expected_value && (
                <div className="rounded bg-black/20 p-2 text-[11px] text-text-muted">
                  <strong>Expected:</strong> {iss.expected_value}
                </div>
              )}

              {iss.status === 'open' && onResolveIssue && (
                <div className="flex justify-end pt-1">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => onResolveIssue(iss.id)}
                    leftIcon={<CheckCircle2 className="size-3 text-emerald-400" />}
                    className="text-[11px] text-emerald-400 hover:bg-emerald-500/10"
                  >
                    Resolve Issue
                  </Button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </div>
  );
};
