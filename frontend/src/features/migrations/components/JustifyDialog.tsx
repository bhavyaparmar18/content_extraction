import React, { useEffect, useState } from 'react';
import { Button } from '@/components/ui/Button';

interface JustifyDialogProps {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  placeholder?: string;
  busy?: boolean;
  onConfirm: (note: string) => void;
  onCancel: () => void;
}

/** Asks for a required note (omitting a section, resolving an issue, accepting a gap). */
export const JustifyDialog: React.FC<JustifyDialogProps> = ({ open, ...props }) => (open ? <Dialog {...props} /> : null);

/** Mounted only while open, so every opening starts with an empty note. */
const Dialog: React.FC<Omit<JustifyDialogProps, 'open'>> = ({
  title,
  description,
  confirmLabel = 'Confirm',
  placeholder = 'Reason (kept in the audit trail)',
  busy,
  onConfirm,
  onCancel,
}) => {
  const [note, setNote] = useState('');

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onCancel();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onCancel]);

  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/50 p-4" onMouseDown={onCancel}>
      <form
        className="dashboard-card w-full max-w-md p-5"
        onMouseDown={(e) => e.stopPropagation()}
        onSubmit={(e) => {
          e.preventDefault();
          if (note.trim()) onConfirm(note.trim());
        }}
      >
        <h3 className="text-sm font-semibold text-text-main">{title}</h3>
        <p className="mt-1 text-xs text-text-muted">{description}</p>
        <textarea
          autoFocus
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder={placeholder}
          rows={3}
          maxLength={2000}
          className="field mt-3 h-auto resize-y py-2 text-sm"
        />
        <div className="mt-4 flex justify-end gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button type="submit" variant="primary" size="sm" disabled={!note.trim()} isLoading={busy}>
            {confirmLabel}
          </Button>
        </div>
      </form>
    </div>
  );
};
