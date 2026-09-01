import React from 'react';
import { FileText, FileCode, File } from 'lucide-react';
import { clsx } from 'clsx';

interface FileTypeIconProps {
  fileType?: string | null;
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

export const FileTypeIcon: React.FC<FileTypeIconProps> = ({
  fileType,
  className,
  size = 'md',
}) => {
  const type = (fileType || '').toLowerCase().replace(/^\./, '');

  const sizeClass = {
    sm: 'size-4',
    md: 'size-5',
    lg: 'size-7',
  }[size];

  if (type === 'pdf') {
    return (
      <div
        className={clsx(
          'grid place-items-center rounded bg-red-500/10 text-red-400 font-bold border border-red-500/20',
          size === 'sm' ? 'size-6 text-[9px]' : size === 'lg' ? 'size-10 text-xs' : 'size-8 text-[10px]',
          className
        )}
        title="PDF Document"
      >
        PDF
      </div>
    );
  }

  if (type === 'docx' || type === 'doc') {
    return (
      <div
        className={clsx(
          'grid place-items-center rounded bg-blue-500/10 text-blue-400 font-bold border border-blue-500/20',
          size === 'sm' ? 'size-6 text-[9px]' : size === 'lg' ? 'size-10 text-xs' : 'size-8 text-[10px]',
          className
        )}
        title="Word Document"
      >
        DOC
      </div>
    );
  }

  return (
    <div
      className={clsx(
        'grid place-items-center rounded bg-primary/10 text-primary border border-primary/20',
        size === 'sm' ? 'size-6' : size === 'lg' ? 'size-10' : 'size-8',
        className
      )}
    >
      <FileText className={sizeClass} />
    </div>
  );
};
