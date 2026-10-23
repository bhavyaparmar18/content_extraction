import { useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { migrationsApi } from './api';
import { isWorking } from './status';
import type { Claim, GwpRuleSet, JobStatus, MigrationJob, SectionPlan, SlotPlan, SourceDocument, SourceUnit, TemplateModel } from './types';

export const migrationKeys = {
  all: ['migrations'] as const,
  list: () => [...migrationKeys.all, 'list'] as const,
  job: (jobId: string) => [...migrationKeys.all, 'job', jobId] as const,
  part: (jobId: string, part: string, ...rest: unknown[]) => [...migrationKeys.job(jobId), part, ...rest] as const,
};

const POLL_MS = 2000;

export function useMigrationJobs() {
  return useQuery({
    queryKey: migrationKeys.list(),
    queryFn: () => migrationsApi.list(),
    refetchInterval: (query) => (query.state.data?.some((j) => isWorking(j)) ? POLL_MS * 2 : false),
  });
}

/** The job, polled while the pipeline works on it. */
export function useMigrationJob(jobId: string) {
  return useQuery({
    queryKey: migrationKeys.job(jobId),
    queryFn: () => migrationsApi.get(jobId),
    refetchInterval: (query) => (query.state.data && isWorking(query.state.data) ? POLL_MS : false),
  });
}

/**
 * The job's artifacts are refetched when a new version appears: the key carries the latest version
 * of the artifact kinds the query reads, so polling the job is enough to keep every view current.
 */
function artifactStamp(job: MigrationJob | undefined, kinds: string[]): string {
  if (!job) return '';
  return kinds
    .map((kind) => {
      const refs = job.artifacts.filter((a) => a.kind === kind);
      return `${kind}:${refs.length}:${Math.max(0, ...refs.map((a) => a.version))}`;
    })
    .join('|');
}

export function useSourceModel(jobId: string, job?: MigrationJob) {
  return useQuery({
    queryKey: migrationKeys.part(jobId, 'source_model'),
    queryFn: () => migrationsApi.sourceModel(jobId),
    enabled: !!job?.artifacts.some((a) => a.kind === 'source_model'),
    staleTime: Infinity,
  });
}

export function useTemplateModel(jobId: string, job?: MigrationJob) {
  return useQuery({
    queryKey: migrationKeys.part(jobId, 'template_model'),
    queryFn: () => migrationsApi.templateModel(jobId),
    enabled: !!job?.artifacts.some((a) => a.kind === 'template_model'),
    staleTime: Infinity,
  });
}

export function useSectionPlan(jobId: string, job?: MigrationJob) {
  const stamp = artifactStamp(job, ['section_plan', 'quality_report']);
  const plan = useQuery({
    queryKey: migrationKeys.part(jobId, 'section_plan', stamp),
    queryFn: () => migrationsApi.sectionPlan(jobId),
    enabled: !!job?.artifacts.some((a) => a.kind === 'section_plan'),
  });
  const validation = useQuery({
    queryKey: migrationKeys.part(jobId, 'section_plan_validation', stamp),
    queryFn: () => migrationsApi.sectionPlanValidation(jobId),
    enabled: !!job?.artifacts.some((a) => a.kind === 'quality_report' && a.scope === 'section_plan'),
  });
  return { plan, validation };
}

export function useSlotPlan(jobId: string, job?: MigrationJob) {
  const stamp = artifactStamp(job, ['slot_plan', 'quality_report']);
  const plan = useQuery({
    queryKey: migrationKeys.part(jobId, 'slot_plan', stamp),
    queryFn: () => migrationsApi.slotPlan(jobId),
    enabled: !!job?.artifacts.some((a) => a.kind === 'slot_plan'),
  });
  const validation = useQuery({
    queryKey: migrationKeys.part(jobId, 'slot_plan_validation', stamp),
    queryFn: () => migrationsApi.slotPlanValidation(jobId),
    enabled: !!job?.artifacts.some((a) => a.kind === 'quality_report' && a.scope === 'slot_plan'),
  });
  return { plan, validation };
}

export function useDrafts(jobId: string, job?: MigrationJob) {
  return useQuery({
    queryKey: migrationKeys.part(jobId, 'drafts', artifactStamp(job, ['section_draft'])),
    queryFn: () => migrationsApi.drafts(jobId),
    enabled: !!job?.artifacts.some((a) => a.kind === 'section_draft'),
  });
}

/** The job's latest quality report (any scope: the server returns the newest). */
export function useQualityReport(jobId: string, job?: MigrationJob) {
  return useQuery({
    queryKey: migrationKeys.part(jobId, 'quality', artifactStamp(job, ['quality_report'])),
    queryFn: () => migrationsApi.quality(jobId),
    enabled: !!job?.artifacts.some((a) => a.kind === 'quality_report' && !a.scope),
  });
}

export function useRenderReport(jobId: string, job?: MigrationJob) {
  return useQuery({
    queryKey: migrationKeys.part(jobId, 'render_report', artifactStamp(job, ['render_report'])),
    queryFn: () => migrationsApi.renderReport(jobId),
    enabled: !!job?.artifacts.some((a) => a.kind === 'render_report' && !a.scope),
  });
}

/** The rule set the job runs with (the GWP's rules plus the built-in preservation rules), by rule ID. */
export function useJobRules(jobId: string, job?: MigrationJob) {
  const query = useQuery({
    queryKey: migrationKeys.part(jobId, 'gwp_rules'),
    queryFn: () => migrationsApi.artifact<GwpRuleSet>(jobId, 'gwp_rules'),
    enabled: !!job?.artifacts.some((a) => a.kind === 'gwp_rules'),
    staleTime: Infinity,
  });
  return useMemo(() => new Map(query.data?.rules.map((r) => [r.rule_id, r]) ?? []), [query.data]);
}

export function useAudit(jobId: string, job?: MigrationJob) {
  return useQuery({
    queryKey: migrationKeys.part(jobId, 'audit', job?.status, job?.updated_at, job?.artifacts.length),
    queryFn: () => migrationsApi.audit(jobId),
    enabled: !!job,
  });
}

/** The SOP behind a job (title and file type for the header and the source pane). */
export function useSopRecord(recordId?: number) {
  return useQuery({
    queryKey: ['sop', recordId],
    queryFn: () => api.getSop(recordId!),
    enabled: !!recordId,
    staleTime: 60_000,
  });
}

// ── Lookups ───────────────────────────────────────────────────────────

export interface SourceIndex {
  units: Map<string, SourceUnit>;
  sectionOf: Map<string, string>;
  sections: Map<string, SourceDocument['sections'][number]>;
}

export function useSourceIndex(source?: SourceDocument): SourceIndex {
  return useMemo(() => {
    const units = new Map<string, SourceUnit>();
    const sectionOf = new Map<string, string>();
    const sections = new Map<string, SourceDocument['sections'][number]>();
    source?.sections.forEach((section) => {
      sections.set(section.section_id, section);
      section.units.forEach((unit) => {
        units.set(unit.unit_id, unit);
        sectionOf.set(unit.unit_id, section.section_id);
      });
    });
    return { units, sectionOf, sections };
  }, [source]);
}

export function useTemplateIndex(template?: TemplateModel) {
  return useMemo(() => {
    const sections = new Map(template?.sections.map((s) => [s.section_id, s]) ?? []);
    const slots = new Map(template?.sections.flatMap((s) => s.slots.map((slot) => [slot.slot_id, slot] as const)) ?? []);
    return { sections, slots };
  }, [template]);
}

// ── Mutations ─────────────────────────────────────────────────────────

/** Every mutation refreshes the job; the artifact queries follow from its new artifact versions. */
export function useJobMutations(jobId: string) {
  const client = useQueryClient();
  const refresh = (job?: MigrationJob) => {
    if (job && 'job_id' in job && 'artifacts' in job) client.setQueryData(migrationKeys.job(jobId), job);
    client.invalidateQueries({ queryKey: migrationKeys.job(jobId) });
    client.invalidateQueries({ queryKey: migrationKeys.list() });
  };
  const onSuccess = (result: unknown) => refresh(result as MigrationJob);

  return {
    cancel: useMutation({ mutationFn: () => migrationsApi.cancel(jobId), onSuccess }),
    retry: useMutation({ mutationFn: (from?: JobStatus) => migrationsApi.retry(jobId, from), onSuccess }),
    saveSectionPlan: useMutation({ mutationFn: (plan: SectionPlan) => migrationsApi.saveSectionPlan(jobId, plan), onSuccess: () => refresh() }),
    approveSectionPlan: useMutation({ mutationFn: () => migrationsApi.approveSectionPlan(jobId), onSuccess }),
    saveSlotPlan: useMutation({ mutationFn: (plan: SlotPlan) => migrationsApi.saveSlotPlan(jobId, plan), onSuccess: () => refresh() }),
    approveSlotPlan: useMutation({ mutationFn: () => migrationsApi.approveSlotPlan(jobId), onSuccess }),
    saveSlot: useMutation({
      mutationFn: (v: { sectionId: string; slotId: string; claims: Claim[] }) =>
        migrationsApi.saveSlot(jobId, v.sectionId, v.slotId, v.claims),
      onSuccess: () => refresh(),
    }),
    resolveIssue: useMutation({
      mutationFn: (v: { issueId: string; note: string }) => migrationsApi.resolveIssue(jobId, v.issueId, v.note),
      onSuccess: () => refresh(),
    }),
  };
}
