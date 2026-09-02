import { LayoutGrid, List, Search } from 'lucide-react'
import type { ViewMode } from '../types'

interface SearchBarProps {
  value: string
  onChange: (value: string) => void
  viewMode: ViewMode
  onViewModeChange: (mode: ViewMode) => void
}

export function SearchBar({ value, onChange, viewMode, onViewModeChange }: SearchBarProps) {
  return (
    <div className="dashboard-card mt-6 flex items-center gap-3 p-3 sm:p-4">
      <div className="relative flex-1">
        <Search
          size={16}
          className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
        />
        <input
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="Search by SOP title, number, filename, content..."
          className="h-12 w-full rounded-xl border border-[var(--border)] bg-[var(--bg-main)]/70 pl-11 pr-4 text-sm text-[var(--text-main)] outline-none placeholder:text-[var(--text-muted)] focus:border-[var(--primary)]/50"
        />
      </div>

      <div className="flex items-center gap-1 rounded-lg border border-[var(--border)] p-1">
        <button
          type="button"
          onClick={() => onViewModeChange('list')}
          aria-pressed={viewMode === 'list'}
          className={`rounded-md p-2 ${
            viewMode === 'list'
              ? 'bg-[var(--primary)]/15 text-[var(--primary)]'
              : 'text-[var(--text-muted)] hover:bg-white/5'
          }`}
        >
          <List size={16} />
        </button>
        <button
          type="button"
          onClick={() => onViewModeChange('grid')}
          aria-pressed={viewMode === 'grid'}
          className={`rounded-md p-2 ${
            viewMode === 'grid'
              ? 'bg-[var(--primary)]/15 text-[var(--primary)]'
              : 'text-[var(--text-muted)] hover:bg-white/5'
          }`}
        >
          <LayoutGrid size={16} />
        </button>
      </div>
    </div>
  )
}
