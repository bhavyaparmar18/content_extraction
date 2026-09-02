import { Eye, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { formatDate } from '../lib/format'
import { displaySubline, displayTitle } from '../lib/sopDisplay'
import type { SopRecord } from '../types'
import { FileTypeIcon } from './FileTypeIcon'
import { StatusBadge } from './StatusBadge'

interface SopTableProps {
  records: SopRecord[]
  onDelete: (sop: SopRecord) => void
}

export function SopTable({ records, onDelete }: SopTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[900px] text-left text-sm">
        <thead>
          <tr className="border-b border-[var(--border)] text-[11px] uppercase tracking-[0.08em] text-[var(--text-muted)]">
            <th className="px-4 py-3 font-medium">SOP</th>
            <th className="px-4 py-3 font-medium">Status</th>
            <th className="px-4 py-3 font-medium">Uploaded</th>
            <th className="px-4 py-3 font-medium">Updated</th>
            <th className="px-4 py-3 font-medium text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {records.map((sop) => (
            <tr key={sop.id} className="border-b border-[var(--border)] last:border-b-0 hover:bg-white/[0.03]">
              <td className="max-w-[380px] px-4 py-3">
                <div className="flex items-start gap-3">
                  <FileTypeIcon fileType={sop.file_type} />
                  <div className="min-w-0">
                    <div className="truncate font-medium" title={displayTitle(sop)}>
                      {displayTitle(sop)}
                    </div>
                    <div className="mt-0.5 truncate text-xs text-[var(--text-muted)]" title={displaySubline(sop)}>
                      {displaySubline(sop)}
                    </div>
                  </div>
                </div>
              </td>
              <td className="px-4 py-3">
                <StatusBadge status={sop.status} />
              </td>
              <td className="px-4 py-3 text-[var(--text-muted)]">{formatDate(sop.created_at)}</td>
              <td className="px-4 py-3 text-[var(--text-muted)]">{formatDate(sop.updated_at)}</td>
              <td className="px-4 py-3">
                <div className="flex items-center justify-end gap-2">
                  <Link
                    to={`/sops/${sop.id}`}
                    title="View extracted content"
                    className="inline-flex items-center gap-1.5 rounded-lg border border-[var(--border)] px-3 py-1.5 text-xs font-medium text-[var(--text-main)] hover:border-[var(--primary)]/30 hover:bg-[var(--primary)]/10 hover:text-[var(--primary)]"
                  >
                    <Eye size={13} />
                    View SOP
                  </Link>
                  <button
                    type="button"
                    onClick={() => onDelete(sop)}
                    title="Delete this SOP record"
                    className="inline-flex items-center justify-center rounded-lg border border-[var(--border)] p-1.5 text-[var(--text-muted)] hover:border-red-400/30 hover:bg-red-400/10 hover:text-red-300"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
