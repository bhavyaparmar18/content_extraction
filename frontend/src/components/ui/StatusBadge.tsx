import React from 'react';
import { clsx } from 'clsx';
import { getStatusConfig } from '@/lib/sopDisplay';
import { SopStatus } from '@/types';

interface StatusBadgeProps {
  status?: SopStatus | string;
  className?: string;
  size?: 'sm' | 'md';
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  className,
  size = 'md',
}) => {
  const config = getStatusConfig(status);

  return (
    <span
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full border font-medium uppercase tracking-wider',
        config.bgClass,
        config.textClass,
        config.borderClass,
        size === 'sm' ? 'px-2 py-0.5 text-[10px]' : 'px-2.5 py-1 text-xs',
        className
      )}
    >
      <span className={clsx('size-1.5 rounded-full shrink-0', config.dotClass)} />
      {config.label}
    </span>
  );
};
