import { useState, useEffect, useRef } from 'react';
import { BatchJob, JobStatus } from '@/types';
import { api } from '@/lib/api';

interface UseJobPollingOptions {
  jobId: string | null;
  pollIntervalMs?: number;
  onComplete?: (job: BatchJob) => void;
  onError?: (err: Error) => void;
}

export function useJobPolling({
  jobId,
  pollIntervalMs = 1500,
  onComplete,
  onError,
}: UseJobPollingOptions) {
  const [job, setJob] = useState<BatchJob | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const completedRef = useRef(false);

  useEffect(() => {
    if (!jobId) {
      setJob(null);
      setIsPolling(false);
      completedRef.current = false;
      return;
    }

    let isMounted = true;
    let timerId: NodeJS.Timeout | null = null;
    completedRef.current = false;
    setIsPolling(true);
    setError(null);

    const poll = async () => {
      try {
        const data = await api.getJob(jobId);
        if (!isMounted) return;

        setJob(data);

        if (data.status === 'completed' || data.status === 'failed') {
          setIsPolling(false);
          if (!completedRef.current) {
            completedRef.current = true;
            onComplete?.(data);
          }
          return; // Stop polling
        }

        // Schedule next poll
        timerId = setTimeout(poll, pollIntervalMs);
      } catch (err: any) {
        if (!isMounted) return;
        const e = err instanceof Error ? err : new Error(String(err));
        setError(e);
        onError?.(e);
        // Retry on failure
        timerId = setTimeout(poll, pollIntervalMs * 2);
      }
    };

    poll();

    return () => {
      isMounted = false;
      if (timerId) clearTimeout(timerId);
    };
  }, [jobId, pollIntervalMs]);

  const clearJob = () => {
    setJob(null);
    setIsPolling(false);
  };

  return {
    job,
    isPolling,
    error,
    clearJob,
  };
}
