import { Moon, Sun } from 'lucide-react'
import { useTheme } from '../lib/theme'

/** Sun/moon toggle switching between the GP-DAT dark (default) and light themes. */
export function ThemeToggle() {
  const [theme, toggleTheme] = useTheme()

  return (
    <button
      type="button"
      onClick={toggleTheme}
      title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
      aria-label="Toggle theme"
      className="flex-none rounded-lg border border-[var(--border)] p-2.5 text-[var(--text-muted)] transition-colors hover:bg-white/5 hover:text-[var(--text-main)]"
    >
      {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  )
}
