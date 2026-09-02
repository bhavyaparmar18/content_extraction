import { FileSearch, Loader2, PackageOpen, TriangleAlert } from 'lucide-react'
import type { SopRecord, ViewMode } from '../types'
import { SopGrid } from './SopGrid'
import { SopTable } from './SopTable'

interface SopListProps {
  records: SopRecord[]
  viewMode: ViewMode
  loading: boolean
  error: string | null
  /** True when a search term or filter is narrowing the list, for the empty-state copy. */
  hasActiveFilters: boolean
  onDelete: (sop: SopRecord) => void
}

export function SopList({ records, viewMode, loading, error, hasActiveFilters, onDelete }: SopListProps) {
  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16 text-sm text-[var(--text-muted)]">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[var(--primary)]/12 text-[var(--primary)]">
          <Loader2 size={22} className="animate-spin" />
        </div>
        Loading SOPs...
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center text-sm text-red-300">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-red-400/12">
          <TriangleAlert size={22} />
        </div>
        {error}
      </div>
    )
  }

  if (records.length === 0) {
    const Icon = hasActiveFilters ? FileSearch : PackageOpen
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center text-sm text-[var(--text-muted)]">
        <div className="flex h-12 w-12 items-center justify-center rounded-full bg-white/5 text-[var(--text-muted)]">
          <Icon size={22} />
        </div>
        {hasActiveFilters
          ? 'No SOPs match your search or filters.'
          : 'No SOPs uploaded yet. Click "Upload SOPs" to get started.'}
      </div>
    )
  }

  return viewMode === 'grid' ? (
    <SopGrid records={records} onDelete={onDelete} />
  ) : (
    <SopTable records={records} onDelete={onDelete} />
  )
}
