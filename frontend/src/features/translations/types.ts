/**
 * Translation contracts, mirrored by hand from `app/schemas/v2/translation.py` and `app/api/translations.py`
 * (`to_clean_dict()`: optional fields that are null on the server are left out).
 */
import type { JobEvent, QualityReport, RenderReport, Severity, ValidationIssue } from '@/features/migrations/types';

export type { JobEvent, QualityReport, RenderReport, ValidationIssue };

// ── Languages ─────────────────────────────────────────────────────────

export type LanguageCode = 'zh-CN' | 'fr-FR' | 'de-DE' | 'it-IT' | 'ja-JP' | 'pt-BR' | 'es-ES' | 'el-GR';

/** `GET /languages`. */
export interface Language {
  code: LanguageCode;
  name: string;
  script: string;
  east_asian: boolean;
}

// ── Glossaries ────────────────────────────────────────────────────────

export type GlossaryStatus = 'uploaded' | 'in_review' | 'approved' | 'failed';

export interface GlossaryEntry {
  source_term: string;
  target_term: string;
  note?: string;
  case_sensitive?: boolean;
  do_not_translate?: boolean;
}

/** The Glossary JSON (`…/entries`, a job's snapshot, a job's document terms). */
export interface Glossary {
  glossary_id: string;
  version: number;
  language: LanguageCode;
  name: string;
  entries: GlossaryEntry[];
  style_notes?: string;
}

/** A row of the `glossaries` table. */
export interface GlossaryRecord {
  id: number;
  glossary_id: string;
  name: string;
  language: LanguageCode;
  version: number;
  file_type: string | null;
  source_filename: string | null;
  total_entries: number | null;
  error: string | null;
  status: GlossaryStatus;
  created_by: string | null;
  created_at: string;
  updated_at: string;
}

// ── Language templates ────────────────────────────────────────────────

export type LanguageTemplateStatus = 'uploaded' | 'extracted' | 'ready' | 'failed';

export interface FrontMatterPart {
  kind: 'header' | 'footer';
  type: 'default' | 'first' | 'even';
  partname: string;
  text: string;
  images: number;
}

export interface FrontMatterReport {
  template_id: string;
  version: number;
  language: LanguageCode;
  source_filename?: string;
  cover_end?: 'section_break' | 'page_break';
  cover_blocks: number;
  cover_text: string;
  sections: number;
  title_page_cover: boolean;
  title_page_body: boolean;
  even_and_odd: boolean;
  cover_parts: FrontMatterPart[];
  body_parts: FrontMatterPart[];
  styles: string[];
  images: number;
  problems: string[];
  warnings: string[];
}

/** A row of the `language_templates` table; the upload's response also carries its `report`. */
export interface LanguageTemplateRecord {
  id: number;
  template_id: string;
  name: string;
  language: LanguageCode;
  version: number;
  source_filename: string | null;
  error: string | null;
  status: LanguageTemplateStatus;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  report?: FrontMatterReport | null;
}

// ── Jobs ──────────────────────────────────────────────────────────────

export type TranslationStatus =
  | 'PENDING' | 'PREPARING' | 'TRANSLATING' | 'CHECKING' | 'REPAIRING' | 'RENDERING'
  | 'REVIEW_PENDING' | 'APPROVED' | 'FAILED_TECHNICAL' | 'CANCELLED';

export type TranslationArtifactKind =
  | 'source_model' | 'template_model' | 'slot_plan' | 'section_draft' | 'assembled_draft' | 'number_map'
  | 'docx' | 'render_report' | 'quality_report' | 'segments' | 'translation' | 'glossary' | 'front_matter';

export interface TranslationArtifactRef {
  kind: TranslationArtifactKind;
  version: number;
  path: string;
  sha256: string;
  scope?: string;
  created_at?: string;
  created_by?: string;
}

export interface Blocker {
  code: 'NO_RENDER' | 'RENDER_OUT_OF_DATE' | 'RENDER_PROBLEMS' | 'NO_VALIDATION' | 'OPEN_GATE' | 'OPEN_CRITICAL' | string;
  message: string;
  issue_id?: string;
}

/** `GET /{id}` of a job in review or approved. */
export interface ReviewState {
  render_current: boolean;
  docx_version: number | null;
  blockers: Blocker[];
  can_approve: boolean;
}

export interface TranslationJob {
  job_id: string;
  migration_job_id: string;
  language: LanguageCode;
  glossary_id?: string;
  glossary_version?: number;
  language_template_id?: string;
  language_template_version?: number;
  status: TranslationStatus;
  artifacts: TranslationArtifactRef[];
  created_by?: string;
  created_at?: string;
  updated_at?: string;
  approved_by?: string;
  approved_at?: string;
  error?: string;
  running: boolean;
  review?: ReviewState;
}

/** A row of `GET /translations` (the job table, without artifacts). */
export interface TranslationJobRow {
  job_id: string;
  migration_job_id: string;
  language: LanguageCode;
  glossary_id: string | null;
  glossary_version: number | null;
  language_template_id: string | null;
  language_template_version: number | null;
  status: TranslationStatus;
  created_by: string | null;
  approved_by: string | null;
  approved_at: string | null;
  error: string | null;
  failed_stage: string | null;
  created_at: string;
  updated_at: string;
  running: boolean;
}

export interface LanguageChoice {
  language: LanguageCode;
  glossary_id?: string;
  glossary_version?: number;
  language_template_id?: string;
  language_template_version?: number;
}

export interface CreateTranslationsRequest {
  migration_job_id: string;
  languages: LanguageChoice[];
}

// ── Segments ──────────────────────────────────────────────────────────

export type SegmentKind = 'claim' | 'table_cell' | 'table_header' | 'xref' | 'template_text';
export type SegmentOrigin = 'llm' | 'repair' | 'human' | 'copied';

export interface SegmentLocator {
  section_id?: string;
  slot_id?: string;
  claim_id?: string;
  unit_id?: string;
  row?: number;
  col?: number;
  paragraph?: number;
  ref_index?: number;
  block_path?: string;
}

export interface Segment {
  segment_id: string;
  kind: SegmentKind;
  source_text: string;
  target_text?: string;
  origin?: SegmentOrigin;
  locator: SegmentLocator;
}

/** `GET /{id}/segments`: the SegmentSet with the latest translations merged in. */
export interface SegmentSet {
  job_id: string;
  migration_job_id: string;
  language: LanguageCode;
  version: number;
  accepted_gaps: string[];
  draft_versions: Record<string, number>;
  notes: string[];
  segments: Segment[];
  counts: Partial<Record<SegmentKind, number>>;
  scopes: string[];
}

// ── Review ────────────────────────────────────────────────────────────

export interface ValidationSummary {
  version: number;
  issues: number;
  open: number;
  by_severity: Partial<Record<Severity, number>>;
  gate_issues: number;
  gates_passed: boolean;
}

/** The response of a segment edit (and the base of a replace's). */
export interface EditResult {
  segments: Segment[];
  issues: ValidationIssue[];
  validation: ValidationSummary;
  translation_versions: Record<string, number>;
  render_current: boolean;
}

export interface ReplaceMatch {
  segment_id: string;
  occurrence: number;
  kind: SegmentKind;
  scope: string;
  origin?: SegmentOrigin | null;
  english: string;
  context_before: string;
  match: string;
  context_after: string;
}

export interface ReplacePreview {
  find: string;
  total: number;
  segments: number;
  longer_words: Record<string, number>;
  matches: ReplaceMatch[];
  translation_versions: Record<string, number>;
  glossary_terms: string[];
  document_terms: string[];
  warnings: string[];
}

export interface ReplaceRequest {
  find: string;
  replace: string;
  case_sensitive: boolean;
  whole_word: boolean;
  section?: string;
  targets: 'all' | { segment_id: string; occurrence: number }[];
  expected_versions: Record<string, number>;
}

export interface ReplaceResult extends EditResult {
  replaced: number;
  skipped: { segment_id: string; problems: string[] }[];
  term_updated: string[];
  longer_words: Record<string, number>;
}

export interface ResolveResult extends QualityReport {
  gates_passed: boolean;
  blockers: Blocker[];
}
