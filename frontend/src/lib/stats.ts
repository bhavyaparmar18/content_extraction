import { SopRecord, BatchJob } from '@/types';

export interface RepositoryStats {
  totalSops: number;
  completed: number;
  processing: number;
  needsReview: number;
  failed: number;
}

export function calculateRepositoryStats(
  records: SopRecord[] = [],
  activeJob?: BatchJob | null
): RepositoryStats {
  let totalSops = records.length;
  let completed = 0;
  let needsReview = 0;
  let failed = 0;
  let processing = 0;

  for (const rec of records) {
    if (rec.status === 'approved') {
      completed++;
    } else if (rec.status === 'rejected') {
      failed++;
    } else {
      needsReview++;
    }
  }

  if (activeJob) {
    for (const doc of activeJob.documents || []) {
      if (doc.status === 'processing' || doc.status === 'queued') {
        processing++;
      } else if (doc.status === 'failed') {
        failed++;
      }
    }
  }

  return {
    totalSops,
    completed,
    processing,
    needsReview,
    failed,
  };
}
