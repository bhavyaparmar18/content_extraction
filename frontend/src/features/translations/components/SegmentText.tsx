import React from 'react';
import { clsx } from 'clsx';
import { formattedRuns, tokenize } from '../markers';
import { CHIP_CLASS, chipLook, runColour } from '../chips';

/** A segment's text with its markers as chips and formatted runs underlined. */
export const SegmentText: React.FC<{ text?: string; cells: boolean; xref?: boolean; className?: string; empty?: React.ReactNode }> = ({
  text,
  cells,
  xref,
  className,
  empty,
}) => {
  if (!text) return <span className={clsx('italic text-text-muted', className)}>{empty ?? 'No translation'}</span>;
  const parts = tokenize(text, cells);
  const runs = formattedRuns(parts);
  return (
    <span className={clsx('whitespace-pre-wrap break-words', className)}>
      {parts.map((p, i) => {
        if (p.type === 'text') {
          const k = runs.get(i);
          return k ? <span key={i} className={clsx('underline decoration-2 underline-offset-2', runColour(k))}>{p.text}</span> : <React.Fragment key={i}>{p.text}</React.Fragment>;
        }
        if (p.type === 'break') return <br key={i} />;
        const look = chipLook(p, xref);
        return <span key={i} title={look.title} className={clsx(CHIP_CLASS, look.className)}>{look.label}</span>;
      })}
    </span>
  );
};
