/**
 * Release 1 — TypeScript Contracts
 * Matching release_1_spec.md Section 31
 */

export type SopStatus = "in_review" | "approved" | "rejected";
export type JobStatus = "queued" | "processing" | "completed" | "failed";
export type ReviewMode = "review" | "translation" | "migration";
export type SuggestionStatus = "proposed" | "accepted" | "rejected" | "expired";

export interface SopRecord {
  id: number;
  job_id: string;
  document_Uid: string;
  document_number: string | null;
  document_name: string | null;
  document_title: string | null;
  document_version: string | null;
  document_type: string | null;
  file_type: string;
  language: string;
  page_count: number;
  gpdat_version: number;
  status: SopStatus;
  source_filename: string | null;
  output_path: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentJob {
  document_id: string;
  filename: string;
  status: JobStatus;
  progress_percentage: number;
  message: string;
  result: Record<string, unknown> | null;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface RejectedFile {
  filename: string;
  reason: string;
}

export interface BatchJob {
  job_id: string;
  status: JobStatus;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  documents: DocumentJob[];
  rejected_files: RejectedFile[];
  total_documents?: number;
  completed_documents?: number;
  failed_documents?: number;
}

export interface MigrationIconRef {
  icon_id?: string;
  path?: string;
  semantic_meaning?: string | null;
}

export interface MigrationTableCell {
  row_index: number;
  col_index: number;
  row_span: number;
  col_span: number;
  text: string;
  is_header?: boolean;
  icon_path?: string | null;
  image_path?: string | null;
  raw_bbox?: number[];
}

export interface MigrationElement {
  id?: string;
  element_type: "heading" | "paragraph" | "list" | "table" | "image" | "icon" | string;
  page: number;
  section_name?: string;
  level?: number;
  text?: string;
  icons?: Array<string | MigrationIconRef>;
  items?: string[];
  title?: string;
  num_rows?: number;
  num_cols?: number;
  cells?: MigrationTableCell[];
  image_path?: string;
  asset_filename?: string;
  confidence?: number;
  raw_bbox?: number[];
}

export interface MigrationSection {
  section_number: string;
  title: string;
  page_start: number;
  page_end: number;
  elements: MigrationElement[];
}

export interface MigrationMetadata {
  document_Uid: string;
  document_number?: string | null;
  document_name?: string | null;
  document_title?: string | null;
  document_version?: string | null;
  document_type?: string | null;
  file_type?: string;
  language?: string;
  page_count?: number;
  gpdat_version?: number;
}

export interface DocxMigrationOutput {
  version: string;
  document_Uid: string;
  metadata: MigrationMetadata;
  sections: MigrationSection[];
}

export interface ReviewDocument {
  recordId: number;
  documentUid: string;
  title: string;
  sopNumber?: string | null;
  version: string;
  fileType: string;
  pageCount: number;
}

export interface ReviewContext {
  mode: ReviewMode;
  workflowId: string;
  workflowVersion: number;
  status: string;
  sourceLocale: string;
  targetLocale?: string | null;
  rowVersion: number;
}

export interface ReviewLayout {
  leftPanel: string;
  rightPanel: string;
  showOriginalViewer: boolean;
  showAiSuggestions: boolean;
  showCompareView: boolean;
  showVersionHistory: boolean;
  showIssuePanel: boolean;
}

export interface ReviewBootstrap {
  document: ReviewDocument;
  reviewContext: ReviewContext;
  layout: ReviewLayout;
  availableActions: string[];
  links: {
    content: string;
    versions: string;
    issues: string;
    websocket: string;
  };
}

export interface AISuggestion {
  id: string;
  workflow_id: string;
  entity_id: string;
  action: string;
  instruction?: string;
  base_revision: number;
  patch_json: string;
  explanation?: string;
  status: SuggestionStatus;
  model_metadata?: string;
  created_at: string;
  created_by?: string;
}

export interface Issue {
  id: string;
  document_uid: string;
  workflow_type: string;
  workflow_id: string;
  entity_type?: string;
  entity_id?: string;
  category: string;
  description: string;
  expected_value?: string;
  source_anchor_json?: string;
  status: "open" | "resolved" | "reopened";
  assigned_to?: string;
  resolution?: string;
  created_at: string;
  created_by: string;
  updated_at: string;
  updated_by: string;
}

export interface ReprocessingRequest {
  id: string;
  document_uid: string;
  sop_record_id: number;
  workflow_id: string;
  status: "pending_approval" | "approved" | "rejected";
  requested_at: string;
  requested_by: string;
  reason: string;
  pages?: string;
  decided_at?: string | null;
  decided_by?: string | null;
  decision_comment?: string | null;
  job_id?: string | null;
}

export interface WorkflowVersion {
  id: string;
  version_number: number;
  workflow_type: string;
  status: string;
  created_at: string;
  created_by?: string;
  description?: string;
  is_current?: boolean;
}

export interface WorkflowProgressEnvelope {
  event_id: string;
  event_type: string;
  sequence: number;
  occurred_at: string;
  workflow_id: string;
  document_uid: string;
  payload: {
    stage: string;
    progress_percentage: number;
    message: string;
    details?: Record<string, unknown>;
  };
}

export interface ElementPlacement {
  source_section_title: string;
  source_element_index: number;
  source_element_type: string;
  target_section_heading: string;
  placement_order: number;
  action: string;
  embed_icons_inline?: boolean;
  notes?: string;
}

export interface SectionPlan {
  template_section_heading: string;
  template_heading_level?: number;
  source_sections_mapped: string[];
  elements: ElementPlacement[];
  has_source_content: boolean;
  is_unmapped_source?: boolean;
}

export interface MigrationPlan {
  template_name: string;
  document_type_detected: string;
  font_family: string;
  font_size_body_pt?: number;
  overall_confidence?: number;
  section_plans: SectionPlan[];
  warnings?: string[];
  reasoning_summary?: string;
}

export interface MigrationQAReport {
  status: string;
  total_source_sections: number;
  total_source_elements: number;
  total_placed_elements: number;
  total_skipped_elements: number;
  content_coverage_pct: number;
  sections_mapped: number;
  low_confidence_warnings: string[];
  validation_errors: string[];
}

export interface MigrationResult {
  output_path: string;
  plan: MigrationPlan;
  qa_report: MigrationQAReport;
  download_url?: string;
}

