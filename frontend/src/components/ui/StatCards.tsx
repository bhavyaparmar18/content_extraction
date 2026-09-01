import React from 'react';
import { FileText, CheckCircle2, Clock, AlertTriangle, RefreshCw } from 'lucide-react';
import { RepositoryStats } from '@/lib/stats';

interface StatCardsProps {
  stats: RepositoryStats;
  selectedFilter?: string | null;
  onSelectFilter?: (filter: string | null) => void;
}

export const StatCards: React.FC<StatCardsProps> = ({
  stats,
  selectedFilter,
  onSelectFilter,
}) => {
  const cards = [
    {
      id: 'all',
      filterValue: null,
      label: 'Total SOPs',
      count: stats.totalSops,
      icon: FileText,
      color: 'text-primary',
      bg: 'bg-primary/10',
      border: 'border-primary/20',
    },
    {
      id: 'approved',
      filterValue: 'approved',
      label: 'Completed',
      count: stats.completed,
      icon: CheckCircle2,
      color: 'text-emerald-400',
      bg: 'bg-emerald-500/10',
      border: 'border-emerald-500/20',
    },
    {
      id: 'processing',
      filterValue: null,
      label: 'Processing',
      count: stats.processing,
      icon: RefreshCw,
      color: 'text-sky-400',
      bg: 'bg-sky-500/10',
      border: 'border-sky-500/20',
      animateIcon: stats.processing > 0,
    },
    {
      id: 'in_review',
      filterValue: 'in_review',
      label: 'Needs Review',
      count: stats.needsReview,
      icon: Clock,
      color: 'text-amber-400',
      bg: 'bg-amber-500/10',
      border: 'border-amber-500/20',
    },
    {
      id: 'rejected',
      filterValue: 'rejected',
      label: 'Failed / Rejected',
      count: stats.failed,
      icon: AlertTriangle,
      color: 'text-red-400',
      bg: 'bg-red-500/10',
      border: 'border-red-500/20',
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-5">
      {cards.map((c) => {
        const Icon = c.icon;
        const isSelected = selectedFilter === c.filterValue && c.filterValue !== null;

        return (
          <button
            key={c.id}
            type="button"
            onClick={() => onSelectFilter && onSelectFilter(isSelected ? null : c.filterValue)}
            className={`summary-card text-left transition-all ${
              isSelected ? 'ring-2 ring-primary border-primary/50 bg-card-hover' : ''
            }`}
          >
            <div className={`summary-icon ${c.border} ${c.bg} ${c.color}`}>
              <Icon className={`size-5 ${c.animateIcon ? 'animate-spin' : ''}`} />
            </div>
            <div>
              <div className="text-2xl font-bold tracking-tight text-text-main">
                {c.count}
              </div>
              <div className="text-xs font-medium text-text-muted mt-0.5">{c.label}</div>
            </div>
          </button>
        );
      })}
    </div>
  );
};
