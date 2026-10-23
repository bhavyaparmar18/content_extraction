import { request, requestBlob } from '@/lib/api';
import type {
  ArtifactKind,
  CreateMigrationRequest,
  GwpGuide,
  GwpRuleSet,
  JobEvent,
  JobStatus,
  MigrationJob,
  MigrationJobRow,
  QualityReport,
  RenderReport,
  ResolveIssueResponse,
  SectionDraft,
  SectionPlan,
  SlotPlan,
  SourceDocument,
  TemplateModel,
  Claim,
  WithValidation,
} from './types';

const BASE = '/api/v1/migrations';
const job = (jobId: string) => `${BASE}/${encodeURIComponent(jobId)}`;
const json = (body: unknown): RequestInit => ({ method: 'PATCH', body: JSON.stringify(body) });

/** The v2 migration jobs API (`app/api/migrations_v2.py`). */
export const migrationsApi = {
  // ── Jobs ──
  list(params: { status?: JobStatus; limit?: number } = {}): Promise<MigrationJobRow[]> {
    const qs = new URLSearchParams();
    if (params.status) qs.set('status', params.status);
    qs.set('limit', String(params.limit ?? 200));
    return request(`${BASE}?${qs}`);
  },
  get: (jobId: string): Promise<MigrationJob> => request(job(jobId)),
  create: (body: CreateMigrationRequest): Promise<MigrationJob> =>
    request(BASE, { method: 'POST', body: JSON.stringify(body) }),
  cancel: (jobId: string): Promise<MigrationJob> => request(`${job(jobId)}/cancel`, { method: 'POST' }),
  retry: (jobId: string, fromStage?: JobStatus): Promise<MigrationJob> =>
    request(`${job(jobId)}/retry${fromStage ? `?from_stage=${fromStage}` : ''}`, { method: 'POST' }),
  audit: (jobId: string): Promise<JobEvent[]> => request(`${job(jobId)}/audit`),

  // ── Inputs (snapshotted when the job started) ──
  artifact<T>(jobId: string, kind: ArtifactKind, opts: { scope?: string; version?: number } = {}): Promise<T> {
    const qs = new URLSearchParams();
    if (opts.scope) qs.set('scope', opts.scope);
    if (opts.version) qs.set('version', String(opts.version));
    const q = qs.toString();
    return request(`${job(jobId)}/artifacts/${kind}${q ? `?${q}` : ''}`);
  },
  sourceModel: (jobId: string) => migrationsApi.artifact<SourceDocument>(jobId, 'source_model'),
  templateModel: (jobId: string) => migrationsApi.artifact<TemplateModel>(jobId, 'template_model'),
  sourceFile: (jobId: string): Promise<Blob> => requestBlob(`${job(jobId)}/source/file`),
  templateFile: (jobId: string, variant: 'normalized' | 'original' = 'normalized'): Promise<Blob> =>
    requestBlob(`${job(jobId)}/template/file?variant=${variant}`),

  // ── Section plan ──
  sectionPlan: (jobId: string): Promise<SectionPlan> => request(`${job(jobId)}/section-plan`),
  sectionPlanValidation: (jobId: string): Promise<QualityReport> => request(`${job(jobId)}/section-plan/validation`),
  saveSectionPlan: (jobId: string, plan: SectionPlan): Promise<WithValidation<SectionPlan>> =>
    request(`${job(jobId)}/section-plan`, json(plan)),
  approveSectionPlan: (jobId: string): Promise<MigrationJob> =>
    request(`${job(jobId)}/section-plan/approve`, { method: 'POST' }),

  // ── Slot plan ──
  slotPlan: (jobId: string): Promise<SlotPlan> => request(`${job(jobId)}/slot-plan`),
  slotPlanValidation: (jobId: string): Promise<QualityReport> => request(`${job(jobId)}/slot-plan/validation`),
  saveSlotPlan: (jobId: string, plan: SlotPlan): Promise<WithValidation<SlotPlan>> =>
    request(`${job(jobId)}/slot-plan`, json(plan)),
  approveSlotPlan: (jobId: string): Promise<MigrationJob> =>
    request(`${job(jobId)}/slot-plan/approve`, { method: 'POST' }),

  // ── Drafts and quality ──
  drafts: (jobId: string): Promise<SectionDraft[]> => request(`${job(jobId)}/drafts`),
  draftVersion: (jobId: string, sectionId: string, version: number) =>
    migrationsApi.artifact<SectionDraft>(jobId, 'section_draft', { scope: sectionId, version }),
  saveSlot: (jobId: string, sectionId: string, slotId: string, claims: Claim[]): Promise<WithValidation<SectionDraft>> =>
    request(`${job(jobId)}/sections/${encodeURIComponent(sectionId)}/slots/${encodeURIComponent(slotId)}`, json({ claims })),
  quality: (jobId: string): Promise<QualityReport> => request(`${job(jobId)}/validation`),
  resolveIssue: (jobId: string, issueId: string, note: string): Promise<ResolveIssueResponse> =>
    request(`${job(jobId)}/issues/${encodeURIComponent(issueId)}/resolve`, {
      method: 'POST',
      body: JSON.stringify({ note }),
    }),

  // ── Documents ──
  renderReport: (jobId: string): Promise<RenderReport> => request(`${job(jobId)}/document/report`),
  reviewDocument: (jobId: string): Promise<Blob> => requestBlob(`${job(jobId)}/document`),
  finalPreview: (jobId: string): Promise<Blob> => requestBlob(`${job(jobId)}/export/preview`),
  exportWord: (jobId: string): Promise<Blob> => requestBlob(`${job(jobId)}/export/word`),
  traceabilityCsv: (jobId: string): Promise<Blob> => requestBlob(`${job(jobId)}/traceability?format=csv`),

  // ── GWP guides ──
  guides: (): Promise<GwpGuide[]> => request('/api/v1/gwp?status=approved'),
  guideRules: (guideId: string, version?: number): Promise<GwpRuleSet> =>
    request(`/api/v1/gwp/${encodeURIComponent(guideId)}/rules${version ? `?version=${version}` : ''}`),
};
