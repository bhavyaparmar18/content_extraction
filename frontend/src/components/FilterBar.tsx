import { SlidersHorizontal } from 'lucide-react'
import type { ReactNode } from 'react'
import type { FileTypeFilter, StatusFilter } from '../types'

interface FilterBarProps {
  statusFilter: StatusFilter
  onStatusFilterChange: (value: StatusFilter) => void
  typeFilter: FileTypeFilter
  onTypeFilterChange: (value: FileTypeFilter) => void
}

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'approved', label: 'Approved' },
  { value: 'in_review', label: 'Needs Review' },
  { value: 'rejected', label: 'Rejected' },
]

const TYPE_OPTIONS: { value: FileTypeFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'pdf', label: 'PDF' },
  { value: 'docx', label: 'DOCX' },
]

function Chip({
  active,
  onClick,
  children,
}: {
  active: boolean
  onClick: () => void
  children: ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
        active
          ? 'border-[var(--primary)]/40 bg-[var(--primary)]/15 text-[var(--primary)]'
          : 'border-[var(--border)] text-[var(--text-muted)] hover:bg-white/5 hover:text-[var(--text-main)]'
      }`}
    >
      {children}
    </button>
  )
}

export function FilterBar({ statusFilter, onStatusFilterChange, typeFilter, onTypeFilterChange }: FilterBarProps) {
  return (
    <div className="mt-4 flex flex-wrap items-center gap-4 px-1">
      <div className="flex items-center gap-1.5 text-xs font-medium text-[var(--text-muted)]">
        <SlidersHorizontal size={14} />
        Filters
      </div>

      <div className="flex flex-wrap items-center gap-1.5">
        {STATUS_OPTIONS.map((option) => (
          <Chip key={option.value} active={statusFilter === option.value} onClick={() => onStatusFilterChange(option.value)}>
            {option.label}
          </Chip>
        ))}
      </div>

      <div className="h-4 w-px bg-[var(--border)]" />

      <div className="flex flex-wrap items-center gap-1.5">
        {TYPE_OPTIONS.map((option) => (
          <Chip key={option.value} active={typeFilter === option.value} onClick={() => onTypeFilterChange(option.value)}>
            {option.label}
          </Chip>
        ))}
      </div>
    </div>
  )
}
