/**
 * Migration v2 contracts, mirrored by hand from `app/schemas/v2/` (the API returns them as
 * `to_clean_dict()`: optional fields that are null on the server are left out).
 */

// ── Common ────────────────────────────────────────────────────────────

export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info';
export type CalloutKind = 'introduction' | 'explanation' | 'attention' | 'key_takeaway';
export type ContentType =
  | 'purpose' | 'scope' | 'definition' | 'responsibility' | 'prerequisite' | 'process_input'
  | 'ordered_procedure' | 'decision' | 'timing' | 'frequency' | 'duration' | 'restriction'
  | 'warning' | 'expected_output' | 'record' | 'reference' | 'supporting_information';

// ── Job ───────────────────────────────────────────────────────────────

export type JobStatus =
  | 'PENDING' | 'PARSING' | 'PLANNING_SECTIONS' | 'SECTION_PLAN_REVIEW_PENDING' | 'PLANNING_SLOTS'
  | 'SLOT_PLAN_REVIEW_PENDING' | 'DRAFTING' | 'VALIDATING' | 'REPAIRING' | 'ASSEMBLING' | 'RECONCILING'
  | 'RENDERING' | 'QUALITY_REVIEW' | 'HUMAN_REVIEW_REQUIRED' | 'COMPLETED' | 'COMPLETED_WITH_WARNINGS'
  | 'MANUALLY_EDITED' | 'FAILED_TECHNICAL' | 'CANCELLED';

export type JobMode = 'review' | 'auto';
export type SectionStatus = 'pending' | 'slot_planned' | 'drafted' | 'validated' | 'repairing' | 'needs_review' | 'approved';
export type ArtifactKind =
  | 'source_model' | 'template_model' | 'gwp_rules' | 'protected_facts' | 'section_plan' | 'slot_plan'
  | 'section_draft' | 'assembled_draft' | 'number_map' | 'quality_report' | 'docx' | 'render_report' | 'traceability';

export interface SectionState {
  target_section_id: string;
  status: SectionStatus;
  attempts: number;
  last_error?: string;
}

export interface ArtifactRef {
  kind: ArtifactKind;
  version: number;
  path: string;
  sha256: string;
  scope?: string;
  created_at?: string;
  created_by?: string;
}

export interface MigrationJob {
  job_id: string;
  sop_record_id: number;
  template_id: string;
  template_version: number;
  gwp_id?: string;
  gwp_version?: number;
  mode: JobMode;
  status: JobStatus;
  sections: SectionState[];
  artifacts: ArtifactRef[];
  created_by?: string;
  created_at?: string;
  updated_at?: string;
  error?: string;
  running: boolean;
}

/** A row of `GET /api/v1/migrations` (the job table, without sections and artifacts). */
export interface MigrationJobRow {
  job_id: string;
  sop_record_id: number;
  template_id: string;
  template_version: number;
  gwp_id: string | null;
  gwp_version: number | null;
  mode: JobMode;
  status: JobStatus;
  created_by: string | null;
  error: string | null;
  failed_stage: string | null;
  cancel_requested: boolean;
  created_at: string;
  updated_at: string;
  running: boolean;
}

export interface CreateMigrationRequest {
  sop_record_id: number;
  template_id: string;
  template_version?: number;
  gwp_id?: string;
  gwp_version?: number;
  mode: JobMode;
}

export interface JobEvent {
  id: number;
  job_id: string;
  at: string;
  actor: string | null;
  event: string;
  from_status: string | null;
  to_status: string | null;
  detail: Record<string, any> | null;
}

// ── Source ────────────────────────────────────────────────────────────

export type UnitType =
  | 'paragraph' | 'procedure_step' | 'bullet' | 'warning' | 'note' | 'table_row' | 'table_cell_group'
  | 'caption' | 'reference' | 'definition' | 'heading_statement' | 'figure';

export interface TableCell {
  col: number;
  text: string;
  row_span?: number;
  col_span?: number;
  is_header?: boolean;
  fill_hex?: string;
  paragraphs?: string[];
}

export interface TableRef {
  table_id: string;
  row_index: number;
  header_cells?: string[];
  cells?: TableCell[];
}

export interface SourceAsset {
  kind: 'figure' | 'icon';
  asset_key: string;
  path?: string;
  width_px?: number;
  height_px?: number;
}

export interface SourceUnit {
  unit_id: string;
  content_hash: string;
  section_id: string;
  seq: number;
  unit_type: UnitType;
  text: string;
  list_level?: number;
  list_number?: string;
  table_ref?: TableRef;
  location?: { page?: number; paragraph_index?: number; xml_path?: string };
  relations?: { type: string; target_unit_id: string }[];
  assets?: SourceAsset[];
  is_boilerplate?: boolean;
}

export interface SourceSection {
  section_id: string;
  number?: string;
  heading: string;
  level: number;
  section_order: number;
  parent_id?: string;
  units: SourceUnit[];
}

export interface SourceDocument {
  schema_version: string;
  document_id: string;
  document_version?: string;
  source_file: string;
  file_type: string;
  language: string;
  sections: SourceSection[];
}

// ── Template ──────────────────────────────────────────────────────────

export type FormattingProfile = 'paragraphs' | 'ordered_list' | 'bullets' | 'table' | 'callout';

export interface TargetSlot {
  slot_id: string;
  section_id: string;
  key?: string;
  instruction: string;
  content_type: ContentType;
  required?: boolean;
  display_order: number;
  instruction_behavior?: string;
  icon?: { icon_key: string; type?: string };
  formatting_profile?: FormattingProfile;
  callout_kind?: CalloutKind;
}

export interface ConditionalRegion {
  region_id: string;
  kind: 'inline_choice' | 'block';
  text: string;
}

export interface TargetSection {
  section_id: string;
  key?: string;
  number?: string;
  heading: string;
  level: number;
  display_order: number;
  required?: boolean;
  purpose_instruction?: string;
  optional_marker?: boolean;
  aliases?: string[];
  slots: TargetSlot[];
  one_of?: string[][];
  conditional_regions?: ConditionalRegion[];
}

export interface CalloutStyle {
  kind: CalloutKind;
  label: string;
  fill_hex: string;
  icon_key?: string;
  text_color_hex?: string;
}

export interface TemplateModel {
  schema_version: string;
  template_id: string;
  template_version: number;
  source_file: string;
  normalized_file?: string;
  sections: TargetSection[];
  callout_palette: CalloutStyle[];
  readiness: 'ready' | 'needs_normalization' | 'needs_review';
}

// ── Plans ─────────────────────────────────────────────────────────────

export type MappingType = 'one_to_one' | 'merge' | 'split' | 'move' | 'copy' | 'omit' | 'unresolved';
export type MappingStatus =
  | 'mapped' | 'source_content_not_found' | 'not_applicable' | 'unmapped_source_content'
  | 'conflicting_source' | 'needs_review';
export type Origin = 'rule' | 'llm' | 'human';

export interface SectionMapping {
  target_section_id?: string;
  source_section_ids: string[];
  unit_ids: string[];
  mapping_type: MappingType;
  ordering_rule?: 'preserve_source_order' | 'template_order';
  status: MappingStatus;
  reason?: string;
  justification?: string;
  confidence?: number;
  origin?: Origin;
}

export interface SectionPlan {
  job_id: string;
  version: number;
  origin: Origin;
  mappings: SectionMapping[];
  approved_by?: string;
  prompt_version?: string;
  model?: string;
  token_usage?: Record<string, number>;
}

export type MigrationAction =
  | 'extract_and_rewrite' | 'extract_and_consolidate' | 'rewrite_as_ordered_procedure' | 'copy_verbatim' | 'none';

export interface SlotMapping {
  slot_id: string;
  source_unit_ids: string[];
  extraction_scope?: string[];
  below_unit_ids?: string[];
  migration_action: MigrationAction;
  ordering_rule?: 'preserve_source_order' | 'template_order';
  status: MappingStatus;
  requires_human_review?: boolean;
  note?: string;
  origin?: Origin;
  rule_ids?: string[];
}

export interface CalloutAssignment {
  unit_ids: string[];
  kind: CalloutKind;
  origin?: Origin;
  reason: string;
}

export interface RegionChoice {
  region_id: string;
  unit_ids: string[];
  choice?: string;
}

export interface SectionSlotPlan {
  target_section_id: string;
  source_section_ids: string[];
  slot_mappings: SlotMapping[];
  unplaced_unit_ids: string[];
  callout_assignments?: CalloutAssignment[];
  region_choices?: RegionChoice[];
  notes?: string[];
}

export interface SlotPlan {
  job_id: string;
  version: number;
  origin: Origin;
  sections: SectionSlotPlan[];
  approved_by?: string;
  prompt_version?: string;
  model?: string;
  token_usage?: Record<string, number>;
  gwp_guide_id?: string;
}

// ── Drafts ────────────────────────────────────────────────────────────

export type ClaimKind = 'paragraph' | 'bullet' | 'step' | 'table_row' | 'figure' | 'caption' | 'heading';

export interface EvidenceSpan {
  unit_id: string;
  start: number;
  end: number;
}

export interface Claim {
  claim_id: string;
  text: string;
  kind: ClaimKind;
  source_unit_ids: string[];
  source_section_id?: string;
  spans?: EvidenceSpan[];
  rule_ids_applied?: string[];
  derived_from_claim_ids?: string[];
  is_gap_marker?: boolean;
  list_level?: number;
  callout_kind?: CalloutKind;
}

export interface SlotDraft {
  slot_id: string;
  rendering: FormattingProfile;
  claims: Claim[];
}

export type DraftOrigin = 'llm' | 'repair' | 'reconcile' | 'human';

export interface SectionDraft {
  target_section_id: string;
  version: number;
  origin: DraftOrigin;
  slots: SlotDraft[];
  unresolved_items?: string[];
  prompt_version?: string;
  model?: string;
}

// ── Quality ───────────────────────────────────────────────────────────

export type Gate =
  | 'unsupported_claim' | 'numerical_change' | 'missing_section' | 'missing_slot'
  | 'broken_cross_reference' | 'unaccounted_source' | 'high_risk_unresolved' | 'sequence_violation';

export type IssueCategory =
  | 'structure' | 'traceability' | 'preservation' | 'order' | 'formatting' | 'cross_reference' | 'semantic' | 'consistency'
  | 'terminology' | 'language'; // the last two: translation checks

export interface ValidationIssue {
  issue_id: string;
  severity: Severity;
  category: IssueCategory;
  source?: 'deterministic' | 'critic' | 'human';
  gate?: Gate;
  target_section_id?: string;
  slot_id?: string;
  claim_ids?: string[];
  unit_ids?: string[];
  /** Translation checks: the segments the issue is about. */
  segment_ids?: string[];
  message: string;
  resolved?: boolean;
  resolution_note?: string;
}

export interface QualityReport {
  job_id: string;
  version: number;
  issues: ValidationIssue[];
  unit_coverage: number;
  soft_scores: Record<string, number>;
  high_risk_units: Record<string, string[]>;
  gate_counts: Partial<Record<Gate, number>>;
}

/** The PATCH responses carry the saved plan or draft plus its validation report. */
export type WithValidation<T> = T & { validation: QualityReport };

export interface ResolveIssueResponse extends QualityReport {
  gates_passed: boolean;
  status: JobStatus;
}

// ── Rendering ─────────────────────────────────────────────────────────

export interface RenderReport {
  job_id: string;
  version: number;
  mode: 'review' | 'final';
  template_file: string;
  draft_versions?: Record<string, number>;
  slots: { slot_id: string; outcome: string; claims?: number; tables?: number; callout_boxes?: number; note?: string }[];
  regions: { region_id: string; outcome: string; choice?: string; note?: string }[];
  sections_removed: string[];
  warnings: string[];
  problems: string[];
  toc_entries?: number;
  toc_page_numbers?: boolean;
  ok: boolean;
}

// ── GWP ───────────────────────────────────────────────────────────────

export interface GwpGuide {
  id: number;
  guide_id: string;
  guide_name: string;
  version: number;
  status: string;
  total_rules?: number;
  approved_rules?: number;
}

export interface GwpRule {
  rule_id: string;
  category: string;
  text: string;
  applies_to_content_types?: ContentType[];
  severity?: Severity;
}

export interface GwpRuleSet {
  guide_id: string;
  version: number;
  rules: GwpRule[];
}
