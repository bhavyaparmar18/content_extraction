import { useEffect, useRef, useState } from 'react'
import { getJob } from './api'
import type { BatchJob } from '../types'

const POLL_INTERVAL_MS = 1500

/**
 * Polls `GET /jobs/{jobId}` until the batch job reaches a terminal state
 * (`completed` or `failed`), then invokes `onSettled` exactly once so the
 * caller can refresh derived data (e.g. re-fetch the SOP list).
 */
export function useJobPolling(jobId: string | null, onSettled: () => void): BatchJob | null {
  const [job, setJob] = useState<BatchJob | null>(null)
  const onSettledRef = useRef(onSettled)

  // Keep the ref pointing at the latest callback without re-triggering the
  // polling effect below (which should only restart when jobId changes).
  useEffect(() => {
    onSettledRef.current = onSettled
  }, [onSettled])

  useEffect(() => {
    if (!jobId) {
      setJob(null)
      return
    }

    const currentJobId = jobId
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined

    async function poll() {
      try {
        const latest = await getJob(currentJobId)
        if (cancelled) return
        setJob(latest)

        const isTerminal = latest.status === 'completed' || latest.status === 'failed'
        if (isTerminal) {
          onSettledRef.current()
        } else {
          timer = setTimeout(poll, POLL_INTERVAL_MS)
        }
      } catch {
        // A transient poll failure shouldn't kill the whole flow — retry.
        if (!cancelled) timer = setTimeout(poll, POLL_INTERVAL_MS)
      }
    }

    poll()

    return () => {
      cancelled = true
      if (timer) clearTimeout(timer)
    }
  }, [jobId])

  return job
}
