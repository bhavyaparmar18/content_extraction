import { useState, useEffect, useRef, useCallback } from 'react';

export type SaveStatus = 'idle' | 'unsaved' | 'saving' | 'saved' | 'error' | 'conflict';

interface UseAutosaveOptions<T> {
  data: T;
  onSave: (data: T) => Promise<void>;
  delayMs?: number;
  enabled?: boolean;
}

export function useAutosave<T>({
  data,
  onSave,
  delayMs = 800,
  enabled = true,
}: UseAutosaveOptions<T>) {
  const [status, setStatus] = useState<SaveStatus>('idle');
  const [lastSaved, setLastSaved] = useState<Date | null>(null);
  const [error, setError] = useState<Error | null>(null);

  const dataRef = useRef(data);
  const isFirstRender = useRef(true);
  const timerRef = useRef<NodeJS.Timeout | null>(null);

  dataRef.current = data;

  const performSave = useCallback(async () => {
    if (!enabled) return;
    setStatus('saving');
    setError(null);
    try {
      await onSave(dataRef.current);
      setStatus('saved');
      setLastSaved(new Date());
    } catch (err: any) {
      if (err?.status === 409) {
        setStatus('conflict');
      } else {
        setStatus('error');
      }
      setError(err instanceof Error ? err : new Error(String(err)));
    }
  }, [enabled, onSave]);

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }

    if (!enabled) return;

    setStatus('unsaved');

    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }

    timerRef.current = setTimeout(() => {
      performSave();
    }, delayMs);

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [data, delayMs, enabled, performSave]);

  const saveImmediately = useCallback(async () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }
    await performSave();
  }, [performSave]);

  return {
    status,
    lastSaved,
    error,
    saveImmediately,
  };
}
