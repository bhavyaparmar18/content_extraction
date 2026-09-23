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

// --- Template Management Contracts ---

/** A reference into `TemplateExtractionOutput.icon_library`. */
export interface TemplateIconRef {
  icon_key: string;
  section_context?: string | null;
  associated_text?: string | null;
}

/** One physical icon in the template, deduplicated by content hash. */
export interface TemplateIconEntry {
  icon_key: string;
  content_hash?: string | null;
  asset_path: string;
  semantic_meaning: string;
  display_name?: string | null;
  usage_rule?: string | null;
  source_instruction?: string | null;
  allowed_sections?: string[];
  occurrences: number;
}

/** A shaded infographic box style, with colours read from the template. */
export interface TemplateCalloutStyle {
  callout_type: string;
  display_name?: string | null;
  background_color_hex: string;
  left_border_color_hex?: string | null;
  border_width_pt?: number;
  font_color_hex?: string | null;
  icon_key?: string | null;
  trigger_instruction?: string | null;
  placement_rule?: string;
  template_source?: Record<string, unknown>;
}

export type TemplateDirectiveType =
  | 'prohibition'
  | 'requirement'
  | 'guidance'
  | 'placeholder_hint'
  | 'icon_usage'
  | 'formatting';

/** A constraint the migration validator can enforce without the LLM. */
export interface TemplateMachineRule {
  rule: string;
  value: unknown;
  enforce: 'hard' | 'soft' | string;
}

export interface TemplateInstruction {
  instruction_id: string;
  text: string;
  scope: 'global' | 'section' | string;
  directive_type: TemplateDirectiveType | string;
  font_color_hex?: string | null;
  color_detection_method?: string | null;
  paragraph_index?: number;
  section_context?: string | null;
  is_global?: boolean;
  machine_rule?: TemplateMachineRule | null;
  icons?: TemplateIconRef[];
}

export interface TemplateTableCell {
  row_index: number;
  col_index: number;
  row_span: number;
  col_span: number;
  text: string;
  is_header: boolean;
  icon_key?: string | null;
  icon_path?: string | null;
  image_path?: string | null;
  shading_hex?: string | null;
  text_direction?: string | null;
  valign?: string | null;
  bold?: boolean;
}

export interface TemplateElement {
  element_type:
    | 'heading'
    | 'paragraph'
    | 'list'
    | 'table'
    | 'image'
    | 'icon'
    | 'callout'
    | string;
  page: number;
  section_name?: string;
  level?: number;
  text?: string;
  icons?: TemplateIconRef[];
  items?: string[];
  title?: string;
  num_rows?: number;
  num_cols?: number;
  header_rows?: number;
  style_name?: string | null;
  col_widths_pt?: number[];
  cells?: TemplateTableCell[];
  image_path?: string;
  is_instruction?: boolean;
  instruction_text?: string | null;
  font_color_hex?: string | null;
  color_detection_method?: string | null;
  shading_hex?: string | null;
  callout_type?: string | null;
}

export interface TemplateSection {
  section_number?: string | null;
  title: string;
  heading_style?: string | null;
  page_start: number;
  page_end: number;
  required: boolean;
  content_editable: boolean;
  allows_subsections: boolean;
  placeholders?: string[];
  /** Black template content, copied verbatim during migration. */
  skeleton_elements: TemplateElement[];
  /** Blue template content — followed during migration, then removed. */
  authoring_instructions: TemplateInstruction[];
  icons_expected?: string[];
  callouts_allowed?: string[];
}

export interface TemplateGlobalRules {
  instructions: TemplateInstruction[];
}

export interface TemplateMetadata {
  template_id: string;
  template_name: string;
  author: string;
  creation_date: string;
  modification_date: string;
  file_type: string;
  file_size_bytes: number;
}

export interface TemplateTotals {
  sections: number;
  elements: number;
  instructions: number;
  icons: number;
  callouts: number;
}

export interface TemplateExtractionOutput {
  version: string;
  template_id: string;
  template_name: string;
  metadata: TemplateMetadata;
  icon_library: TemplateIconEntry[];
  callout_styles: TemplateCalloutStyle[];
  global_rules: TemplateGlobalRules;
  sections: TemplateSection[];
  totals: TemplateTotals;
}

export interface TemplateRecord {
  id: number;
  template_uid: string;
  template_name: string;
  template_version: number;
  file_type?: string;
  file_size_bytes?: number;
  source_filename?: string | null;
  upload_path?: string | null;
  output_path?: string | null;
  total_sections: number;
  total_elements?: number;
  total_instructions: number;
  total_icons: number;
  total_callouts?: number;
  global_rules_json?: string | null;
  status: "uploaded" | "extracting" | "ready" | "failed";
  created_at: string;
  updated_at?: string;
}

