import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { translationsApi, type GlossaryUpload, type LanguageTemplateUpload } from './api';
import { isTranslationWorking } from './status';
import type {
  GlossaryEntry,
  GlossaryStatus,
  LanguageCode,
  LanguageTemplateStatus,
  ReplaceRequest,
  TranslationArtifactKind,
  TranslationJob,
  TranslationStatus,
} from './types';

export const translationKeys = {
  all: ['translations'] as const,
  languages: () => [...translationKeys.all, 'languages'] as const,
  list: (filter: object = {}) => [...translationKeys.all, 'list', filter] as const,
  lists: () => [...translationKeys.all, 'list'] as const,
  job: (jobId: string) => [...translationKeys.all, 'job', jobId] as const,
  part: (jobId: string, part: string, ...rest: unknown[]) => [...translationKeys.job(jobId), part, ...rest] as const,
  glossaries: (filter: object = {}) => [...translationKeys.all, 'glossaries', filter] as const,
  glossaryEntries: (id: string, version?: number) => [...translationKeys.all, 'glossary-entries', id, version] as const,
  templates: (filter: object = {}) => [...translationKeys.all, 'language-templates', filter] as const,
  template: (id: string, version?: number) => [...translationKeys.all, 'language-template', id, version] as const,
};

const POLL_MS = 2000;

/**
 * The latest version of an artifact kind (and scope, or any scope with ``'*'``): artifact queries carry it in their
 * key, so polling the job is enough to keep every view current.
 */
export function artifactStamp(job: TranslationJob | undefined, kind: TranslationArtifactKind, scope?: string): string {
  if (!job) return '';
  const refs = job.artifacts.filter((a) => a.kind === kind && (scope === '*' || a.scope === scope));
  return `${kind}:${scope ?? ''}:${refs.length}:${Math.max(0, ...refs.map((a) => a.version))}`;
}

const has = (job: TranslationJob | undefined, kind: TranslationArtifactKind, scope?: string) =>
  !!job?.artifacts.some((a) => a.kind === kind && (scope === '*' || a.scope === scope));

export function useLanguages() {
  return useQuery({ queryKey: translationKeys.languages(), queryFn: () => translationsApi.languages(), staleTime: Infinity });
}

/** Language names by code ("de-DE" → "German"), with the code itself while loading. */
export function useLanguageNames() {
  const languages = useLanguages();
  const names = new Map((languages.data ?? []).map((l) => [l.code, l.name] as const));
  return (code: string) => names.get(code as LanguageCode) ?? code;
}

// ── Jobs ──────────────────────────────────────────────────────────────

export function useTranslationJobs(filter: { migration_job_id?: string; language?: LanguageCode; status?: TranslationStatus } = {}, enabled = true) {
  return useQuery({
    queryKey: translationKeys.list(filter),
    queryFn: () => translationsApi.list(filter),
    enabled,
    refetchInterval: (query) => (query.state.data?.some((j) => isTranslationWorking(j)) ? POLL_MS * 2 : false),
  });
}

/** The job, polled while the pipeline works on it. */
export function useTranslationJob(jobId: string) {
  return useQuery({
    queryKey: translationKeys.job(jobId),
    queryFn: () => translationsApi.get(jobId),
    refetchInterval: (query) => (query.state.data && isTranslationWorking(query.state.data) ? POLL_MS : false),
  });
}

export function useSegments(job?: TranslationJob) {
  const jobId = job?.job_id ?? '';
  return useQuery({
    queryKey: translationKeys.part(jobId, 'segments', artifactStamp(job, 'segments'), artifactStamp(job, 'translation', '*')),
    queryFn: () => translationsApi.segments(jobId),
    enabled: has(job, 'segments'),
    placeholderData: (previous) => previous, // keep the grid while a new version loads
  });
}

export function useTranslationValidation(job?: TranslationJob) {
  const jobId = job?.job_id ?? '';
  return useQuery({
    queryKey: translationKeys.part(jobId, 'validation', artifactStamp(job, 'quality_report', 'translation')),
    queryFn: () => translationsApi.validation(jobId),
    enabled: has(job, 'quality_report', 'translation'),
    placeholderData: (previous) => previous,
  });
}

export function useTranslationRenderReport(job?: TranslationJob) {
  const jobId = job?.job_id ?? '';
  return useQuery({
    queryKey: translationKeys.part(jobId, 'render_report', artifactStamp(job, 'render_report', 'translated')),
    queryFn: () => translationsApi.renderReport(jobId),
    enabled: has(job, 'render_report', 'translated'),
  });
}

export function useTranslationAudit(job?: TranslationJob) {
  const jobId = job?.job_id ?? '';
  return useQuery({
    queryKey: translationKeys.part(jobId, 'audit', job?.status, job?.updated_at, job?.artifacts.length),
    queryFn: () => translationsApi.audit(jobId),
    enabled: !!job,
  });
}

/** The job's glossary snapshot (none: free translation). */
export function useJobGlossary(job?: TranslationJob) {
  const jobId = job?.job_id ?? '';
  return useQuery({
    queryKey: translationKeys.part(jobId, 'glossary'),
    queryFn: () => translationsApi.jobGlossary(jobId),
    enabled: !!job?.glossary_id && has(job, 'glossary'),
    staleTime: Infinity,
  });
}

/** The document terms as agreed (a replace of every occurrence can agree a new one). */
export function useJobTerms(job?: TranslationJob) {
  const jobId = job?.job_id ?? '';
  return useQuery({
    queryKey: translationKeys.part(jobId, 'terms', artifactStamp(job, 'glossary', 'terms')),
    queryFn: () => translationsApi.jobTerms(jobId),
    enabled: has(job, 'glossary', 'terms'),
  });
}

/** Every job action refreshes the job; the artifact queries follow from its new artifact versions. */
export function useTranslationMutations(jobId: string) {
  const client = useQueryClient();
  const refresh = (job?: TranslationJob) => {
    if (job && 'job_id' in job && 'artifacts' in job) client.setQueryData(translationKeys.job(jobId), job);
    client.invalidateQueries({ queryKey: translationKeys.job(jobId) });
    client.invalidateQueries({ queryKey: translationKeys.lists() });
  };
  const onSuccess = (result: unknown) => refresh(result as TranslationJob);

  return {
    cancel: useMutation({ mutationFn: () => translationsApi.cancel(jobId), onSuccess }),
    retry: useMutation({ mutationFn: (from?: TranslationStatus) => translationsApi.retry(jobId, from), onSuccess }),
    render: useMutation({ mutationFn: () => translationsApi.render(jobId), onSuccess }),
    approve: useMutation({ mutationFn: (note?: string) => translationsApi.approve(jobId, note), onSuccess }),
    editSegment: useMutation({
      mutationFn: (v: { segmentId: string; text: string; applyTo: 'same_text' | 'this' }) =>
        translationsApi.editSegment(jobId, v.segmentId, v.text, v.applyTo),
      onSuccess: () => refresh(),
    }),
    replace: useMutation({ mutationFn: (body: ReplaceRequest) => translationsApi.replace(jobId, body), onSuccess: () => refresh() }),
    resolveIssue: useMutation({
      mutationFn: (v: { issueId: string; note: string }) => translationsApi.resolveIssue(jobId, v.issueId, v.note),
      onSuccess: () => refresh(),
    }),
  };
}

// ── Resources ─────────────────────────────────────────────────────────

export function useGlossaries(filter: { language?: LanguageCode; status?: GlossaryStatus; glossary_id?: string } = {}, enabled = true) {
  return useQuery({ queryKey: translationKeys.glossaries(filter), queryFn: () => translationsApi.glossaries(filter), enabled });
}

export function useGlossaryEntries(id: string, version?: number) {
  return useQuery({
    queryKey: translationKeys.glossaryEntries(id, version),
    queryFn: () => translationsApi.glossaryEntries(id, version),
    enabled: !!id,
  });
}

export function useLanguageTemplates(filter: { language?: LanguageCode; status?: LanguageTemplateStatus; template_id?: string } = {}, enabled = true) {
  return useQuery({ queryKey: translationKeys.templates(filter), queryFn: () => translationsApi.languageTemplates(filter), enabled });
}

export function useLanguageTemplate(id: string, version?: number) {
  return useQuery({
    queryKey: translationKeys.template(id, version),
    queryFn: () => translationsApi.languageTemplate(id, version),
    enabled: !!id,
  });
}

export function useLanguageTemplateReport(id: string, version?: number) {
  return useQuery({
    queryKey: [...translationKeys.template(id, version), 'report'],
    queryFn: () => translationsApi.languageTemplateReport(id, version),
    enabled: !!id && !!version,
    retry: false,
  });
}

/** Glossary and language-template changes; each refreshes every resource list. */
export function useResourceMutations() {
  const client = useQueryClient();
  const refresh = () => {
    client.invalidateQueries({ queryKey: [...translationKeys.all, 'glossaries'] });
    client.invalidateQueries({ queryKey: [...translationKeys.all, 'glossary-entries'] });
    client.invalidateQueries({ queryKey: [...translationKeys.all, 'language-templates'] });
    client.invalidateQueries({ queryKey: [...translationKeys.all, 'language-template'] });
  };
  return {
    createGlossary: useMutation({ mutationFn: (upload: GlossaryUpload) => translationsApi.createGlossary(upload), onSuccess: refresh }),
    saveGlossary: useMutation({
      mutationFn: (v: { id: string; version: number; entries: GlossaryEntry[]; style_notes: string | null; name: string }) =>
        translationsApi.saveGlossaryEntries(v.id, v.version, { entries: v.entries, style_notes: v.style_notes, name: v.name }),
      onSuccess: refresh,
    }),
    approveGlossary: useMutation({ mutationFn: (v: { id: string; version: number }) => translationsApi.approveGlossary(v.id, v.version), onSuccess: refresh }),
    deleteGlossary: useMutation({ mutationFn: (v: { id: string; version: number }) => translationsApi.deleteGlossary(v.id, v.version), onSuccess: refresh }),
    createTemplate: useMutation({ mutationFn: (upload: LanguageTemplateUpload) => translationsApi.createLanguageTemplate(upload), onSuccess: refresh }),
    markReady: useMutation({ mutationFn: (v: { id: string; version: number }) => translationsApi.markLanguageTemplateReady(v.id, v.version), onSuccess: refresh }),
    deleteTemplate: useMutation({ mutationFn: (v: { id: string; version: number }) => translationsApi.deleteLanguageTemplate(v.id, v.version), onSuccess: refresh }),
  };
}
