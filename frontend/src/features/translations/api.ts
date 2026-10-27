import { request, requestBlob } from '@/lib/api';
import type {
  CreateTranslationsRequest,
  EditResult,
  FrontMatterReport,
  Glossary,
  GlossaryEntry,
  GlossaryRecord,
  GlossaryStatus,
  JobEvent,
  Language,
  LanguageCode,
  LanguageTemplateRecord,
  LanguageTemplateStatus,
  QualityReport,
  RenderReport,
  ReplacePreview,
  ReplaceRequest,
  ReplaceResult,
  ResolveResult,
  SegmentSet,
  TranslationJob,
  TranslationJobRow,
  TranslationStatus,
} from './types';

const BASE = '/api/v1/translations';
const job = (jobId: string) => `${BASE}/${encodeURIComponent(jobId)}`;
const glossary = (id: string) => `${BASE}/glossaries/${encodeURIComponent(id)}`;
const template = (id: string) => `${BASE}/language-templates/${encodeURIComponent(id)}`;
const post = (body?: unknown): RequestInit => ({ method: 'POST', ...(body === undefined ? {} : { body: JSON.stringify(body) }) });

/** `?a=1&b=2` from the defined values, or nothing. */
function query(params: Record<string, string | number | undefined | null>): string {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v !== undefined && v !== null && v !== '' && qs.set(k, String(v)));
  const q = qs.toString();
  return q ? `?${q}` : '';
}

function form(fields: Record<string, string | Blob | undefined>): FormData {
  const data = new FormData();
  Object.entries(fields).forEach(([k, v]) => v !== undefined && v !== '' && data.append(k, v));
  return data;
}

export interface GlossaryUpload {
  language: LanguageCode;
  name?: string;
  glossary_id?: string;
  style_notes?: string;
  file?: File;
}

export interface LanguageTemplateUpload {
  language: LanguageCode;
  file: File;
  name?: string;
  template_id?: string;
}

/** The translation API (`app/api/translations.py`). */
export const translationsApi = {
  languages: (): Promise<Language[]> => request(`${BASE}/languages`),

  // ── Glossaries ──
  glossaries: (params: { language?: LanguageCode; status?: GlossaryStatus; glossary_id?: string } = {}): Promise<GlossaryRecord[]> =>
    request(`${BASE}/glossaries${query(params)}`),
  glossary: (id: string, version?: number): Promise<GlossaryRecord> => request(`${glossary(id)}${query({ version })}`),
  createGlossary: (upload: GlossaryUpload): Promise<GlossaryRecord> =>
    request(`${BASE}/glossaries`, { method: 'POST', body: form({ ...upload }) }),
  glossaryEntries: (id: string, version?: number): Promise<Glossary> => request(`${glossary(id)}/entries${query({ version })}`),
  saveGlossaryEntries: (
    id: string,
    version: number,
    body: { entries: GlossaryEntry[]; style_notes?: string | null; name?: string },
  ): Promise<GlossaryRecord> => request(`${glossary(id)}/entries${query({ version })}`, { method: 'PUT', body: JSON.stringify(body) }),
  approveGlossary: (id: string, version: number): Promise<GlossaryRecord> => request(`${glossary(id)}/approve${query({ version })}`, post()),
  exportGlossary: (id: string, version: number, format: 'csv' | 'xlsx'): Promise<Blob> =>
    requestBlob(`${glossary(id)}/export${query({ version, format })}`),
  deleteGlossary: (id: string, version: number): Promise<unknown> => request(`${glossary(id)}${query({ version })}`, { method: 'DELETE' }),

  // ── Language templates ──
  languageTemplates: (
    params: { language?: LanguageCode; status?: LanguageTemplateStatus; template_id?: string } = {},
  ): Promise<LanguageTemplateRecord[]> => request(`${BASE}/language-templates${query(params)}`),
  languageTemplate: (id: string, version?: number): Promise<LanguageTemplateRecord> => request(`${template(id)}${query({ version })}`),
  createLanguageTemplate: (upload: LanguageTemplateUpload): Promise<LanguageTemplateRecord> =>
    request(`${BASE}/language-templates`, { method: 'POST', body: form({ ...upload }) }),
  languageTemplateReport: (id: string, version?: number): Promise<FrontMatterReport> => request(`${template(id)}/report${query({ version })}`),
  languageTemplatePreview: (id: string, version?: number): Promise<Blob> => requestBlob(`${template(id)}/preview${query({ version })}`),
  markLanguageTemplateReady: (id: string, version: number): Promise<LanguageTemplateRecord> =>
    request(`${template(id)}/ready${query({ version })}`, post()),
  deleteLanguageTemplate: (id: string, version: number): Promise<unknown> =>
    request(`${template(id)}${query({ version })}`, { method: 'DELETE' }),

  // ── Jobs ──
  create: (body: CreateTranslationsRequest): Promise<TranslationJob[]> => request(BASE, post(body)),
  list: (params: { migration_job_id?: string; language?: LanguageCode; status?: TranslationStatus; limit?: number } = {}): Promise<TranslationJobRow[]> =>
    request(`${BASE}${query({ limit: 500, ...params })}`),
  get: (jobId: string): Promise<TranslationJob> => request(job(jobId)),
  cancel: (jobId: string): Promise<TranslationJob> => request(`${job(jobId)}/cancel`, post()),
  retry: (jobId: string, fromStage?: TranslationStatus): Promise<TranslationJob> =>
    request(`${job(jobId)}/retry${query({ from_stage: fromStage })}`, post()),
  audit: (jobId: string): Promise<JobEvent[]> => request(`${job(jobId)}/audit`),
  segments: (jobId: string): Promise<SegmentSet> => request(`${job(jobId)}/segments`),
  validation: (jobId: string): Promise<QualityReport> => request(`${job(jobId)}/validation`),
  renderReport: (jobId: string): Promise<RenderReport> => request(`${job(jobId)}/render-report`),
  preview: (jobId: string): Promise<Blob> => requestBlob(`${job(jobId)}/export/preview`),
  english: (jobId: string): Promise<Blob> => requestBlob(`${job(jobId)}/english`),
  jobGlossary: (jobId: string): Promise<Glossary> => request(`${job(jobId)}/glossary`),
  jobTerms: (jobId: string): Promise<Glossary> => request(`${job(jobId)}/glossary?scope=terms`),

  // ── Review ──
  editSegment: (jobId: string, segmentId: string, targetText: string, applyTo: 'same_text' | 'this'): Promise<EditResult> =>
    request(`${job(jobId)}/segments/${encodeURIComponent(segmentId)}`, {
      method: 'PATCH',
      body: JSON.stringify({ target_text: targetText, apply_to: applyTo }),
    }),
  replacePreview: (jobId: string, body: { find: string; case_sensitive: boolean; whole_word: boolean; section?: string }): Promise<ReplacePreview> =>
    request(`${job(jobId)}/replace/preview`, post(body)),
  replace: (jobId: string, body: ReplaceRequest): Promise<ReplaceResult> => request(`${job(jobId)}/replace`, post(body)),
  resolveIssue: (jobId: string, issueId: string, note: string): Promise<ResolveResult> =>
    request(`${job(jobId)}/issues/${encodeURIComponent(issueId)}/resolve`, post({ note })),
  render: (jobId: string): Promise<TranslationJob> => request(`${job(jobId)}/render`, post()),
  approve: (jobId: string, note?: string): Promise<TranslationJob> => request(`${job(jobId)}/approve`, post(note ? { note } : {})),
  exportWord: (jobId: string): Promise<Blob> => requestBlob(`${job(jobId)}/export/word`),
};
