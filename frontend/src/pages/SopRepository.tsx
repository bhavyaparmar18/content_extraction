import React, { useState, useMemo } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  UploadCloud,
  LayoutGrid,
  List,
  FileQuestion,
  RefreshCw,
} from 'lucide-react';
import { api } from '@/lib/api';
import { SopRecord, SopStatus, BatchJob } from '@/types';
import { StatCards } from '@/components/ui/StatCards';
import { SearchBar } from '@/components/ui/SearchBar';
import { FilterBar } from '@/components/ui/FilterBar';
import { SopTable } from '@/components/repository/SopTable';
import { SopGrid } from '@/components/repository/SopGrid';
import { UploadSops } from '@/components/repository/UploadSops';
import { JobProgressBanner } from '@/components/repository/JobProgressBanner';
import { ConfirmDialog } from '@/components/ui/ConfirmDialog';
import { useToast } from '@/components/ui/ToastStack';
import { calculateRepositoryStats } from '@/lib/stats';
import { useJobPolling } from '@/lib/useJobPolling';
import { Button } from '@/components/ui/Button';

export const SopRepository: React.FC = () => {
  const queryClient = useQueryClient();
  const { success: toastSuccess, error: toastError } = useToast();

  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<SopStatus | 'all'>('all');
  const [fileTypeFilter, setFileTypeFilter] = useState<'all' | 'pdf' | 'docx'>('all');
  const [viewMode, setViewMode] = useState<'table' | 'grid'>('table');
  const [isUploadOpen, setIsUploadOpen] = useState(false);
  const [sopToDelete, setSopToDelete] = useState<SopRecord | null>(null);

  // Active batch job state
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  // Query SOPs list
  const {
    data: sops = [],
    isLoading,
    isRefetching,
    refetch,
  } = useQuery({
    queryKey: ['sops'],
    queryFn: () => api.getSops({ limit: 1000 }),
    staleTime: 5000,
  });

  // Job Polling Hook
  const { job: activeJob, clearJob } = useJobPolling({
    jobId: activeJobId,
    onComplete: (completedJob) => {
      toastSuccess('Batch extraction completed! Repository updated.', 'Success');
      // Refresh SOPs list exactly once on completion
      queryClient.invalidateQueries({ queryKey: ['sops'] });
    },
    onError: (err) => {
      toastError(`Job polling issue: ${err.message}`);
    },
  });

  // Delete Mutation
  const deleteMutation = useMutation({
    mutationFn: (recordId: number) => api.deleteSop(recordId),
    onSuccess: () => {
      toastSuccess('SOP record and associated data removed.', 'Deleted');
      queryClient.invalidateQueries({ queryKey: ['sops'] });
      setSopToDelete(null);
    },
    onError: (err: any) => {
      toastError(err.message || 'Failed to delete SOP record.');
    },
  });

  // Compute stats
  const stats = useMemo(() => {
    return calculateRepositoryStats(sops, activeJob);
  }, [sops, activeJob]);

  // Filter & search records
  const filteredSops = useMemo(() => {
    return sops.filter((sop) => {
      // Search filter
      if (searchQuery.trim()) {
        const q = searchQuery.toLowerCase();
        const matchesTitle = (sop.document_title || '').toLowerCase().includes(q);
        const matchesName = (sop.document_name || '').toLowerCase().includes(q);
        const matchesNumber = (sop.document_number || '').toLowerCase().includes(q);
        const matchesUid = (sop.document_Uid || '').toLowerCase().includes(q);
        const matchesFile = (sop.source_filename || '').toLowerCase().includes(q);
        if (!matchesTitle && !matchesName && !matchesNumber && !matchesUid && !matchesFile) {
          return false;
        }
      }

      // Status filter
      if (statusFilter !== 'all' && sop.status !== statusFilter) {
        return false;
      }

      // File type filter
      if (fileTypeFilter !== 'all') {
        const ft = (sop.file_type || '').toLowerCase();
        if (ft !== fileTypeFilter) return false;
      }

      return true;
    });
  }, [sops, searchQuery, statusFilter, fileTypeFilter]);

  const handleUploadSuccess = (job: BatchJob) => {
    setActiveJobId(job.job_id);
  };

  return (
    <div className="content-pane space-y-6">
      {/* Page Header */}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold uppercase tracking-widest text-primary">
              Standard Operating Procedures
            </span>
            {isRefetching && (
              <RefreshCw className="size-3 text-text-muted animate-spin" />
            )}
          </div>
          <h1 className="page-title mt-1">SOP Repository</h1>
          <p className="page-description">
            Ingest, extract, review, translate, and migrate regulated procedure documents
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="primary"
            onClick={() => setIsUploadOpen(true)}
            leftIcon={<UploadCloud className="size-4" />}
          >
            Upload SOPs
          </Button>
        </div>
      </div>

      {/* KPI Cards */}
      <StatCards
        stats={stats}
        selectedFilter={statusFilter === 'all' ? null : statusFilter}
        onSelectFilter={(filterVal) => {
          setStatusFilter(filterVal ? (filterVal as SopStatus) : 'all');
        }}
      />

      {/* Batch Job Progress Banner */}
      <JobProgressBanner
        job={activeJob}
        onDismiss={() => {
          clearJob();
          setActiveJobId(null);
        }}
      />

      {/* Search & Filter Toolbar */}
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between pt-2">
        <SearchBar
          value={searchQuery}
          onChange={setSearchQuery}
          className="w-full md:max-w-md"
        />

        <div className="flex flex-wrap items-center justify-between gap-3 md:justify-end">
          <FilterBar
            statusFilter={statusFilter}
            fileTypeFilter={fileTypeFilter}
            onStatusChange={setStatusFilter}
            onFileTypeChange={setFileTypeFilter}
            onReset={() => {
              setStatusFilter('all');
              setFileTypeFilter('all');
              setSearchQuery('');
            }}
          />

          {/* Table / Grid Switch */}
          <div className="flex items-center rounded-lg border border-border bg-black/10 p-0.5">
            <button
              type="button"
              onClick={() => setViewMode('table')}
              className={`btn-icon size-7 rounded ${
                viewMode === 'table' ? 'bg-primary/20 text-primary' : 'text-text-muted hover:text-text-main'
              }`}
              title="Table View"
            >
              <List className="size-4" />
            </button>
            <button
              type="button"
              onClick={() => setViewMode('grid')}
              className={`btn-icon size-7 rounded ${
                viewMode === 'grid' ? 'bg-primary/20 text-primary' : 'text-text-muted hover:text-text-main'
              }`}
              title="Grid View"
            >
              <LayoutGrid className="size-4" />
            </button>
          </div>
        </div>
      </div>

      {/* Results Content */}
      {isLoading ? (
        <div className="dashboard-card flex flex-col items-center justify-center p-12 text-center">
          <RefreshCw className="size-8 text-primary animate-spin mb-3" />
          <div className="text-sm font-semibold text-text-main">Loading SOP Documents...</div>
          <div className="text-xs text-text-muted mt-1">Retrieving database records</div>
        </div>
      ) : filteredSops.length === 0 ? (
        <div className="dashboard-card flex flex-col items-center justify-center p-12 text-center">
          <div className="grid size-14 place-items-center rounded-full bg-white/5 border border-border text-text-muted mb-4">
            <FileQuestion className="size-7" />
          </div>
          <h3 className="text-base font-semibold text-text-main">No SOP Documents Found</h3>
          <p className="text-xs text-text-muted max-w-sm mt-1 mb-5">
            {searchQuery || statusFilter !== 'all' || fileTypeFilter !== 'all'
              ? 'No documents match your active search and filter criteria.'
              : 'Get started by uploading PDF or DOCX procedure documents for automated structured extraction.'}
          </p>
          {searchQuery || statusFilter !== 'all' || fileTypeFilter !== 'all' ? (
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                setSearchQuery('');
                setStatusFilter('all');
                setFileTypeFilter('all');
              }}
            >
              Clear Filters
            </Button>
          ) : (
            <Button
              variant="primary"
              onClick={() => setIsUploadOpen(true)}
              leftIcon={<UploadCloud className="size-4" />}
            >
              Upload First Batch
            </Button>
          )}
        </div>
      ) : viewMode === 'table' ? (
        <SopTable
          sops={filteredSops}
          onDelete={(sop) => setSopToDelete(sop)}
        />
      ) : (
        <SopGrid
          sops={filteredSops}
          onDelete={(sop) => setSopToDelete(sop)}
        />
      )}

      {/* Upload Dialog */}
      <UploadSops
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onUploadSuccess={handleUploadSuccess}
      />

      {/* Delete Confirmation Modal */}
      <ConfirmDialog
        isOpen={sopToDelete !== null}
        title="Delete SOP Document"
        message={`Are you sure you want to delete "${sopToDelete?.document_title || sopToDelete?.document_Uid}"? Sibling versions will be retained, but deleting the last version cleans all extracted assets.`}
        confirmLabel="Delete SOP"
        isDangerous
        isLoading={deleteMutation.isPending}
        onConfirm={() => {
          if (sopToDelete) {
            deleteMutation.mutate(sopToDelete.id);
          }
        }}
        onCancel={() => setSopToDelete(null)}
      />
    </div>
  );
};
