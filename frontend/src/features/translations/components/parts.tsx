import React from 'react';
import { Loader2, X } from 'lucide-react';
import { clsx } from 'clsx';
import { TONE_CLASSES } from '@/features/migrations/status';
import { translationStatusInfo } from '../status';
import type { TranslationStatus } from '../types';

/** A small rounded status label in one of the shared tones. */
export const ToneChip: React.FC<{ tone: keyof typeof TONE_CLASSES; children: React.ReactNode; className?: string; title?: string }> = ({
  tone,
  children,
  className,
  title,
}) => (
  <span title={title} className={clsx('inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium', TONE_CLASSES[tone], className)}>
    {children}
  </span>
);

export const TranslationStatusPill: React.FC<{ status: TranslationStatus; running?: boolean; className?: string }> = ({ status, running, className }) => {
  const info = translationStatusInfo(status);
  return (
    <span className={clsx('inline-flex items-center gap-1.5 whitespace-nowrap rounded-full border px-2.5 py-0.5 text-[11px] font-medium', info.classes, className)}>
      {running || info.tone === 'working' ? <Loader2 className="size-3 animate-spin" /> : <span className="size-1.5 rounded-full bg-current" />}
      {info.label}
    </span>
  );
};

/** "German · de-DE". */
export const LanguageLabel: React.FC<{ code: string; name?: string; className?: string }> = ({ code, name, className }) => (
  <span className={clsx('whitespace-nowrap', className)}>
    {name && name !== code ? <span className="text-text-main">{name}</span> : null}
    <span className={clsx('font-mono text-[11px] text-text-muted', name && name !== code && 'ml-1.5')}>{code}</span>
  </span>
);

/** A modal shell: dimmed backdrop, card, header with a close button, body, footer. */
export const Modal: React.FC<{
  open: boolean;
  title: React.ReactNode;
  icon?: React.ReactNode;
  onClose: () => void;
  footer?: React.ReactNode;
  wide?: boolean;
  children: React.ReactNode;
}> = ({ open, title, icon, onClose, footer, wide, children }) => {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" onMouseDown={onClose}>
      <div className={clsx('dashboard-card flex max-h-[90vh] w-full flex-col', wide ? 'max-w-2xl' : 'max-w-lg')} onMouseDown={(e) => e.stopPropagation()}>
        <div className="panel-header shrink-0">
          <div className="flex items-center gap-2 text-sm font-semibold text-text-main">
            {icon}
            {title}
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="grid size-7 place-items-center rounded text-text-muted hover:bg-white/5">
            <X className="size-4" />
          </button>
        </div>
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-5">{children}</div>
        {footer && <div className="flex shrink-0 justify-end gap-2 border-t border-border px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
};

/** The problems an API error carries (field errors), under its message. */
export const ErrorPanel: React.FC<{ error: Error | null | undefined; details?: string[] }> = ({ error, details = [] }) => {
  if (!error) return null;
  return (
    <div className="error-panel text-xs">
      <div className="font-medium text-danger">{error.message}</div>
      {details.length > 0 && (
        <ul className="mt-1.5 max-h-40 list-disc space-y-0.5 overflow-y-auto pl-4 text-text-muted">
          {details.map((d, i) => <li key={i}>{d}</li>)}
        </ul>
      )}
    </div>
  );
};
