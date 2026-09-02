import { useCallback, useState } from 'react'

export type Theme = 'dark' | 'light'

const STORAGE_KEY = 'gpdat.theme'
const DEFAULT_THEME: Theme = 'dark'

/** Read the persisted theme preference, defaulting to dark (GP-DAT default). */
export function getTheme(): Theme {
  if (typeof window === 'undefined') return DEFAULT_THEME
  const stored = window.localStorage.getItem(STORAGE_KEY)
  return stored === 'light' ? 'light' : DEFAULT_THEME
}

/** Apply the theme to the document root and persist the choice. */
export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute('data-theme', theme)
  window.localStorage.setItem(STORAGE_KEY, theme)
}

/**
 * React-facing wrapper around getTheme/applyTheme: keeps the current theme in
 * state so toggling it re-renders whatever component reads it (plain
 * applyTheme calls only mutate the DOM attribute, which React never observes).
 */
export function useTheme(): [Theme, () => void] {
  const [theme, setTheme] = useState<Theme>(getTheme)

  const toggleTheme = useCallback(() => {
    setTheme((prev) => {
      const next: Theme = prev === 'dark' ? 'light' : 'dark'
      applyTheme(next)
      return next
    })
  }, [])

  return [theme, toggleTheme]
}
