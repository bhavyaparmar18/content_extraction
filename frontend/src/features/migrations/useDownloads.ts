import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useToast } from '@/components/ui/ToastStack';
import { apiErrorDetails, saveBlob } from '@/lib/api';
import { migrationsApi } from './api';
import { migrationKeys } from './hooks';
import type { MigrationJob } from './types';

/** The job's downloads (final document, review draft, traceability), fetched with the reviewer's token. */
export function useDownloads(job: MigrationJob) {
  const { success, error } = useToast();
  const client = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);

  const run = (what: string, load: () => Promise<Blob>, name: string, after?: () => void) => async () => {
    setBusy(what);
    try {
      saveBlob(await load(), name);
      after?.();
    } catch (e) {
      const details = apiErrorDetails(e);
      error([e instanceof Error ? e.message : String(e), ...details.slice(0, 3)].join(' · '), `${what} not downloaded`);
    } finally {
      setBusy(null);
    }
  };

  return {
    busy,
    final: run('Final document', () => migrationsApi.exportWord(job.job_id), `${job.job_id}_final.docx`, () => {
      success('The export is recorded in the job history and on the SOP.', 'Final document exported');
      client.invalidateQueries({ queryKey: migrationKeys.job(job.job_id) });
    }),
    review: run('Review draft', () => migrationsApi.reviewDocument(job.job_id), `${job.job_id}_review.docx`),
    trace: run('Traceability', () => migrationsApi.traceabilityCsv(job.job_id), `${job.job_id}_traceability.csv`),
  };
}
