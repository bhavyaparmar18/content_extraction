import React, { useState, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  UploadCloud,
  FileText,
  X,
  AlertCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { formatBytes } from '@/lib/format';
import { api } from '@/lib/api';
import { BatchJob, RejectedFile } from '@/types';
import { useToast } from '@/components/ui/ToastStack';

interface UploadSopsProps {
  isOpen: boolean;
  onClose: () => void;
  onUploadSuccess: (job: BatchJob) => void;
}

interface StagedFile {
  file: File;
  id: string;
  isValid: boolean;
  error?: string;
}

export const UploadSops: React.FC<UploadSopsProps> = ({
  isOpen,
  onClose,
  onUploadSuccess,
}) => {
  const { error: toastError, success: toastSuccess } = useToast();
  const [stagedFiles, setStagedFiles] = useState<StagedFile[]>([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [rejectedBackendFiles, setRejectedBackendFiles] = useState<RejectedFile[]>([]);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const MAX_SIZE_BYTES = 50 * 1024 * 1024; // 50MB
  const ALLOWED_EXTS = ['.pdf', '.docx'];

  const validateAndAddFiles = (files: FileList | File[]) => {
    const newStaged: StagedFile[] = [];

    Array.from(files).forEach((file) => {
      const ext = '.' + file.name.split('.').pop()?.toLowerCase();
      let isValid = true;
      let error = '';

      if (!ALLOWED_EXTS.includes(ext)) {
        isValid = false;
        error = `Unsupported format (${ext}). Allowed: .pdf, .docx`;
      } else if (file.size > MAX_SIZE_BYTES) {
        isValid = false;
        error = `File exceeds 50 MB limit (${formatBytes(file.size)})`;
      } else if (file.size === 0) {
        isValid = false;
        error = 'File is empty (0 bytes)';
      }

      newStaged.push({
        file,
        id: `${file.name}_${file.size}_${Date.now()}_${Math.random()}`,
        isValid,
        error,
      });
    });

    setStagedFiles((prev) => [...prev, ...newStaged]);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndAddFiles(e.dataTransfer.files);
    }
  };

  const removeFile = (id: string) => {
    setStagedFiles((prev) => prev.filter((f) => f.id !== id));
  };

  const clearAll = () => {
    setStagedFiles([]);
    setRejectedBackendFiles([]);
  };

  const validFiles = stagedFiles.filter((f) => f.isValid);
  const invalidFiles = stagedFiles.filter((f) => !f.isValid);

  const handleSubmit = async () => {
    if (validFiles.length === 0) {
      toastError('Please select at least one valid PDF or DOCX document.');
      return;
    }

    setIsSubmitting(true);
    setRejectedBackendFiles([]);

    try {
      const filesToUpload = validFiles.map((sf) => sf.file);
      const batchJob = await api.uploadBatch(filesToUpload);

      if (batchJob.rejected_files && batchJob.rejected_files.length > 0) {
        setRejectedBackendFiles(batchJob.rejected_files);
      }

      toastSuccess(
        `Batch job queued with ${batchJob.documents?.length || filesToUpload.length} document(s).`,
        'Upload Accepted'
      );
      onUploadSuccess(batchJob);
      onClose();
      clearAll();
    } catch (err: any) {
      toastError(err.message || 'Failed to submit batch upload.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        className="fixed inset-0 bg-black/70 backdrop-blur-sm"
        onClick={isSubmitting ? undefined : onClose}
      />

      {/* Modal Dialog */}
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        className="relative flex flex-col w-full max-w-2xl max-h-[90vh] rounded-xl border border-border bg-card shadow-panel z-10 overflow-hidden"
      >
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-6 py-4">
          <div>
            <h2 className="text-lg font-semibold text-text-main">Upload SOP Batch</h2>
            <p className="text-xs text-text-muted mt-0.5">
              Upload PDF or Word documents for automatic structured parsing & extraction
            </p>
          </div>
          <button
            onClick={onClose}
            disabled={isSubmitting}
            className="text-text-muted hover:text-text-main p-1 transition"
          >
            <X className="size-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-5">
          {/* Dropzone */}
          <div
            onDragOver={(e) => {
              e.preventDefault();
              setIsDragging(true);
            }}
            onDragLeave={() => setIsDragging(false)}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`flex flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 text-center cursor-pointer transition-all ${
              isDragging
                ? 'border-primary bg-primary/10'
                : 'border-border hover:border-primary/50 hover:bg-white/[0.02]'
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
              className="hidden"
              onChange={(e) => {
                if (e.target.files && e.target.files.length > 0) {
                  validateAndAddFiles(e.target.files);
                }
              }}
            />

            <div className="grid size-12 place-items-center rounded-full bg-primary/10 text-primary mb-3">
              <UploadCloud className="size-6" />
            </div>

            <div className="text-sm font-semibold text-text-main">
              Click to select or drag & drop SOP files here
            </div>
            <div className="text-xs text-text-muted mt-1">
              Supports .PDF and .DOCX files up to 50 MB each
            </div>
          </div>

          {/* Staged File List */}
          {stagedFiles.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center justify-between text-xs font-medium text-text-muted">
                <span>Selected Documents ({validFiles.length} valid, {invalidFiles.length} rejected)</span>
                <button
                  type="button"
                  onClick={clearAll}
                  className="text-xs text-red-400 hover:underline"
                >
                  Clear All
                </button>
              </div>

              <div className="max-h-48 overflow-y-auto rounded-lg border border-border divide-y divide-border bg-black/10">
                {stagedFiles.map((sf) => (
                  <div key={sf.id} className="flex items-center justify-between p-2.5 text-xs">
                    <div className="flex items-center gap-2.5 min-w-0 flex-1 mr-3">
                      <FileText
                        className={`size-4 shrink-0 ${
                          sf.isValid ? 'text-primary' : 'text-red-400'
                        }`}
                      />
                      <div className="min-w-0">
                        <div className="font-medium text-text-main truncate">
                          {sf.file.name}
                        </div>
                        <div className="text-[10px] text-text-muted">
                          {formatBytes(sf.file.size)}
                          {sf.error && <span className="text-red-400 ml-2">⚠️ {sf.error}</span>}
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {sf.isValid ? (
                        <span className="rounded bg-emerald-500/15 px-2 py-0.5 text-[10px] font-medium text-emerald-400">
                          Ready
                        </span>
                      ) : (
                        <span className="rounded bg-red-500/15 px-2 py-0.5 text-[10px] font-medium text-red-400">
                          Rejected
                        </span>
                      )}

                      <button
                        type="button"
                        onClick={() => removeFile(sf.id)}
                        className="text-text-muted hover:text-text-main p-1 transition"
                      >
                        <X className="size-3.5" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Backend Rejected Files */}
          {rejectedBackendFiles.length > 0 && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-3 space-y-1">
              <div className="text-xs font-semibold text-amber-400 flex items-center gap-1.5">
                <AlertCircle className="size-3.5" />
                <span>Files rejected by server:</span>
              </div>
              {rejectedBackendFiles.map((rf, idx) => (
                <div key={idx} className="text-xs text-text-muted flex justify-between">
                  <span className="font-mono text-text-main">{rf.filename}</span>
                  <span className="text-amber-400">{rf.reason}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-border bg-card px-6 py-4">
          <div className="text-xs text-text-muted">
            {validFiles.length > 0 && (
              <span>
                Ready to extract <strong className="text-text-main">{validFiles.length}</strong> document(s)
              </span>
            )}
          </div>

          <div className="flex items-center gap-3">
            <Button variant="secondary" onClick={onClose} disabled={isSubmitting}>
              Cancel
            </Button>
            <Button
              variant="primary"
              onClick={handleSubmit}
              isLoading={isSubmitting}
              disabled={validFiles.length === 0}
              leftIcon={<UploadCloud className="size-4" />}
            >
              Start Batch Extraction
            </Button>
          </div>
        </div>
      </motion.div>
    </div>
  );
};
