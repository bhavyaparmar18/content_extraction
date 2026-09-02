import { FileText } from 'lucide-react'
import type { MigrationSection } from '../../types'

interface SectionNavProps {
  sections: MigrationSection[]
  activeIndex: number
  onSelect: (index: number) => void
}

/** Left-hand section navigator: click a section to show only its content on the right. */
export function SectionNav({ sections, activeIndex, onSelect }: SectionNavProps) {
  return (
    <nav className="dashboard-card sticky top-6 max-h-[calc(100vh-8rem)] w-full flex-none overflow-y-auto p-2 lg:w-72">
      <div className="px-2.5 py-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
        Sections ({sections.length})
      </div>
      <ul className="space-y-0.5">
        {sections.map((section, index) => {
          const isActive = index === activeIndex
          return (
            <li key={`${section.title}-${index}`}>
              <button
                type="button"
                onClick={() => onSelect(index)}
                aria-current={isActive}
                className={`flex w-full items-start gap-2.5 rounded-lg px-2.5 py-2.5 text-left text-sm transition-colors ${
                  isActive
                    ? 'bg-[var(--nav-active-bg)] text-[var(--primary)]'
                    : 'text-[var(--text-muted)] hover:bg-white/5 hover:text-[var(--text-main)]'
                }`}
              >
                <FileText size={15} className="mt-0.5 flex-none" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">
                    {section.section_number ? `${section.section_number}. ` : ''}
                    {section.title}
                  </span>
                  <span className={`block text-[11px] ${isActive ? 'text-[var(--primary)]/70' : 'text-[var(--text-muted)]/80'}`}>
                    {section.elements.length} element{section.elements.length === 1 ? '' : 's'}
                  </span>
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
