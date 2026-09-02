import type { BatchJob, SopRecord } from '../types'

export interface StatCardData {
  key: string
  label: string
  value: number
  sublabel: string
}

/**
 * Derives the repository KPI cards from two independent sources:
 *  - `sops`: the persisted, already-completed extraction records (GET /sops).
 *  - `activeJob`: the batch job for the *current* upload session, if any is
 *    in flight. The backend does not persist job history, so "Processing"
 *    and "Failed" only reflect documents from this session's active job —
 *    they reset once the page is reloaded, by design.
 */
export function computeStats(sops: SopRecord[], activeJob: BatchJob | null): StatCardData[] {
  const completed = sops.length
  const needsReview = sops.filter((s) => s.status === 'in_review').length

  const liveDocs = activeJob?.documents ?? []
  const processing = liveDocs.filter((d) => d.status === 'queued' || d.status === 'processing').length
  const failed = liveDocs.filter((d) => d.status === 'failed').length + (activeJob?.rejected_files.length ?? 0)

  const total = completed + processing + failed
  const pct = (value: number) => (total === 0 ? '0%' : `${Math.round((value / total) * 100)}%`)

  return [
    { key: 'total', label: 'Total SOPs', value: total, sublabel: 'All documents' },
    { key: 'completed', label: 'Completed', value: completed, sublabel: `${pct(completed)} of total` },
    { key: 'processing', label: 'Processing', value: processing, sublabel: `${pct(processing)} of total` },
    { key: 'needs_review', label: 'Needs Review', value: needsReview, sublabel: `${pct(needsReview)} of total` },
    { key: 'failed', label: 'Failed', value: failed, sublabel: `${pct(failed)} of total` },
  ]
}
