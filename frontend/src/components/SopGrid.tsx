import { Eye, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { formatDate } from '../lib/format'
import { displaySubline, displayTitle } from '../lib/sopDisplay'
import type { SopRecord } from '../types'
import { FileTypeIcon } from './FileTypeIcon'
import { StatusBadge } from './StatusBadge'

interface SopGridProps {
  records: SopRecord[]
  onDelete: (sop: SopRecord) => void
}

export function SopGrid({ records, onDelete }: SopGridProps) {
  return (
    <div className="grid gap-3 p-3 sm:grid-cols-2 xl:grid-cols-3">
      {records.map((sop) => (
        <div key={sop.id} className="dashboard-card flex flex-col gap-3 p-4">
          <div className="flex items-start justify-between gap-2">
            <div className="flex items-start gap-2.5 min-w-0">
              <FileTypeIcon fileType={sop.file_type} size="sm" />
              <div className="min-w-0">
                <div className="truncate font-medium" title={displayTitle(sop)}>
                  {displayTitle(sop)}
                </div>
                <div className="mt-0.5 truncate text-xs text-[var(--text-muted)]" title={displaySubline(sop)}>
                  {displaySubline(sop)}
                </div>
              </div>
            </div>
            <StatusBadge status={sop.status} />
          </div>

          <dl className="grid grid-cols-2 gap-y-1.5 text-xs text-[var(--text-muted)]">
            <dt>Uploaded</dt>
            <dd className="text-right text-[var(--text-main)]">{formatDate(sop.created_at)}</dd>
            <dt>Updated</dt>
            <dd className="text-right text-[var(--text-main)]">{formatDate(sop.updated_at)}</dd>
          </dl>

          <div className="mt-1 flex items-center gap-2">
            <Link
              to={`/sops/${sop.id}`}
              title="View extracted content"
              className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs font-medium text-[var(--text-main)] hover:border-[var(--primary)]/30 hover:bg-[var(--primary)]/10 hover:text-[var(--primary)]"
            >
              <Eye size={13} />
              View SOP
            </Link>
            <button
              type="button"
              onClick={() => onDelete(sop)}
              title="Delete this SOP record"
              className="inline-flex flex-none items-center justify-center rounded-lg border border-[var(--border)] p-1.5 text-[var(--text-muted)] hover:border-red-400/30 hover:bg-red-400/10 hover:text-red-300"
            >
              <Trash2 size={14} />
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
