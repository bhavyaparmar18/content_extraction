import { FolderOpen, Upload } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ConfirmDialog } from '../components/ConfirmDialog'
import { FilterBar } from '../components/FilterBar'
import { JobProgressBanner } from '../components/JobProgressBanner'
import { Layout } from '../components/Layout'
import { SearchBar } from '../components/SearchBar'
import { SopList } from '../components/SopList'
import { StatCards } from '../components/StatCards'
import { ThemeToggle } from '../components/ThemeToggle'
import type { ToastMessage } from '../components/Toast'
import { ToastStack } from '../components/Toast'
import { Button } from '../components/ui/Button'
import { UploadSops } from '../components/UploadSops'
import { ApiError, deleteSop, listSops } from '../lib/api'
import { displayTitle } from '../lib/sopDisplay'
import { computeStats } from '../lib/stats'
import { useJobPolling } from '../lib/useJobPolling'
import type { BatchJob, FileTypeFilter, SopRecord, StatusFilter, ViewMode } from '../types'

function matchesSearch(sop: SopRecord, query: string): boolean {
  const haystack = [sop.document_title, sop.document_name, sop.document_number, sop.source_filename]
    .filter(Boolean)
    .join(' ')
    .toLowerCase()
  return haystack.includes(query.toLowerCase())
}

export function SopRepository() {
  const [sops, setSops] = useState<SopRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [loadError, setLoadError] = useState<string | null>(null)

  const [search, setSearch] = useState('')
  const [viewMode, setViewMode] = useState<ViewMode>('list')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [typeFilter, setTypeFilter] = useState<FileTypeFilter>('all')

  const [uploadOpen, setUploadOpen] = useState(false)
  const [activeJobId, setActiveJobId] = useState<string | null>(null)
  const [bannerDismissed, setBannerDismissed] = useState(false)

  const [deleteTarget, setDeleteTarget] = useState<SopRecord | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [toasts, setToasts] = useState<ToastMessage[]>([])
  const toastIdRef = useRef(0)

  const fetchSops = useCallback(async () => {
    setLoading(true)
    setLoadError(null)
    try {
      const response = await listSops()
      setSops(response.records)
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : 'Failed to load SOPs.')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchSops()
  }, [fetchSops])

  // Once the active job reaches a terminal state, the newly extracted SOPs
  // are already persisted server-side — refresh the list to pick them up.
  const handleJobSettled = useCallback(() => {
    fetchSops()
  }, [fetchSops])

  const activeJob = useJobPolling(activeJobId, handleJobSettled)

  function handleUploaded(job: BatchJob) {
    setActiveJobId(job.job_id)
    setBannerDismissed(false)
  }

  const pushToast = useCallback((kind: ToastMessage['kind'], text: string) => {
    toastIdRef.current += 1
    setToasts((prev) => [...prev, { id: toastIdRef.current, kind, text }])
  }, [])

  const dismissToast = useCallback((id: number) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id))
  }, [])

  async function handleConfirmDelete() {
    if (!deleteTarget) return
    setDeleting(true)
    try {
      await deleteSop(deleteTarget.id)
      setSops((prev) => prev.filter((sop) => sop.id !== deleteTarget.id))
      pushToast('success', `Deleted "${displayTitle(deleteTarget)}".`)
      setDeleteTarget(null)
    } catch (err) {
      pushToast('error', err instanceof ApiError ? err.message : 'Failed to delete SOP. Please try again.')
    } finally {
      setDeleting(false)
    }
  }

  const stats = useMemo(() => computeStats(sops, activeJob), [sops, activeJob])

  const filteredSops = useMemo(() => {
    return sops.filter((sop) => {
      if (statusFilter !== 'all' && sop.status !== statusFilter) return false
      if (typeFilter !== 'all' && sop.file_type?.toLowerCase() !== typeFilter) return false
      if (search.trim() && !matchesSearch(sop, search)) return false
      return true
    })
  }, [sops, search, statusFilter, typeFilter])

  const hasActiveFilters = search.trim().length > 0 || statusFilter !== 'all' || typeFilter !== 'all'

  return (
    <Layout>
      <header className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          <div className="mt-1 flex h-11 w-11 flex-none items-center justify-center rounded-xl bg-[var(--primary)]/12 text-[var(--primary)]">
            <FolderOpen size={22} />
          </div>
          <div>
            <div className="text-[11px] uppercase tracking-[0.2em] text-[var(--text-muted)]">GP-DAT</div>
            <h1 className="mt-1 text-3xl font-semibold tracking-tight">SOP Repository</h1>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Manage and monitor all SOPs in your repository
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Button onClick={() => setUploadOpen(true)}>
            <Upload size={16} />
            Upload SOPs
          </Button>
        </div>
      </header>

      <StatCards stats={stats} />

      {activeJob && !bannerDismissed && (
        <JobProgressBanner job={activeJob} onDismiss={() => setBannerDismissed(true)} />
      )}

      <SearchBar value={search} onChange={setSearch} viewMode={viewMode} onViewModeChange={setViewMode} />

      <FilterBar
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
        typeFilter={typeFilter}
        onTypeFilterChange={setTypeFilter}
      />

      <div className="mt-4 dashboard-card overflow-hidden">
        <SopList
          records={filteredSops}
          viewMode={viewMode}
          loading={loading}
          error={loadError}
          hasActiveFilters={hasActiveFilters}
          onDelete={setDeleteTarget}
        />
      </div>

      <UploadSops open={uploadOpen} onClose={() => setUploadOpen(false)} onUploaded={handleUploaded} />

      <ConfirmDialog
        open={deleteTarget !== null}
        title="Delete this SOP?"
        description={
          deleteTarget
            ? `"${displayTitle(deleteTarget)}" will be permanently removed. If no other version of this document remains, its files will be deleted too.`
            : ''
        }
        confirmLabel="Delete"
        busy={deleting}
        onConfirm={handleConfirmDelete}
        onCancel={() => !deleting && setDeleteTarget(null)}
      />

      <ToastStack toasts={toasts} onDismiss={dismissToast} />
    </Layout>
  )
}
