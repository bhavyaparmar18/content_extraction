import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  Clock,
  ChevronDown,
  ChevronUp,
  X,
  FileText,
} from 'lucide-react';
import { BatchJob, DocumentJob } from '@/types';
import { Button } from '@/components/ui/Button';

interface JobProgressBannerProps {
  job: BatchJob | null;
  onDismiss: () => void;
}

export const JobProgressBanner: React.FC<JobProgressBannerProps> = ({ job, onDismiss }) => {
  const [isExpanded, setIsExpanded] = useState(true);

  if (!job) return null;

  const total = job.documents.length;
  const completed = job.documents.filter((d) => d.status === 'completed').length;
  const failed = job.documents.filter((d) => d.status === 'failed').length;
  const processing = job.documents.filter((d) => d.status === 'processing').length;
  const isDone = job.status === 'completed' || job.status === 'failed';

  const overallProgress =
    total > 0
      ? Math.round(
          job.documents.reduce((acc, d) => acc + (d.progress_percentage || 0), 0) / total
        )
      : 0;

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className="dashboard-card mb-6 overflow-hidden border-primary/30 bg-primary/[0.04]"
    >
      {/* Header Summary */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4">
        <div className="flex items-center gap-3">
          <div
            className={`grid size-9 shrink-0 place-items-center rounded-lg border ${
              isDone
                ? failed > 0
                  ? 'border-amber-500/30 bg-amber-500/10 text-amber-400'
                  : 'border-emerald-500/30 bg-emerald-500/10 text-emerald-400'
                : 'border-primary/30 bg-primary/10 text-primary'
            }`}
          >
            {isDone ? (
              failed > 0 ? (
                <AlertCircle className="size-4" />
              ) : (
                <CheckCircle2 className="size-4" />
              )
            ) : (
              <RefreshCw className="size-4 animate-spin" />
            )}
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-text-main">
                {isDone
                  ? failed > 0
                    ? `Extraction finished with ${failed} issue(s)`
                    : 'Batch extraction completed successfully'
                  : `Extracting ${total} document(s)...`}
              </span>
              <span className="rounded bg-primary/15 px-1.5 py-0.5 text-[10px] font-mono text-primary">
                {overallProgress}%
              </span>
            </div>
            <div className="text-xs text-text-muted mt-0.5">
              {completed} completed • {processing} processing • {failed} failed • {total} total
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setIsExpanded((prev) => !prev)}
            leftIcon={isExpanded ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
          >
            {isExpanded ? 'Hide Details' : 'View Details'}
          </Button>

          {isDone && (
            <Button variant="ghost" size="sm" onClick={onDismiss} aria-label="Dismiss">
              <X className="size-3.5" />
            </Button>
          )}
        </div>
      </div>

      {/* Progress Bar */}
      <div className="h-1.5 w-full bg-border">
        <div
          className={`h-full transition-all duration-300 ${
            failed > 0 && isDone ? 'bg-amber-400' : 'bg-primary'
          }`}
          style={{ width: `${overallProgress}%` }}
        />
      </div>

      {/* Expanded Document Breakdown */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="border-t border-border/50 divide-y divide-border/30 bg-black/20"
          >
            {job.documents.map((doc: DocumentJob, idx: number) => (
              <div key={doc.document_id || idx} className="flex items-center justify-between p-3 text-xs">
                <div className="flex items-center gap-2.5 min-w-0 max-w-md">
                  <FileText className="size-4 text-text-muted shrink-0" />
                  <span className="font-mono text-text-main truncate">
                    {doc.filename || doc.document_id}
                  </span>
                </div>

                <div className="flex items-center gap-4">
                  <div className="text-text-muted hidden sm:block">
                    {doc.message || 'Queued'}
                  </div>

                  <div className="flex items-center gap-2 w-28">
                    <div className="flex-1 h-1.5 bg-border rounded-full overflow-hidden">
                      <div
                        className="h-full bg-primary transition-all duration-300 rounded-full"
                        style={{ width: `${doc.progress_percentage || 0}%` }}
                      />
                    </div>
                    <span className="text-[10px] font-mono text-text-muted w-8 text-right">
                      {doc.progress_percentage || 0}%
                    </span>
                  </div>

                  <div className="w-20 text-right">
                    {doc.status === 'completed' && (
                      <span className="inline-flex items-center gap-1 text-emerald-400 font-medium">
                        <CheckCircle2 className="size-3.5" /> Done
                      </span>
                    )}
                    {doc.status === 'processing' && (
                      <span className="inline-flex items-center gap-1 text-sky-400 font-medium">
                        <RefreshCw className="size-3 animate-spin" /> In progress
                      </span>
                    )}
                    {doc.status === 'failed' && (
                      <span className="inline-flex items-center gap-1 text-red-400 font-medium" title={doc.error || 'Extraction failed'}>
                        <AlertCircle className="size-3.5" /> Failed
                      </span>
                    )}
                    {doc.status === 'queued' && (
                      <span className="inline-flex items-center gap-1 text-text-muted">
                        <Clock className="size-3" /> Queued
                      </span>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};
