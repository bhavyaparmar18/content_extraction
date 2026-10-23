import React, { useEffect } from 'react';
import { clsx } from 'clsx';

/** The view switch at the top of a context pane. */
export const PaneTabs: React.FC<{
  value: string;
  onChange: (value: string) => void;
  tabs: { id: string; label: string }[];
  extra?: React.ReactNode;
}> = ({ value, onChange, tabs, extra }) => (
  <div className="flex h-9 shrink-0 items-center gap-1 border-b border-border px-2">
    {tabs.map((tab) => (
      <button
        key={tab.id}
        type="button"
        onClick={() => onChange(tab.id)}
        className={clsx('pane-tab shrink-0 whitespace-nowrap', value === tab.id && 'pane-tab-active')}
      >
        {tab.label}
      </button>
    ))}
    {extra && <div className="ml-auto min-w-0 truncate pl-2">{extra}</div>}
  </div>
);

/** Scrolls the first element matching ``selector`` into the middle of ``container`` when the selector changes. */
export const ScrollToFocus: React.FC<{ container: React.RefObject<HTMLElement | null>; selector: string | null }> = ({
  container,
  selector,
}) => {
  useEffect(() => {
    if (!selector) return;
    const el = container.current?.querySelector<HTMLElement>(selector);
    el?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  }, [container, selector]);
  return null;
};
