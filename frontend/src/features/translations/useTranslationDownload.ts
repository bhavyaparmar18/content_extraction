import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useToast } from '@/components/ui/ToastStack';
import { apiErrorDetails, saveBlob } from '@/lib/api';
import { translationsApi } from './api';
import { translationKeys } from './hooks';
import type { TranslationJob } from './types';

/** The approved translated document, fetched with the reviewer's token; each download is recorded on the job. */
export function useTranslationDownload(job: TranslationJob) {
  const { success, error } = useToast();
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      const version = job.review?.docx_version;
      saveBlob(await translationsApi.exportWord(job.job_id), `${job.job_id}_${job.language}${version ? `_v${version}` : ''}.docx`);
      success('The download is recorded in the job history.', 'Translated document downloaded');
      client.invalidateQueries({ queryKey: translationKeys.job(job.job_id) });
    } catch (e) {
      error([e instanceof Error ? e.message : String(e), ...apiErrorDetails(e).slice(0, 3)].join(' · '), 'Not downloaded');
    } finally {
      setBusy(false);
    }
  };
  return { busy, run };
}
