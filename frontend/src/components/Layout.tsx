import type { ReactNode } from 'react'
import { ChevronRight } from 'lucide-react'
import { Sidebar } from './Sidebar'

interface LayoutProps {
  children: ReactNode
  /** Trailing breadcrumb segment(s) after "GP-DAT / Documents". Defaults to "GP Repository". */
  breadcrumb?: ReactNode
}

/**
 * Page shell: fixed sidebar + breadcrumb + scrollable content area.
 *
 * The outer row is pinned to the viewport height (`h-screen` + `overflow-hidden`)
 * so the sidebar never moves and the content pane below is the *only* thing
 * that scrolls — without a bounded height here, `overflow-y-auto` on the content
 * pane has nothing to clip against and the whole document scrolls instead,
 * dragging the sidebar off-screen with it.
 */
export function Layout({ children, breadcrumb = 'GP Repository' }: LayoutProps) {
  return (
    <div className="flex h-screen overflow-hidden bg-[var(--bg-main)] text-[var(--text-main)]">
      <Sidebar />
      <div className="min-w-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1600px] px-4 py-6 md:px-8">
          <div className="flex items-center gap-1.5 pb-4 text-xs text-[var(--text-muted)]">
            <span>GP-DAT</span>
            <ChevronRight size={13} />
            <span>Documents</span>
            <ChevronRight size={13} />
            <span className="text-[var(--text-main)]">{breadcrumb}</span>
          </div>
          {children}
        </div>
      </div>
    </div>
  )
}
