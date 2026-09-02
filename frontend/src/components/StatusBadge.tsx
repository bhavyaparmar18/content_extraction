import { CheckCircle2, Clock, TriangleAlert, XCircle } from 'lucide-react'
import type { ComponentType } from 'react'
import type { JobStatus, SopStatus } from '../types'

type AnyStatus = SopStatus | JobStatus

interface StatusConfig {
  label: string
  className: string
  icon: ComponentType<{ size?: number; className?: string }>
}

/** Color language follows frontend.md: green = good/primary, sky = in-progress, red = destructive. */
const STATUS_CONFIG: Record<AnyStatus, StatusConfig> = {
  approved: {
    label: 'Approved',
    className: 'border-[var(--primary)]/30 bg-[var(--primary)]/10 text-[var(--primary)]',
    icon: CheckCircle2,
  },
  in_review: {
    label: 'Needs Review',
    className: 'border-amber-400/30 bg-amber-400/10 text-amber-300',
    icon: TriangleAlert,
  },
  rejected: {
    label: 'Rejected',
    className: 'border-red-400/30 bg-red-400/10 text-red-300',
    icon: XCircle,
  },
  queued: {
    label: 'Queued',
    className: 'border-[var(--text-muted)]/30 bg-white/5 text-[var(--text-muted)]',
    icon: Clock,
  },
  processing: {
    label: 'Processing',
    className: 'border-sky-400/30 bg-sky-400/10 text-sky-300',
    icon: Clock,
  },
  completed: {
    label: 'Completed',
    className: 'border-[var(--primary)]/30 bg-[var(--primary)]/10 text-[var(--primary)]',
    icon: CheckCircle2,
  },
  failed: {
    label: 'Failed',
    className: 'border-red-400/30 bg-red-400/10 text-red-300',
    icon: XCircle,
  },
}

/** Small colored pill used for both review status (SopStatus) and job status (JobStatus). */
export function StatusBadge({ status }: { status: AnyStatus }) {
  const config = STATUS_CONFIG[status]
  const Icon = config.icon
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium whitespace-nowrap ${config.className}`}
    >
      <Icon size={12} />
      {config.label}
    </span>
  )
}
