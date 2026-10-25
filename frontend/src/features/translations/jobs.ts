import type { MigrationJobRow } from '@/features/migrations/types';
import type { TranslationJobRow } from './types';

/** Migration job id → the title of its SOP (translation rows name only their migration). */
export function jobSopTitles(migrations: Pick<MigrationJobRow, 'job_id' | 'sop_record_id'>[], sopTitles: Map<number, string>): Map<string, string> {
  return new Map(
    migrations.map((m) => [m.job_id, sopTitles.get(m.sop_record_id) ?? `SOP #${m.sop_record_id}`] as const),
  );
}

/** The translation jobs of each migration, newest first (the list is already newest first). */
export function jobsByMigration(jobs: TranslationJobRow[]): Map<string, TranslationJobRow[]> {
  const out = new Map<string, TranslationJobRow[]>();
  jobs.forEach((j) => out.set(j.migration_job_id, [...(out.get(j.migration_job_id) ?? []), j]));
  return out;
}
