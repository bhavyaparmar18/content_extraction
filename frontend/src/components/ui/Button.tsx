import type { ButtonHTMLAttributes, ReactNode } from 'react'

type ButtonVariant = 'primary' | 'ghost' | 'icon'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  children: ReactNode
}

const BASE =
  'inline-flex items-center justify-center gap-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-[var(--primary)]/50'

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary: 'btn-primary px-4 py-2.5 rounded-lg',
  ghost:
    'rounded-lg border border-[var(--border)] px-4 py-2.5 text-[var(--text-main)] hover:bg-white/5',
  icon: 'rounded-lg p-2 text-[var(--text-muted)] hover:bg-white/5 hover:text-[var(--text-main)]',
}

/** Shared button primitive matching the GP-DAT design tokens (see frontend.md). */
export function Button({ variant = 'primary', className = '', children, ...rest }: ButtonProps) {
  return (
    <button className={`${BASE} ${VARIANT_CLASSES[variant]} ${className}`} {...rest}>
      {children}
    </button>
  )
}
