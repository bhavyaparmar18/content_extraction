import React from 'react';
import { Filter, FileType, CheckCircle } from 'lucide-react';
import { SopStatus } from '@/types';

interface FilterBarProps {
  statusFilter: SopStatus | 'all';
  fileTypeFilter: 'all' | 'pdf' | 'docx';
  onStatusChange: (status: SopStatus | 'all') => void;
  onFileTypeChange: (type: 'all' | 'pdf' | 'docx') => void;
  onReset?: () => void;
}

export const FilterBar: React.FC<FilterBarProps> = ({
  statusFilter,
  fileTypeFilter,
  onStatusChange,
  onFileTypeChange,
  onReset,
}) => {
  const statuses: Array<{ value: SopStatus | 'all'; label: string }> = [
    { value: 'all', label: 'All Status' },
    { value: 'in_review', label: 'In Review' },
    { value: 'approved', label: 'Approved' },
    { value: 'rejected', label: 'Rejected' },
  ];

  const fileTypes: Array<{ value: 'all' | 'pdf' | 'docx'; label: string }> = [
    { value: 'all', label: 'All Formats' },
    { value: 'pdf', label: 'PDF' },
    { value: 'docx', label: 'DOCX' },
  ];

  const hasActiveFilters = statusFilter !== 'all' || fileTypeFilter !== 'all';

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-1 text-xs font-medium text-text-muted mr-1">
        <Filter className="size-3.5" />
        <span>Filters:</span>
      </div>

      {/* Status Chips */}
      <div className="flex items-center gap-1.5">
        {statuses.map((s) => (
          <button
            key={s.value}
            type="button"
            onClick={() => onStatusChange(s.value)}
            className={`filter-chip ${statusFilter === s.value ? 'filter-chip-active' : ''}`}
          >
            {s.label}
          </button>
        ))}
      </div>

      <div className="h-4 w-px bg-border mx-1" />

      {/* File Type Chips */}
      <div className="flex items-center gap-1.5">
        {fileTypes.map((ft) => (
          <button
            key={ft.value}
            type="button"
            onClick={() => onFileTypeChange(ft.value)}
            className={`filter-chip ${fileTypeFilter === ft.value ? 'filter-chip-active' : ''}`}
          >
            {ft.label}
          </button>
        ))}
      </div>

      {hasActiveFilters && onReset && (
        <button
          type="button"
          onClick={onReset}
          className="text-xs text-primary hover:underline ml-2"
        >
          Reset
        </button>
      )}
    </div>
  );
};
