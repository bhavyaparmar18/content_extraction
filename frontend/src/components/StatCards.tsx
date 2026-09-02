import { CheckCircle2, Layers, Loader2, TriangleAlert, XCircle } from 'lucide-react'
import type { ComponentType } from 'react'
import type { StatCardData } from '../lib/stats'

interface StatIconConfig {
  icon: ComponentType<{ size?: number; className?: string }>
  badgeClassName: string
}

/** Each KPI gets an icon inside a soft-tinted circle matching its semantic color. */
const ICON_CONFIG: Record<string, StatIconConfig> = {
  total: { icon: Layers, badgeClassName: 'bg-[var(--primary)]/12 text-[var(--primary)]' },
  completed: { icon: CheckCircle2, badgeClassName: 'bg-[var(--primary)]/12 text-[var(--primary)]' },
  processing: { icon: Loader2, badgeClassName: 'bg-sky-400/12 text-sky-300' },
  needs_review: { icon: TriangleAlert, badgeClassName: 'bg-amber-400/12 text-amber-300' },
  failed: { icon: XCircle, badgeClassName: 'bg-red-400/12 text-red-300' },
}

export function StatCards({ stats }: { stats: StatCardData[] }) {
  return (
    <div className="mt-6 grid gap-4 md:grid-cols-2 xl:grid-cols-5">
      {stats.map((stat) => {
        const config = ICON_CONFIG[stat.key] ?? ICON_CONFIG.total
        const Icon = config.icon
        return (
          <div key={stat.key} className="dashboard-card px-4 py-4">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[13px] text-[var(--text-muted)]">{stat.label}</span>
              <div className={`flex h-9 w-9 flex-none items-center justify-center rounded-full ${config.badgeClassName}`}>
                <Icon size={17} className={stat.key === 'processing' ? 'animate-spin' : undefined} />
              </div>
            </div>
            <div className="mt-4 text-3xl font-semibold">{stat.value}</div>
            <div className="mt-1 text-[11px] uppercase tracking-[0.08em] text-[var(--text-muted)]">
              {stat.sublabel}
            </div>
          </div>
        )
      })}
    </div>
  )
}
