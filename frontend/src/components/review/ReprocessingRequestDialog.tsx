import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { RotateCcw, X, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/Button';

interface ReprocessingRequestDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: { reason: string; pages?: string }) => void;
  isLoading?: boolean;
}

export const ReprocessingRequestDialog: React.FC<ReprocessingRequestDialogProps> = ({
  isOpen,
  onClose,
  onSubmit,
  isLoading = false,
}) => {
  const [reason, setReason] = useState('');
  const [pages, setPages] = useState('all');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!reason.trim()) return;
    onSubmit({ reason, pages });
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/70 backdrop-blur-sm"
        onClick={isLoading ? undefined : onClose}
      />

      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        className="relative w-full max-w-lg rounded-xl border border-border bg-card p-6 shadow-panel z-10 space-y-4"
      >
        <div className="flex items-center justify-between border-b border-border pb-3">
          <div className="flex items-center gap-2">
            <div className="grid size-8 place-items-center rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20">
              <RotateCcw className="size-4" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-text-main">Request Extraction Reprocessing</h3>
              <p className="text-[11px] text-text-muted">Requires administrator approval before queueing</p>
            </div>
          </div>
          <button onClick={onClose} disabled={isLoading} className="text-text-muted hover:text-text-main p-1">
            <X className="size-4" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 text-xs">
          <div>
            <label className="field-label">Scope / Target Pages</label>
            <select
              value={pages}
              onChange={(e) => setPages(e.target.value)}
              className="field h-9 text-xs"
            >
              <option value="all">Full Document (All Pages)</option>
              <option value="tables_only">Tables & Stitching Only</option>
              <option value="ocr_enhanced">Full OCR Enhanced Pass</option>
              <option value="icons_graphics">Graphics & Icon Reclassification Only</option>
            </select>
          </div>

          <div>
            <label className="field-label">Reason / Extraction Defect</label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              rows={4}
              placeholder="Explain why reprocessing is needed (e.g. cross-page table missed header row, missing subscript equations)..."
              className="field text-xs p-3 resize-none bg-black/20"
              required
            />
          </div>

          <div className="flex items-center justify-end gap-2 pt-2 border-t border-border">
            <Button variant="secondary" type="button" onClick={onClose} disabled={isLoading}>
              Cancel
            </Button>
            <Button
              variant="primary"
              type="submit"
              isLoading={isLoading}
              disabled={!reason.trim()}
              leftIcon={<RotateCcw className="size-3.5" />}
            >
              Submit for Admin Review
            </Button>
          </div>
        </form>
      </motion.div>
    </div>
  );
};
