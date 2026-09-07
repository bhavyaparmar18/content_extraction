# System Specification: SOP Batch Upload, Repository, Common Review Page, AI Translation, AI Migration, and Content Viewer

## Release 1 Complete Frontend and Backend Implementation Specification

**Document status:** Implementation ready  
**Release:** Release 1  
**Frontend:** React 19, TypeScript, Vite, React Router, Tailwind CSS v3  
**Backend:** FastAPI, Python, Uvicorn, Pydantic 2  
**Release 1 data:** SQLite and local filesystem  
**Processing:** In-memory `JobManager`, `asyncio.to_thread`, `concurrency=1`  
**Realtime:** HTTP polling with optional FastAPI WebSocket progress  
**AI workflows:** Extraction assistance, Translation, Migration, and reviewable AI suggestions

---

## 1. Overview

This document is the single implementation-ready specification for the Release 1 SOP Migration System. The platform manages SOP documents throughout the complete lifecycle:

```text
Batch Upload
  -> Metadata Pre-Extraction
  -> Background Extraction
  -> Repository
  -> Common Review Page
      -> Extraction Review
      -> Translation Review
      -> Migration Review
  -> Approval
  -> Content Viewing and Download
```

The system allows users to upload PDF and DOCX Standard Operating Procedure documents in a batch. Each accepted file is asynchronously parsed into structured content including headings, paragraphs, lists, tables, images, icons, and captions. Metadata includes document number, document name, title, version, type, language, file type, and page count.

The Release 1 backend uses SQLite and the local filesystem. The React frontend uses Tailwind CSS and follows the supplied dark navy, teal, and emerald UI design. A single reusable `ReviewPage` supports extraction review, translation, and migration, preventing duplicated screens and keeping common behavior consistent.

### Core capabilities

- Batch upload of PDF and DOCX documents.
- Independent per-file validation and partial batch acceptance.
- Background extraction with polling and optional WebSocket progress.
- Deterministic document identity and database-derived upload versioning.
- SOP Repository with KPI cards, search, filters, table and card views.
- Common Review Page configured by document ID, mode, workflow ID, permissions, and backend response.
- Extraction editing, source viewing, issue reporting, and reprocessing requests.
- Admin approval or rejection of reprocessing requests.
- AI translation with glossary, suggestions, editing, QA, and approval.
- AI migration with template mapping, suggestions, editing, validation, and approval.
- Content Viewer with section navigation and structured element rendering.
- Version history, comparison, review statuses, downloads, logging, and auditability.

---

## 2. Release 1 architecture

```text
+-------------------------+       HTTP/JSON, multipart, WS       +--------------------------+
| React Frontend          | -----------------------------------> | FastAPI Backend          |
| Vite, TS, Tailwind CSS  | <----------------------------------- |                          |
+-------------------------+                                      | +----------------------+ |
                                                                 | | JobManager          | |
                                                                 | | asyncio + threads  | |
                                                                 | | concurrency = 1    | |
                                                                 | +----------+---------+ |
                                                                 |            |           |
                                                                 |            v           |
                                                                 | Extraction Pipeline    |
                                                                 | Parse -> Tables ->      |
                                                                 | Stitch -> Icons ->      |
                                                                 | Captions -> AST ->      |
                                                                 | Chunk -> Export JSON    |
                                                                 +------------+-------------+
                                                                              |
                                                                              v
                                      +-----------------------------------------------+
                                      | Filesystem                                    |
                                      | data/uploads                                  |
                                      | data/output                                   |
                                      | data/extracted_images                         |
                                      | data/extracted_icons                          |
                                      |                                               |
                                      | SQLite                                        |
                                      | sop_records.db, workflow.db, logs.db          |
                                      +-----------------------------------------------+
```

### Architectural decisions

#### Asynchronous job queue

Uploads do not block until extraction finishes. `POST /documents/upload/batch` returns a `job_id` immediately. The frontend polls `GET /jobs/{job_id}` every 1.5 seconds or connects to `WS /jobs/{job_id}/progress` until all documents reach a terminal state.

#### Single worker

Release 1 runs `JobManager(settings, concurrency=1)`. Pipeline stages are CPU-bound pure-Python work dispatched through `asyncio.to_thread`. Multiple threads do not provide meaningful CPU parallelism because of the GIL and can increase stage time through thread contention. Documents are therefore processed sequentially while the FastAPI event loop remains responsive.

#### SQLite-derived versioning

SQLite is the source of truth for `gpdat_version`. The next version is:

```text
MAX(gpdat_version for document_uid) + 1
```

There is no separate counter file. Deleting every row for a document resets the next upload to version 1.

#### Deterministic document ID

`document_id` is built from sanitized document number, document name, and document version:

```text
BI-VQD-24416_BI-VQD-24416-G_v3.0
```

Re-uploading the same physical document overwrites the shared uploaded file and latest v2 JSON, but creates a new `sop_records` row with a new `gpdat_version`.

#### Common Review Page

One route and one top-level page support all three workflows:

```text
/review/1025?mode=review
/review/1025?mode=translation
/review/1025?mode=migration
```

The backend supplies layout configuration and actions. The frontend composes shared components with mode-specific adapters.

---

## 3. Technology stack

### Backend

- FastAPI and Uvicorn.
- Pydantic 2 and `pydantic-settings`.
- SQLite in WAL mode.
- PyMuPDF (`fitz`) and `pdfplumber` for PDF parsing.
- `python-docx` for DOCX parsing.
- Pillow and `imagehash` for icon detection.
- scikit-learn `TfidfVectorizer` and cosine similarity for semantic chunking.
- Loguru for console, file, and SQLite logging.
- `asyncio.to_thread` and an in-memory `JobManager`.

### Frontend

- React 19 and React DOM.
- TypeScript.
- Vite.
- `react-router-dom`.
- Tailwind CSS v3.
- CSS variables for dark and light themes.
- TanStack Query for server state.
- React Hook Form and Zod for forms.
- Zustand for small UI-only state.
- PDF.js for original-document viewing.
- TipTap for rich-text editing.
- `lucide-react`, `framer-motion`, and `react-file-icon`.
- Vitest, React Testing Library, Mock Service Worker, and Playwright.
- `oxlint` for frontend linting.

---

# Part I: FastAPI Backend Specification

## 4. Backend project structure

```text
backend/
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── documents.py
│   │   ├── jobs.py
│   │   ├── sops.py
│   │   ├── review.py
│   │   ├── translations.py
│   │   ├── migrations.py
│   │   ├── suggestions.py
│   │   ├── issues.py
│   │   ├── reprocessing.py
│   │   ├── assets.py
│   │   └── logs.py
│   ├── core/
│   │   ├── config.py
│   │   ├── errors.py
│   │   ├── logging.py
│   │   ├── middleware.py
│   │   └── security.py
│   ├── jobs/
│   │   ├── manager.py
│   │   └── models.py
│   ├── extraction/
│   │   ├── metadata.py
│   │   ├── parsers.py
│   │   ├── tables.py
│   │   ├── stitcher.py
│   │   ├── icons.py
│   │   ├── captions.py
│   │   ├── ast.py
│   │   ├── chunking.py
│   │   └── exporter.py
│   ├── workflows/
│   │   ├── translation.py
│   │   ├── migration.py
│   │   ├── suggestions.py
│   │   └── validation.py
│   ├── stores/
│   │   ├── sop_store.py
│   │   ├── workflow_store.py
│   │   └── log_store.py
│   └── schemas/
├── data/
└── tests/
```

Routers validate transport data and return response models. Extraction, translation, migration, issue, and reprocessing business logic belongs in services and workflow modules, not in routers.

---

## 5. Configuration

`Settings` uses `pydantic_settings.BaseSettings`, environment prefix `SOP_`, and an optional `.env` file.

```text
upload_dir = data/uploads
extracted_images_dir = data/extracted_images
extracted_icons_dir = data/extracted_icons
temp_dir = data/temp
output_dir = data/output
log_dir = data/logs
log_file_path = data/logs/app.log
error_file_path = data/logs/error.log
log_db_path = data/logs/logs.db
sop_db_path = data/sop_records.db
workflow_db_path = data/workflow.db
max_upload_size_mb = 50
allowed_extensions = [".pdf", ".docx"]
table_stitch_enabled = true
table_stitch_score_threshold = configurable
table_stitch_column_tolerance_pt = configurable
table_stitch_bottom_zone_pct = configurable
table_stitch_top_zone_pct = configurable
watermark_keywords = configurable list
log_level = INFO
job_concurrency = 1
job_poll_interval_seconds = 1.5
log_retention_days = 14
```

All relative paths are resolved against `project_root`. `ensure_directories()` creates every required directory during application startup.

---

## 6. Filesystem layout

```text
data/
├── uploads/{document_id}.{pdf|docx}
├── output/{document_id}_v2.json
├── output/translations/{translation_id}.json
├── output/translations/{translation_id}.{pdf|docx}
├── output/migrations/{migration_id}.json
├── output/migrations/{migration_id}.{pdf|docx}
├── extracted_images/{document_id}/{page}_{img|vec}{n}_{hash}.png
├── extracted_icons/{document_id}/{page}_{img|vec}{n}_{hash}.png
├── temp/
├── logs/app.log
├── logs/error.log
├── logs/logs.db
├── sop_records.db
└── workflow.db
```

Release 1 extraction source and v2 JSON filenames are unversioned. Database rows retain `gpdat_version` history, but shared physical files represent the latest re-upload. Translation and migration workflow outputs use workflow-specific IDs so approved outputs remain independently addressable.

---

## 7. SQLite schemas

### 7.1 SOP records

```sql
CREATE TABLE IF NOT EXISTS sop_records (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id           TEXT    NOT NULL,
    document_uid     TEXT    NOT NULL,
    document_number  TEXT,
    document_name    TEXT,
    document_title   TEXT,
    document_version TEXT,
    document_type    TEXT,
    file_type        TEXT,
    language         TEXT    DEFAULT 'en',
    page_count       INTEGER DEFAULT 0,
    gpdat_version    INTEGER DEFAULT 0,
    status           TEXT    NOT NULL DEFAULT 'in_review'
                     CHECK(status IN ('in_review','approved','rejected')),
    source_filename  TEXT,
    output_path      TEXT,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL,
    UNIQUE(document_uid, gpdat_version)
);

CREATE INDEX IF NOT EXISTS idx_sop_uid ON sop_records(document_uid);
CREATE INDEX IF NOT EXISTS idx_sop_status ON sop_records(status);
CREATE INDEX IF NOT EXISTS idx_sop_job ON sop_records(job_id);
```

Release 1 defaults a new extraction to `in_review`, because approval requires a reviewer. If compatibility with an earlier build requires `approved`, expose `SOP_DEFAULT_REVIEW_STATUS`, but `in_review` is the recommended authoritative value.

Upsert updates metadata but never silently resets an existing reviewer status.

### 7.2 Workflow records

```sql
CREATE TABLE IF NOT EXISTS workflow_runs (
    id                TEXT PRIMARY KEY,
    document_uid      TEXT NOT NULL,
    sop_record_id     INTEGER NOT NULL,
    workflow_type     TEXT NOT NULL
                      CHECK(workflow_type IN ('extraction','translation','migration')),
    workflow_version  INTEGER NOT NULL DEFAULT 1,
    status            TEXT NOT NULL,
    source_version    INTEGER,
    source_language   TEXT,
    target_language   TEXT,
    template_id       TEXT,
    template_version  INTEGER,
    draft_path        TEXT,
    output_path       TEXT,
    created_at        TEXT NOT NULL,
    created_by        TEXT,
    updated_at        TEXT NOT NULL,
    updated_by        TEXT,
    approved_at       TEXT,
    approved_by       TEXT,
    row_version       INTEGER NOT NULL DEFAULT 1,
    UNIQUE(document_uid, workflow_type, workflow_version)
);

CREATE INDEX IF NOT EXISTS idx_workflow_document ON workflow_runs(document_uid);
CREATE INDEX IF NOT EXISTS idx_workflow_type_status ON workflow_runs(workflow_type, status);
```

### 7.3 AI suggestions

```sql
CREATE TABLE IF NOT EXISTS ai_suggestions (
    id              TEXT PRIMARY KEY,
    workflow_id     TEXT NOT NULL,
    entity_id       TEXT,
    action          TEXT NOT NULL,
    instruction     TEXT,
    base_revision   INTEGER NOT NULL,
    patch_json      TEXT NOT NULL,
    explanation     TEXT,
    status          TEXT NOT NULL
                    CHECK(status IN ('proposed','accepted','rejected','expired')),
    model_metadata  TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    created_by      TEXT,
    decided_at      TEXT,
    decided_by      TEXT
);
```

### 7.4 Issues

```sql
CREATE TABLE IF NOT EXISTS issues (
    id                  TEXT PRIMARY KEY,
    document_uid        TEXT NOT NULL,
    workflow_type       TEXT NOT NULL,
    workflow_id         TEXT NOT NULL,
    entity_type         TEXT,
    entity_id           TEXT,
    category            TEXT NOT NULL,
    description         TEXT NOT NULL,
    expected_value      TEXT,
    source_anchor_json  TEXT,
    status              TEXT NOT NULL,
    assigned_to         TEXT,
    resolution          TEXT,
    created_at          TEXT NOT NULL,
    created_by          TEXT NOT NULL,
    updated_at          TEXT NOT NULL,
    updated_by          TEXT NOT NULL
);
```

### 7.5 Reprocessing requests

```sql
CREATE TABLE IF NOT EXISTS reprocessing_requests (
    id                   TEXT PRIMARY KEY,
    document_uid         TEXT NOT NULL,
    sop_record_id        INTEGER NOT NULL,
    workflow_id          TEXT NOT NULL,
    requested_scope      TEXT NOT NULL,
    requested_pages_json TEXT,
    options_json         TEXT NOT NULL,
    reason               TEXT NOT NULL,
    status               TEXT NOT NULL,
    requested_at         TEXT NOT NULL,
    requested_by         TEXT NOT NULL,
    decided_at           TEXT,
    decided_by           TEXT,
    decision_comment     TEXT,
    job_id               TEXT
);
```

### 7.6 Audit events

```sql
CREATE TABLE IF NOT EXISTS audit_events (
    id             TEXT PRIMARY KEY,
    actor_id       TEXT,
    action         TEXT NOT NULL,
    resource_type  TEXT NOT NULL,
    resource_id    TEXT NOT NULL,
    before_json    TEXT,
    after_json     TEXT,
    metadata_json  TEXT,
    request_id     TEXT,
    created_at     TEXT NOT NULL
);
```

### 7.7 Structured logs

`logs.db` runs in WAL mode. Log rows include timestamp, level, service, message, request ID, job ID, document ID, workflow ID, stage, duration, and safe exception metadata. Rows older than 14 days are pruned.

---

## 8. Domain errors

Handled errors subclass `AppError`.

```json
{
  "error": "file_too_large",
  "message": "The selected file exceeds the permitted size.",
  "detail": "Maximum file size is 50 MB.",
  "path": "/documents/upload/batch",
  "request_id": "a1b2c3d4e5f6"
}
```

Mappings:

```text
BadRequestError              400 bad_request
UnsupportedFileTypeError     415 unsupported_file_type
FileTooLargeError            413 file_too_large
EmptyFileError               400 empty_file
DocumentNotFoundError        404 document_not_found
ParsingError                 422 parsing_error
SopRecordNotFoundError       404 sop_record_not_found
WorkflowNotFoundError        404 workflow_not_found
VersionConflictError         409 version_conflict
PermissionDeniedError        403 permission_denied
RequestValidationError       422 validation_error
Unhandled Exception          500 internal_error
```

---

## 9. Metadata pre-extraction and deterministic ID

`SOPMetadataExtractor` reads raw bytes before the full pipeline to create a stable identifier and upload preview.

### PDF rules

- Read first-page tables with `pdfplumber`.
- Match label cells through case-insensitive whole-word patterns.
- If fields remain missing, search raw first-page text with PyMuPDF regular expressions.

### DOCX rules

- Inspect the first three tables.
- Inspect the first twenty paragraphs.
- Apply the same label matching and regex fallback.

### Label groups

```text
Title: document title, title
Name: document name, doc name
Number: document number, doc number, doc no, sop number, document id
Version: version, ver, rev, revision
Type: type/subtype, type, subtype, document type, doc type
```

A trailing cell containing another `Label: value` pair is parsed separately. `_clean_cell_value` removes any standalone line containing no more than two alphabetic characters to reduce watermark fragments.

### ID generation

1. Sanitize document number, name, and version to `[A-Za-z0-9_\-.]`.
2. Replace other characters with underscore.
3. Collapse repeated underscores.
4. Trim separators.
5. Use filename stem when document name is empty.
6. Defaults: `DOC`, `UNKNOWN`, and `1.0`.

```python
document_id = f"{number}_{name}_v{version}"
```

---

## 10. Extraction pipeline

Each stage is executed with `asyncio.to_thread` and `logger.contextualize(stage=...)`.

```text
1. Locate     20%  Find data/uploads/{document_id}{ext}
2. Parse      40%  ParserFactory -> PdfParser or DocxParser
3. Tables           TableExtractor
4. Stitch           CrossPageTableStitcher
5. Icons            IconExtractor
6. Captions   65%  CaptionExtractor
7. AST        80%  ASTBuilder
8. Chunk      90%  HierarchicalChunker -> SemanticChunker
9. Export    100%  MigrationExporter + sop_store.upsert_record
```

### Requirements

- Parse pages into headings, paragraphs, lists, tables, images, and icons.
- Preserve reading order.
- Refine merged table cells.
- Merge cross-page tables using configured scoring and column tolerance.
- Reclassify small images through perceptual hashing and heuristics.
- Associate `Figure N:` and `Table N:` captions.
- Build a typed document tree.
- Produce section chunks refined through TF-IDF similarity.
- Export v2 JSON and upsert the SOP record.

### Export traversal rules

- Suppress configured running headers, footers, and watermarks.
- A heading matching `^(\d+)\s+([A-Z0-9\s&/\-_,]+)$` begins a top-level section.
- Other headings remain in-section heading elements.
- Buffer an icon and attach it to the next element.
- Attach a remaining orphan icon to the final element.
- Serialize only merge-origin table cells with explicit row and column spans.
- Stamp every element with its parent `section_name`.
- Rewrite asset paths to HTTP URLs before returning JSON.

On exception, the document job becomes `failed`. A batch becomes `completed` only when every document succeeds; otherwise it becomes `failed` after all documents reach a terminal state.

---

## 11. V2 content JSON contract

```text
DocxMigrationOutput
├── version: string
├── document_Uid: string
├── metadata: MigrationMetadata
└── sections: MigrationSection[]

MigrationMetadata
├── document_Uid
├── document_number
├── document_name
├── document_title
├── document_version
├── document_type
├── file_type
├── language
├── page_count
└── gpdat_version

MigrationSection
├── section_number
├── title
├── page_start
├── page_end
└── elements

MigrationElement
├── element_type: heading | paragraph | list | table | image
├── page
├── section_name
├── level
├── text
├── icons
├── items
├── title
├── num_rows
├── num_cols
├── cells
└── image_path
```

Example:

```json
{
  "version": "3.1",
  "document_Uid": "BI-VQD-24416_BI-VQD-24416-G_v3.0",
  "metadata": {
    "document_Uid": "BI-VQD-24416_BI-VQD-24416-G_v3.0",
    "document_number": "BI-VQD-24416",
    "document_name": "BI-VQD-24416-G",
    "document_title": "Good Writing Practice for Governance and Procedure Documents",
    "document_version": "3.0",
    "document_type": "Governance and Procedure > Guidance",
    "file_type": "pdf",
    "language": "en",
    "page_count": 15,
    "gpdat_version": 1
  },
  "sections": [
    {
      "section_number": "0",
      "title": "PREAMBLE",
      "page_start": 1,
      "page_end": 2,
      "elements": [
        {
          "element_type": "table",
          "page": 1,
          "section_name": "PREAMBLE",
          "num_rows": 8,
          "num_cols": 2,
          "cells": [
            {
              "row_index": 0,
              "col_index": 0,
              "row_span": 1,
              "col_span": 1,
              "text": "Scope",
              "is_header": true
            }
          ]
        }
      ]
    }
  ]
}
```

The Review Page may consume an extended canonical JSON with confidence and source bounding boxes. The v2 contract remains available to preserve Content Viewer compatibility.

---

## 12. Job schemas

```python
class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class RejectedFile(BaseModel):
    filename: str
    reason: str

class DocumentJob(BaseModel):
    document_id: str
    filename: str
    status: JobStatus = JobStatus.QUEUED
    progress_percentage: int = 0
    message: str = "Queued for processing"
    result: dict | None = None
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

class BatchJob(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.QUEUED
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    documents: list[DocumentJob] = []
    rejected_files: list[RejectedFile] = []
```

Jobs are in memory for Release 1 and are lost on API restart. SQLite remains the durable source of completed SOP records and workflows.

---

## 13. REST API reference

### Health

```text
GET /health
```

```json
{"status":"healthy","service":"sop-migration-system","version":"1.0.0"}
```

### Batch upload and jobs

```text
POST /documents/upload/batch
GET  /jobs/{job_id}
WS   /jobs/{job_id}/progress
```

`POST /documents/upload/batch` accepts repeatable multipart field `files`. Each file is independently validated. If no file survives, return `400`. Otherwise return `BatchJob` with accepted documents and rejected files.

### SOP Repository

```text
GET    /sops
GET    /sops/{record_id}
PATCH  /sops/{record_id}/status
DELETE /sops/{record_id}
```

`GET /sops` supports `status`, `document_Uid`, `limit`, and `offset`. Newest records appear first.

Review statuses:

```text
in_review | approved | rejected
```

### Content and assets

```text
GET /documents/v2/{document_id}/json
GET /documents/{document_id}/assets/{filename}
GET /documents/{document_id}
GET /documents/{document_id}/elements?page=
GET /documents/{document_id}/tree
GET /documents/{document_id}/chunks
POST /documents/extract
```

Asset serving uses `basename(filename)` to neutralize path traversal, checks extracted images first, then extracted icons.

### Common Review Page

```text
GET /review/{record_id}?mode=review&workflowId={id}
GET /review/{record_id}?mode=translation&workflowId={id}
GET /review/{record_id}?mode=migration&workflowId={id}
```

The response contains document metadata, workflow context, layout configuration, `availableActions`, and links.

### Extraction edits and approval

```text
GET   /extractions/{workflow_id}
GET   /extractions/{workflow_id}/content
PATCH /extractions/{workflow_id}/entities/{entity_id}
POST  /extractions/{workflow_id}/approve
```

### Translation

```text
POST  /translations
GET   /translations/{workflow_id}
GET   /translations/{workflow_id}/segments
PATCH /translations/{workflow_id}/segments/{segment_id}
POST  /translations/{workflow_id}/ai-translate
POST  /translations/{workflow_id}/qa
POST  /translations/{workflow_id}/approve
```

### Migration

```text
POST  /migrations
GET   /migrations/{workflow_id}
GET   /migrations/{workflow_id}/sections
PATCH /migrations/{workflow_id}/sections/{section_id}
POST  /migrations/{workflow_id}/ai-migrate
POST  /migrations/{workflow_id}/validate
POST  /migrations/{workflow_id}/approve
```

### AI suggestions

```text
GET  /suggestions/{suggestion_id}
POST /suggestions/{suggestion_id}/accept
POST /suggestions/{suggestion_id}/reject
```

### Issues

```text
POST  /issues
GET   /issues
GET   /issues/{issue_id}
PATCH /issues/{issue_id}
POST  /issues/{issue_id}/comments
POST  /issues/{issue_id}/resolve
POST  /issues/{issue_id}/reopen
```

### Reprocessing approval

```text
POST /extractions/{workflow_id}/reprocessing-requests
GET  /reprocessing-requests
GET  /reprocessing-requests/{request_id}
POST /reprocessing-requests/{request_id}/approve
POST /reprocessing-requests/{request_id}/reject
```

Approval queues a new extraction job. Rejection requires a comment and does not alter the current version.

### Versions and comparison

```text
GET  /workflows/{workflow_id}/versions
POST /versions/compare
```

### Downloads

```text
POST /downloads
GET  /downloads/{download_id}
```

---

## 14. Review bootstrap response

```json
{
  "document": {
    "recordId": 1,
    "documentUid": "BI-VQD-24416_BI-VQD-24416-G_v3.0",
    "title": "Good Writing Practice for Governance and Procedure Documents",
    "sopNumber": "BI-VQD-24416",
    "version": "3.0",
    "fileType": "pdf",
    "pageCount": 15
  },
  "reviewContext": {
    "mode": "translation",
    "workflowId": "trn_03",
    "workflowVersion": 1,
    "status": "in_review",
    "sourceLocale": "en",
    "targetLocale": "fr",
    "rowVersion": 4
  },
  "layout": {
    "leftPanel": "SOURCE_CONTENT",
    "rightPanel": "TRANSLATED_CONTENT",
    "showOriginalViewer": true,
    "showAiSuggestions": true,
    "showCompareView": true,
    "showVersionHistory": true,
    "showIssuePanel": true
  },
  "availableActions": [
    "AI_TRANSLATE",
    "ACCEPT_SUGGESTION",
    "EDIT",
    "SAVE",
    "RUN_QA",
    "APPROVE"
  ],
  "links": {
    "content": "/translations/trn_03/segments",
    "versions": "/workflows/trn_03/versions",
    "issues": "/issues?workflow_id=trn_03",
    "websocket": "/workflows/trn_03/progress"
  }
}
```

---

## 15. WebSocket contracts

### Batch job progress

```text
WS /jobs/{job_id}/progress
```

The server sends the full `BatchJob` every second. Unknown jobs close with code `1008`. The socket closes normally after `completed` or `failed`.

### Workflow progress

```text
WS /workflows/{workflow_id}/progress
```

Envelope:

```json
{
  "event_id": "evt_01",
  "event_type": "workflow.progress",
  "sequence": 18,
  "occurred_at": "2026-08-28T08:55:32Z",
  "workflow_id": "trn_03",
  "document_uid": "BI-VQD-24416_BI-VQD-24416-G_v3.0",
  "payload": {
    "stage": "TRANSLATING_SEGMENTS",
    "progress_percentage": 62,
    "message": "Translating section 8 of 13"
  }
}
```

Events include job queued, started, progress, warning, completed, failed, suggestion created, QA completed, migration validated, reprocessing approved, and download ready.

---

## 16. Translation pipeline

1. Load approved extraction content.
2. Snapshot source language, target language, glossary, and AI instruction version.
3. Segment paragraphs, lists, headings, and table cells while preserving structure.
4. Protect SOP IDs, product codes, URLs, variables, and configured terminology.
5. Retrieve translation-memory matches.
6. Call the AI gateway for unmatched content.
7. Store proposed translations and provenance.
8. Restore formatting and inline marks.
9. Run QA rules.
10. Open Translation mode in the common Review Page.
11. Save edits as a new draft revision.
12. Approve and render output.

QA rules include missing translation, number mismatch, unit mismatch, punctuation mismatch, modified protected term, missing glossary term, formatting mismatch, inconsistent translation, excessive length, and possible untranslated source text.

AI output is always reviewable. AI output never silently modifies approved content.

---

## 17. Migration pipeline

1. Load approved extraction version.
2. Snapshot target template and AI instruction versions.
3. Map source sections to target template keys.
4. Detect missing required, optional, and unsupported sections.
5. Transform headings, numbering, metadata, tables, and references.
6. Preserve source-to-target provenance.
7. Ask the AI gateway for uncertain mappings or rewrites.
8. Store AI results as proposed patches.
9. Create editable migration sections.
10. Validate required content and rendering readiness.
11. Open Migration mode in the common Review Page.
12. Approve and render DOCX/PDF output.

---

## 18. Smart cleanup

`DELETE /sops/{record_id}` deletes the database row and counts remaining rows for the same `document_uid`.

```text
Sibling versions remain -> retain shared files
No sibling versions     -> best-effort delete:
                           data/uploads/{document_id}{ext}
                           data/output/{document_id}_v2.json
                           data/extracted_images/{document_id}
                           data/extracted_icons/{document_id}
```

Cleanup failure is logged and does not reverse a successful database deletion.

---

## 19. Middleware and startup

- CORS allows configured frontend origins, including local Vite origins.
- Every response carries `X-Request-ID`.
- Incoming `X-Request-ID` is reused or a new 12-character hexadecimal ID is generated.
- Logging is contextualized with request, job, document, workflow, and stage.
- Typed domain errors, request validation errors, and unhandled errors are centrally mapped.
- Startup configures logging, creates directories, initializes SQLite stores, creates `JobManager(settings, concurrency=1)`, and starts the worker.
- Shutdown drains or safely stops workers and closes stores.

---

# Part II: React Frontend and Tailwind CSS Specification

## 20. Frontend structure

```text
frontend/
├── src/
│   ├── App.tsx
│   ├── main.tsx
│   ├── types.ts
│   ├── styles/globals.css
│   ├── lib/
│   │   ├── api.ts
│   │   ├── useJobPolling.ts
│   │   ├── useWorkflowSocket.ts
│   │   ├── useAutosave.ts
│   │   ├── stats.ts
│   │   ├── sopDisplay.ts
│   │   ├── format.ts
│   │   └── theme.ts
│   ├── components/
│   │   ├── layout/
│   │   ├── ui/
│   │   ├── repository/
│   │   ├── content/
│   │   ├── document/
│   │   ├── review/
│   │   ├── ai/
│   │   └── editor/
│   └── pages/
│       ├── SopRepository.tsx
│       ├── SopContentView.tsx
│       ├── ReviewPage.tsx
│       └── ReprocessingAdminPage.tsx
├── tailwind.config.ts
└── vite.config.ts
```

---

## 21. Routing

```tsx
<BrowserRouter>
  <Routes>
    <Route path="/" element={<SopRepository />} />
    <Route path="/sops/:recordId" element={<SopContentView />} />
    <Route path="/review/:recordId" element={<ReviewPage />} />
    <Route path="/admin/reprocessing" element={<ReprocessingAdminPage />} />
  </Routes>
</BrowserRouter>
```

Examples:

```text
/review/1025?mode=review&workflowId=ext_04
/review/1025?mode=translation&workflowId=trn_03
/review/1025?mode=migration&workflowId=mig_02
```

---

## 22. Common Review Page component hierarchy

```text
ReviewPage
├── ReviewHeader
├── DocumentMetadata
├── ReviewWorkspace
│   ├── ExtractionReviewMode
│   ├── TranslationReviewMode
│   └── MigrationReviewMode
├── OriginalDocumentViewer
├── ContentEditor
├── AISuggestionPanel
├── CompareView
├── VersionHistory
├── IssuePanel
├── StatusIndicator
└── ActionFooter
```

The page reads `recordId`, `mode`, and `workflowId`, calls the review bootstrap endpoint, loads linked content, and renders only the configured components and actions.

### Extraction Review

```text
Original SOP | Extracted Content | AI and Warnings
```

Actions: Edit, Save, Report Issue, Request Reprocessing, Resolve Warning, Approve.

### Translation

```text
Source Content | Translated Content | AI, Glossary, and QA
```

Actions: AI Translate, Accept or Reject Suggestion, Edit, Save, Apply Glossary, Run QA, Approve.

### Migration

```text
Current Format | Migrated Format | AI and Validation
```

Actions: AI Migration, Accept or Reject Suggestion, Edit, Apply Template, Validate, Save, Render Preview, Approve.

---

## 23. Tailwind configuration

```typescript
import type { Config } from "tailwindcss";

export default {
  darkMode: ["class", "[data-theme='dark']"],
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        app: "var(--bg-main)",
        card: "var(--bg-card)",
        sidebar: "var(--sidebar-bg)",
        border: "var(--border)",
        primary: "var(--primary)",
        "primary-dark": "var(--primary-dark)",
        "text-main": "var(--text-main)",
        "text-muted": "var(--text-muted)"
      },
      boxShadow: {
        panel: "0 16px 40px rgba(0,0,0,.26)",
        glow: "0 0 0 1px rgba(0,228,124,.16), 0 0 24px rgba(0,228,124,.08)"
      },
      spacing: {
        sidebar: "224px",
        "sidebar-collapsed": "72px",
        header: "64px"
      }
    }
  },
  plugins: [require("@tailwindcss/forms"), require("@tailwindcss/typography")]
} satisfies Config;
```

---

## 24. Global CSS and design tokens

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

[data-theme='dark'] {
  --primary: #00e47c;
  --primary-dark: #00c86d;
  --bg-main: #041c19;
  --bg-card: #082f2a;
  --bg-card-hover: #0b3932;
  --text-main: #ffffff;
  --text-muted: #94a3b8;
  --border: rgba(255,255,255,0.08);
  --sidebar-bg: #031713;
  --nav-active-bg: rgba(0,228,124,0.15);
  --warning: #f59e0b;
  --danger: #ef4444;
  --info: #3b82f6;
}

[data-theme='light'] {
  --primary: #169949;
  --primary-dark: #08783b;
  --bg-main: #ffffff;
  --bg-card: #f8fafc;
  --bg-card-hover: #f1f5f9;
  --text-main: #0f172a;
  --text-muted: #475569;
  --border: #e2e8f0;
  --sidebar-bg: #ffffff;
  --nav-active-bg: rgba(22,153,73,0.10);
  --warning: #d97706;
  --danger: #dc2626;
  --info: #2563eb;
}

@layer base {
  html { min-width: 320px; min-height: 100%; }
  body {
    min-width: 320px;
    min-height: 100vh;
    margin: 0;
    overflow-x: hidden;
    background: var(--bg-main);
    color: var(--text-main);
    font-family: Inter, ui-sans-serif, system-ui, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }
  #root { min-height: 100vh; }
  * { box-sizing: border-box; border-color: var(--border); }
  button, input, textarea, select { font: inherit; }
  *:focus-visible {
    outline: none;
    box-shadow: 0 0 0 2px var(--bg-main), 0 0 0 4px var(--primary);
  }
  ::selection { background: rgba(0,228,124,.3); }
  ::-webkit-scrollbar { width: 8px; height: 8px; }
  ::-webkit-scrollbar-track { background: var(--sidebar-bg); }
  ::-webkit-scrollbar-thumb { border-radius: 999px; background: rgba(148,163,184,.35); }
}

@layer components {
  .app-shell { @apply h-screen overflow-hidden bg-app text-text-main; }
  .app-main { @apply h-full overflow-hidden pl-sidebar; }
  .content-pane { @apply h-full overflow-y-auto px-6 py-5; }
  .dashboard-card { @apply rounded-xl border border-border bg-card shadow-panel; }
  .panel-header { @apply flex min-h-12 items-center justify-between border-b border-border px-4 py-3; }
  .page-title { @apply text-3xl font-semibold tracking-tight text-text-main; }
  .page-description { @apply mt-1 text-sm text-text-muted; }

  .btn { @apply inline-flex h-10 items-center justify-center gap-2 rounded-md border px-4 text-sm font-medium transition disabled:pointer-events-none disabled:opacity-45; }
  .btn-primary { @apply btn border-primary bg-primary text-slate-950 hover:bg-primary-dark; }
  .btn-secondary { @apply btn border-border bg-transparent text-text-main hover:bg-white/5; }
  .btn-ghost { @apply btn border-transparent bg-transparent text-text-muted hover:bg-white/5 hover:text-text-main; }
  .btn-danger { @apply btn border-red-500/40 bg-red-500/10 text-red-300 hover:bg-red-500/20; }
  .btn-icon { @apply inline-flex size-10 items-center justify-center rounded-md border border-border bg-transparent text-text-muted hover:bg-white/5 hover:text-text-main; }

  .field { @apply h-10 w-full rounded-md border border-border bg-black/10 px-3 text-sm text-text-main placeholder:text-text-muted focus:border-primary focus:ring-1 focus:ring-primary; }
  .field-label { @apply mb-1.5 block text-xs font-medium text-text-main; }
  .field-error { @apply mt-1 text-xs text-red-400; }

  .status-pill { @apply inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium; }
  .status-approved { @apply status-pill bg-emerald-500/15 text-emerald-300; }
  .status-processing { @apply status-pill bg-blue-500/15 text-blue-300; }
  .status-review { @apply status-pill bg-amber-500/15 text-amber-300; }
  .status-rejected { @apply status-pill bg-red-500/15 text-red-300; }
  .status-draft { @apply status-pill bg-violet-500/15 text-violet-300; }

  .summary-card { @apply dashboard-card flex min-h-28 items-center gap-4 px-5 py-4 transition hover:shadow-glow; }
  .summary-icon { @apply grid size-11 shrink-0 place-items-center rounded-lg border border-primary/20 bg-primary/10 text-primary; }
  .filter-chip { @apply inline-flex h-8 items-center gap-2 rounded-md border border-border bg-white/5 px-3 text-xs text-text-muted; }
  .sidebar-item { @apply flex min-h-12 items-center gap-3 rounded-md px-3 text-sm text-text-muted transition hover:bg-white/5 hover:text-text-main; }
  .sidebar-item-active { background: var(--nav-active-bg); color: var(--primary); }

  .table-header-cell { @apply h-11 whitespace-nowrap border-b border-border bg-black/10 px-4 text-left text-xs font-medium text-text-muted; }
  .table-cell { @apply border-b border-border px-4 py-3 text-sm text-text-muted; }
  .table-row { @apply transition hover:bg-white/[0.025]; }

  .editor-paper { @apply min-h-72 rounded-md bg-white p-5 text-slate-900 shadow-inner; }
  .warning-panel { @apply rounded-lg border border-amber-500/30 bg-amber-500/[0.06] p-4; }
  .error-panel { @apply rounded-lg border border-red-500/30 bg-red-500/[0.06] p-4; }
  .sticky-action-bar { @apply sticky bottom-0 z-30 flex min-h-16 items-center justify-between gap-4 border-t border-border bg-card/95 px-6 py-3 backdrop-blur; }
}

@media (max-width: 1279px) {
  .app-main { padding-left: 72px; }
}

@media (max-width: 767px) {
  .app-main { padding-left: 0; }
  .content-pane { padding: 12px; }
  .sticky-action-bar { padding-inline: 12px; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: .01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: .01ms !important;
  }
}
```

Theme is stored in `localStorage` under `gpdat.theme` and applied through `data-theme` on `<html>`.

---

## 25. Application shell

### Layout

- Root uses `h-screen overflow-hidden`.
- Sidebar uses `h-full`.
- Main content pane uses `h-full overflow-y-auto`.
- This bounded layout ensures the sidebar, section navigation, document viewer, and review editor can scroll independently.

### Sidebar

- 224px expanded and 72px collapsed.
- Dark navy/teal background.
- GP-DAT brand and Platform v1.0.
- Dashboard, Documents, Templates, Glossary, AI Instructions.
- Migration, Translation, SOP Extraction.
- User Management, Model Settings, Audit Logs, System Settings.
- Emerald selected item.
- Mobile drawer.

### Header

- Breadcrumb.
- Notification and help actions.
- Theme toggle.
- User avatar and account menu.
- Sticky translucent background.

---

## 26. SOP Repository page

### Hierarchy

1. Breadcrumb, GP-DAT eyebrow, title, subtitle.
2. Theme toggle and Upload SOPs button.
3. Five KPI cards: Total SOPs, Completed, Processing, Needs Review, Failed.
4. Batch progress banner.
5. Search input and list/grid toggle.
6. Status and file-type filters.
7. Table or card results.
8. Upload, delete, and toast overlays.

### Data behavior

- On mount, call `GET /sops?limit=1000`.
- Search title, name, number, and filename.
- Status and file-type filters combine with AND logic.
- Upload stores `activeJobId` and polls every 1500ms.
- On terminal job status, refresh `/sops` exactly once.
- Delete optimistically removes the row and shows a toast.
- Processing and failed job KPIs reset after reload because Release 1 jobs are in memory.

### Table columns

```text
SOP | Type | Pages | Review Status | Extraction Results | Uploaded | Updated | Actions
```

Actions:

- View Content.
- Open Review.
- Start Translation.
- Start Migration.
- View Versions.
- Download JSON.
- Delete.

---

## 27. Batch upload UI

`UploadSops` provides drag-and-drop and file selection.

- Accept `.pdf` and `.docx`.
- Maximum 50 MB per file by default.
- Validate extension immediately in the browser.
- Show file name, size, validation state, progress, remove, and retry.
- Allow partial acceptance.
- Workflow selection: extraction only, extraction plus translation, or extraction plus migration.
- Translation options: target language and glossary.
- Migration options: template and template version.
- On submit call `POST /documents/upload/batch`.
- Display rejected files without hiding accepted files.
- Open `JobProgressBanner` after submission.

---

## 28. Content Viewer

Route:

```text
/sops/:recordId
```

Data flow:

1. Fetch `GET /sops/{recordId}`.
2. Fetch `GET /documents/v2/{record.document_Uid}/json`.
3. Set active section to zero.
4. Render one section at a time.

Layout:

- Back to Repository.
- File icon, display title, and display subline.
- Review Status badge and Approve, Needs Review, Reject actions.
- Left sticky `SectionNav` with section number, title, and count.
- Right `ElementRenderer` for the active section.
- Previous, Next, and N of M controls.

`ElementRenderer` supports headings, paragraphs, lists, tables, images, icons, captions, merged cells, and an unsupported-type fallback.

---

## 29. Common Review Page visual behavior

Desktop layout:

```text
Extraction: 34% Original | 42% Content | 24% AI and Warnings
Translation: 21% Navigation | 54% Source/Target | 25% AI/Glossary/QA
Migration:   21% Navigation | 54% Current/Migrated | 25% AI/Validation
```

### Shared components

- `ReviewHeader`: title, metadata, status, View Original, Download, More.
- `DocumentMetadata`: common and mode-specific fields.
- `OriginalDocumentViewer`: PDF.js, thumbnails, page controls, zoom, source highlights.
- `ContentEditor`: adapter-based editing with 800ms autosave.
- `AISuggestionPanel`: prompt, quick actions, cards, diff, Accept, Reject.
- `CompareView`: added emerald, removed red, modified amber.
- `VersionHistory`: open, compare, identify draft/approved, restore as new draft.
- `IssuePanel`: create, comment, assign, resolve, reopen.
- `StatusIndicator`: label, icon, progress, stage, warnings, error.
- `ActionFooter`: actions from backend `availableActions`.

### Optimistic concurrency

- Send `row_version` with save.
- One save at a time per entity.
- Keep only the newest pending local editor state.
- On `409`, show Reload Latest, Compare Changes, Copy My Changes, and Close.
- Never discard local edits automatically.

---

## 30. Component inventory

```text
Layout
Sidebar
AppHeader
StatCards
SearchBar
FilterBar
SopList
SopTable
SopGrid
UploadSops
JobProgressBanner
StatusBadge
FileTypeIcon
ThemeToggle
ConfirmDialog
ToastStack
Button
SectionNav
ElementRenderer
ReviewPage
ReviewHeader
DocumentMetadata
OriginalDocumentViewer
ContentEditor
AISuggestionPanel
CompareView
VersionHistory
IssuePanel
StatusIndicator
ActionFooter
ExtractionReviewMode
TranslationReviewMode
MigrationReviewMode
GlossaryPanel
TranslationQaPanel
MigrationValidationPanel
ReprocessingRequestDialog
ReprocessingAdminQueue
```

Every component must define loading, empty, error, disabled, permission, and mobile states where applicable. Icon-only actions require an accessible name and tooltip.

---

## 31. TypeScript contracts

```typescript
type SopStatus = "in_review" | "approved" | "rejected";
type JobStatus = "queued" | "processing" | "completed" | "failed";
type ReviewMode = "review" | "translation" | "migration";
type SuggestionStatus = "proposed" | "accepted" | "rejected" | "expired";

interface SopRecord {
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

interface DocumentJob {
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

interface BatchJob {
  job_id: string;
  status: JobStatus;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  documents: DocumentJob[];
  rejected_files: Array<{ filename: string; reason: string }>;
}
```

---

# Part III: End-to-End Flows

## 32. Upload to Repository refresh

1. User chooses PDF or DOCX files.
2. Browser rejects invalid extensions.
3. Frontend posts multipart files.
4. Backend validates each file independently.
5. Metadata pre-extraction computes document ID.
6. Accepted files are written to uploads.
7. Backend creates an in-memory batch job.
8. Frontend polls every 1.5 seconds.
9. The single worker processes documents sequentially.
10. Each successful extraction writes v2 JSON and upserts an SOP row.
11. Batch status becomes completed or failed.
12. Polling stops and the repository refreshes exactly once.

---

## 33. Extraction Review flow

1. User selects Open Review.
2. Frontend navigates to `/review/{recordId}?mode=review&workflowId={id}`.
3. Bootstrap loads metadata, layout, actions, content links, and status.
4. User selects an extracted entity.
5. Original viewer opens the source page and highlight.
6. User edits and saves.
7. Backend validates revision and persists a draft.
8. User reports an issue or requests reprocessing if needed.
9. Reviewer approves extraction when blocking warnings are resolved.

---

## 34. Reprocessing approval flow

1. Reviewer opens Request Reprocessing.
2. Reviewer selects scope, pages, options, and reason.
3. Backend creates `pending_approval` request.
4. Admin views the queue.
5. Admin approves or rejects with comment.
6. Approval queues a new extraction job.
7. New extraction creates a new version.
8. Reviewer compares and approves the new version.

---

## 35. Translation flow

1. User starts translation from an approved extraction.
2. User selects target language and glossary.
3. Backend creates translation workflow.
4. AI translates segments and records suggestions.
5. User opens common Review Page in translation mode.
6. User accepts, rejects, or edits suggestions.
7. User applies glossary and runs QA.
8. Blocking QA issues must be resolved.
9. Reviewer approves and downloads translated output.

---

## 36. Migration flow

1. User starts migration from an approved extraction.
2. User selects template and version.
3. Backend maps sections and creates migration draft.
4. AI generates uncertain mappings and rewrites as suggestions.
5. User opens common Review Page in migration mode.
6. User accepts, rejects, or edits suggestions.
7. User validates required sections and rendering.
8. Reviewer approves and downloads migrated output.

---

## 37. Delete and versioning flow

- Delete removes the selected SOP row.
- Shared extraction files are retained while sibling versions remain.
- Deleting the final row triggers best-effort file cleanup.
- Re-upload of the same deterministic document ID overwrites shared files.
- A fresh upload inserts `MAX(gpdat_version) + 1`.
- Replaying the same version updates metadata but preserves status.
- Deleting every row resets the next version to 1.

---

# Part IV: Non-Functional Requirements

## 38. Security

- Validate MIME type and file signature.
- Sanitize filenames and asset paths.
- Limit file size.
- Reject encrypted or unreadable documents.
- Add authentication and role checks before production deployment.
- Never log document text, AI prompts containing document text, access tokens, or secrets.
- Sanitize HTML generated from rich-text content.
- Protect AI calls against prompt injection by treating SOP text as untrusted data.
- Audit suggestion acceptance, status changes, approvals, reprocessing decisions, and downloads.

---

## 39. Accessibility and responsive design

Target WCAG 2.2 AA.

- Keyboard-accessible navigation, table actions, dialogs, tabs, PDF controls, editors, and section lists.
- Focus trap and restoration in dialogs.
- Status uses icon and text, not color alone.
- Progress and autosave announcements use live regions.
- Minimum normal-text contrast 4.5:1.
- Reduced-motion support.
- Desktop three-column review.
- Tablet two-column review with AI drawer.
- Mobile single-column tabs and repository cards.

---

## 40. Performance and reliability

- Keep Release 1 extraction concurrency at 1.
- Move CPU work to processes or a separate service before increasing throughput.
- Lazy-load PDF.js and TipTap.
- Render only visible PDF pages.
- Virtualize large lists.
- Retry transient polling failures.
- Cancel stale frontend requests.
- Keep jobs in memory for Release 1 and clearly communicate restart behavior.
- Persist completed records, workflow drafts, issues, suggestions, versions, and audit events in SQLite.

---

## 41. Testing

### Backend

- Metadata extraction fixtures for PDF and DOCX.
- Deterministic ID tests.
- File validation and partial batch tests.
- Pipeline stage and progress tests.
- Cross-page table, icon, caption, and exporter tests.
- SQLite upsert, versioning, and smart-cleanup tests.
- REST and WebSocket contract tests.
- Translation, migration, suggestion, issue, and reprocessing tests.
- Request ID, logging, CORS, and exception tests.

### Frontend

- Repository statistics, filters, search, table, and grid.
- Upload validation, polling, and settled refresh.
- Content Viewer navigation and element rendering.
- Common Review Page configuration for all modes.
- Autosave and conflict handling.
- AI suggestion acceptance and rejection.
- QA and migration validation.
- Reprocessing admin queue.
- Accessibility and visual regression.
- Playwright end-to-end flows.

---

## 42. Release 1 acceptance scenarios

1. Batch upload includes valid and rejected files.
2. Accepted documents process sequentially.
3. Dashboard progress updates every 1.5 seconds.
4. Successful documents appear without manual refresh.
5. Content Viewer renders headings, paragraphs, lists, tables, images, and icons.
6. Extraction Review highlights source content and saves corrections.
7. Issue reporting persists a workflow-linked issue.
8. Admin approval starts reprocessing and creates a new version.
9. AI translation is edited, QA-validated, approved, and downloaded.
10. AI migration is edited, validated, approved, and downloaded.
11. Common Review Page changes mode without duplicated pages.
12. Deleting the last version cleans shared files.
13. All Tailwind layouts match the provided dark teal and emerald design direction.

---

## 43. Definition of done

Release 1 is complete when:

- FastAPI batch upload, job polling, optional WebSocket, extraction, translation, and migration endpoints work;
- SQLite schemas and filesystem paths are initialized automatically;
- deterministic IDs and `gpdat_version` behavior match this specification;
- the nine-stage extraction pipeline produces v2 JSON;
- the Repository, Content Viewer, and common Review Page are implemented in React;
- Tailwind CSS and supplied design styles are applied;
- extraction, translation, and migration modes reuse shared components;
- AI changes require explicit acceptance;
- issues, versions, comparisons, approvals, and reprocessing admin approval work;
- smart cleanup preserves shared files correctly;
- tests, linting, accessibility, and critical end-to-end flows pass.

---

## 44. Coding-agent instruction

```text
Read this specification completely before generating code.

Build the Release 1 system with:

backend/   FastAPI, SQLite, local filesystem, JobManager concurrency=1
frontend/  React 19, TypeScript, Vite, Tailwind CSS v3

Mandatory requirements:

1. Preserve the specified batch upload, deterministic document ID,
   gpdat_version, nine-stage extraction, v2 JSON, polling, WebSocket,
   SQLite, local filesystem, and smart cleanup behavior.
2. Implement one reusable /review/:recordId page for review,
   translation, and migration modes.
3. Do not create three duplicate review pages.
4. Implement all shared Review Page components.
5. Implement AI suggestions as explicit proposed patches.
6. Implement admin-approved extraction reprocessing.
7. Implement the specified REST and WebSocket contracts.
8. Use the supplied Tailwind configuration and CSS design system.
9. Use PDF.js for document viewing and TipTap for rich-text editing.
10. Do not use Bootstrap, Material UI, or Ant Design.
11. Keep business logic out of FastAPI routers.
12. Provide strict TypeScript, Python typing, tests, and linting.
13. Do not use placeholder comments, omitted code, or ellipses.
14. Ensure the frontend build and backend tests succeed.
```
