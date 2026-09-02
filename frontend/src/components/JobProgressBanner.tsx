import { CheckCircle2, Loader2, X, XCircle } from 'lucide-react'
import type { BatchJob } from '../types'

interface JobProgressBannerProps {
  job: BatchJob
  onDismiss: () => void
}

/** Overall progress across all documents in the job, 0-100. */
function overallProgress(job: BatchJob): number {
  if (job.documents.length === 0) return 100
  const sum = job.documents.reduce((acc, doc) => acc + doc.progress_percentage, 0)
  return Math.round(sum / job.documents.length)
}

export function JobProgressBanner({ job, onDismiss }: JobProgressBannerProps) {
  const isDone = job.status === 'completed' || job.status === 'failed'
  const completedCount = job.documents.filter((d) => d.status === 'completed').length
  const failedCount = job.documents.filter((d) => d.status === 'failed').length
  const progress = overallProgress(job)

  return (
    <div className="dashboard-card mt-6 flex items-center gap-4 px-4 py-4">
      {isDone ? (
        job.status === 'completed' ? (
          <CheckCircle2 size={20} className="flex-none text-[var(--primary)]" />
        ) : (
          <XCircle size={20} className="flex-none text-red-300" />
        )
      ) : (
        <Loader2 size={20} className="flex-none animate-spin text-sky-300" />
      )}

      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">
          {isDone
            ? `Batch upload ${job.status === 'completed' ? 'completed' : 'finished with errors'}`
            : 'Processing uploaded SOPs...'}
        </p>
        <p className="mt-0.5 text-xs text-[var(--text-muted)]">
          {completedCount} completed · {failedCount} failed · {job.documents.length} total
          {job.rejected_files.length > 0 && ` · ${job.rejected_files.length} rejected before processing`}
        </p>
        {!isDone && (
          <div className="mt-2 h-1.5 w-full overflow-hidden rounded-full bg-white/5">
            <div
              className="h-full rounded-full bg-[var(--primary)] transition-all"
              style={{ width: `${progress}%` }}
            />
          </div>
        )}
      </div>

      {isDone && (
        <button
          type="button"
          onClick={onDismiss}
          className="flex-none rounded-md p-1.5 text-[var(--text-muted)] hover:bg-white/5 hover:text-[var(--text-main)]"
        >
          <X size={16} />
        </button>
      )}
    </div>
  )
}
