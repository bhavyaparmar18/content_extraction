import { LibraryBig, Mail, Sparkles } from 'lucide-react'

/**
 * Minimal GP-DAT sidebar: only the SOP Repository entry point is wired up for now.
 * Other sections (Templates, Migration, Translation, Settings, ...) are intentionally
 * left out until those areas of the product are built.
 */
export function Sidebar() {
  return (
    <aside className="flex h-full w-64 flex-none flex-col border-r border-[var(--border)] bg-[var(--sidebar-bg)]">
      <div className="flex items-center gap-2.5 px-5 py-5">
        <div className="flex h-9 w-9 flex-none items-center justify-center rounded-xl bg-gradient-to-br from-[var(--primary)] to-[var(--primary-dark)] text-sm font-bold text-[#08312A] shadow-[0_4px_14px_rgba(0,228,124,0.35)]">
          <Sparkles size={18} strokeWidth={2.25} />
        </div>
        <div>
          <div className="text-sm font-semibold leading-tight">GP-DAT</div>
          <div className="text-[11px] leading-tight text-[var(--text-muted)]">Platform v1.0</div>
        </div>
      </div>

      <nav className="flex-1 px-3 py-2">
        <div className="px-2 pb-2 text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--text-muted)]">
          Documents
        </div>
        <div className="flex items-center gap-3 rounded-lg bg-[var(--nav-active-bg)] px-3 py-2.5 text-[var(--primary)]">
          <LibraryBig size={17} />
          <span className="min-w-0 flex-1">
            <span className="block text-sm font-medium">GP Docs</span>
            <span className="block text-[11px] text-[var(--primary)]/80">Source documents</span>
          </span>
        </div>
      </nav>

      <div className="border-t border-[var(--border)] px-5 py-4">
        <a
          href="mailto:support@gpdat.example"
          className="flex items-center gap-2 text-xs text-[var(--text-muted)] hover:text-[var(--text-main)]"
        >
          <Mail size={14} />
          Contact Us
        </a>
      </div>
    </aside>
  )
}
