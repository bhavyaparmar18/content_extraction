/** Review state of a persisted SOP extraction run (matches app/schemas/sop.py). */
export type SopStatus = 'in_review' | 'approved' | 'rejected'

/** One row of `sop_records` — a single completed extraction run of an SOP. */
export interface SopRecord {
  id: number
  job_id: string
  document_Uid: string
  document_number: string | null
  document_name: string | null
  document_title: string | null
  document_version: string | null
  document_type: string | null
  file_type: string
  language: string
  page_count: number
  gpdat_version: number
  status: SopStatus
  source_filename: string | null
  output_path: string | null
  created_at: string
  updated_at: string
}

export interface SopListResponse {
  count: number
  records: SopRecord[]
}

/** Lifecycle state of a batch job or an individual document within it. */
export type JobStatus = 'queued' | 'processing' | 'completed' | 'failed'

export interface RejectedFile {
  filename: string
  reason: string
}

export interface DocumentJob {
  document_id: string
  filename: string
  status: JobStatus
  progress_percentage: number
  message: string
  error: string | null
  started_at: string | null
  completed_at: string | null
}

/** Table vs. card presentation for the SOP list. */
export type ViewMode = 'list' | 'grid'

/** Review-status filter chip value; 'all' clears the filter. */
export type StatusFilter = SopStatus | 'all'

/** File-type filter chip value; 'all' clears the filter. */
export type FileTypeFilter = 'pdf' | 'docx' | 'all'

export interface BatchJob {
  job_id: string
  status: JobStatus
  created_at: string
  started_at: string | null
  completed_at: string | null
  documents: DocumentJob[]
  rejected_files: RejectedFile[]
}

/** One of the element types the exporter currently emits (see app/schemas/migration.py). */
export type MigrationElementType = 'heading' | 'paragraph' | 'list' | 'table' | 'image' | string

/** Reference to an inline or attached icon (path is already a servable /documents/.../assets/... URL). */
export interface MigrationIconRef {
  icon_id: string
  path: string
  semantic_meaning?: string | null
}

/** A single origin cell in a table element, ready to render as a native <td>/<th>. */
export interface MigrationTableCell {
  row_index: number
  col_index: number
  row_span: number
  col_span: number
  text: string
  is_header: boolean
  icon_path?: string | null
  image_path?: string | null
}

/** A single linear document element in reading order within a section. */
export interface MigrationElement {
  element_type: MigrationElementType
  page: number
  section_name?: string | null
  level?: number | null
  text?: string | null
  icons?: MigrationIconRef[]
  items?: string[]
  title?: string | null
  num_rows?: number | null
  num_cols?: number | null
  cells?: MigrationTableCell[]
  image_path?: string | null
}

/** A chapter/section of the document, containing reading-order elements. */
export interface MigrationSection {
  section_number?: string | null
  title: string
  page_start: number
  page_end: number
  elements: MigrationElement[]
}

/** Top-level v2 export envelope returned by GET /documents/v2/{document_id}/json. */
export interface MigrationDocument {
  version: string
  document_Uid: string
  metadata: Record<string, unknown>
  sections: MigrationSection[]
}
