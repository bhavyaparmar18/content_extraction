import React, { useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertCircle, X } from 'lucide-react';
import { Button } from './Button';

interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  isDangerous?: boolean;
  isLoading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export const ConfirmDialog: React.FC<ConfirmDialogProps> = ({
  isOpen,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  isDangerous = false,
  isLoading = false,
  onConfirm,
  onCancel,
}) => {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen && !isLoading) {
        onCancel();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, isLoading, onCancel]);

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm"
            onClick={isLoading ? undefined : onCancel}
          />
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 10 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 10 }}
            className="relative w-full max-w-md rounded-xl border border-border bg-card p-6 shadow-panel z-10"
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="dialog-title"
          >
            <div className="flex items-start gap-4">
              <div
                className={`grid size-10 shrink-0 place-items-center rounded-lg border ${
                  isDangerous
                    ? 'border-red-500/30 bg-red-500/10 text-red-400'
                    : 'border-primary/30 bg-primary/10 text-primary'
                }`}
              >
                <AlertCircle className="size-5" />
              </div>

              <div className="flex-1 min-w-0">
                <h3 id="dialog-title" className="text-base font-semibold text-text-main">
                  {title}
                </h3>
                <p className="mt-2 text-sm text-text-muted leading-relaxed">{message}</p>
              </div>

              <button
                onClick={onCancel}
                disabled={isLoading}
                className="text-text-muted hover:text-text-main p-1 transition"
                aria-label="Close"
              >
                <X className="size-5" />
              </button>
            </div>

            <div className="mt-6 flex items-center justify-end gap-3">
              <Button variant="secondary" onClick={onCancel} disabled={isLoading}>
                {cancelLabel}
              </Button>
              <Button
                variant={isDangerous ? 'danger' : 'primary'}
                onClick={onConfirm}
                isLoading={isLoading}
              >
                {confirmLabel}
              </Button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};
