## System Specification: SOP Batch Upload, Repository & Content Viewer

This document is a complete, implementation-ready specification of the **SOP Migration System**'s upload → extraction → review → content-viewing flow. It covers both the FastAPI backend and the React frontend, including all REST/WebSocket contracts, database schemas, the extraction pipeline, and every UI component's behavior — enough to rebuild the same system on a different stack.

---

## 1. Overview

The system lets a user upload PDF/DOCX Standard Operating Procedure (SOP) documents in a batch. Each document is asynchronously parsed into structured content (headings, paragraphs, lists, tables, images, icons) and metadata (document number, name, title, version, type, page count). Completed extractions are persisted as **SOP records** with a review status (`in_review` / `approved` / `rejected`) that a reviewer can change. A dedicated content-viewer page renders the extracted document section-by-section.

Core capabilities:
1. **Batch upload** of PDF/DOCX files → background extraction pipeline → progress polling.
2. **SOP Repository** page: KPI cards, searchable/filterable list (table or grid) of all extraction runs, delete with smart file cleanup.
3. **SOP Content View** page: per-section navigation and rendering of the extracted document, plus review-status actions (Approve / Needs Review / Reject).

---

## 2. Architecture

```
┌─────────────────────┐        HTTP/JSON, multipart, WS        ┌──────────────────────────┐
│   React Frontend     │ ───────────────────────────────────▶  │   FastAPI Backend        │
│  (Vite, TS, Tailwind)│ ◀───────────────────────────────────  │                          │
└─────────────────────┘                                        │  ┌────────────────────┐  │
                                                                 │  │ JobManager (queue)  │  │
                                                                 │  │  asyncio + threads  │  │
                                                                 │  └─────────┬──────────┘  │
                                                                 │            ▼             │
                                                                 │  Extraction Pipeline:     │
                                                                 │  Parse → Tables → Stitch  │
                                                                 │  → Icons → Captions →     │
                                                                 │  AST Build → Chunk →      │
                                                                 │  Export (v2 JSON)         │
                                                                 └──────────┬───────────────┘
                                                                            ▼
                                              ┌───────────────────────────────────────────────┐
                                              │ Filesystem: data/uploads, data/output,         │
                                              │ data/extracted_images, data/extracted_icons     │
                                              │ SQLite: sop_records.db, logs.db                 │
                                              └───────────────────────────────────────────────┘
```

Key architectural decisions:
- **Job queue, not request-blocking**: uploads return immediately with a `job_id`; the frontend polls `GET /jobs/{job_id}` (or connects to a WebSocket) until every document in the batch reaches a terminal state.
- **`concurrency=1` worker pool**: every pipeline stage is CPU-bound pure-Python work dispatched via `asyncio.to_thread`. Because of the GIL, running documents "concurrently" on multiple threads does **not** parallelize CPU work — it just makes the GIL bounce between threads, roughly doubling each document's stage time for no wall-clock gain. The job manager therefore runs exactly one worker so documents are processed strictly sequentially; the FastAPI event loop (and `/jobs` polling) stays responsive regardless, since only the worker pool is affected.
- **SQLite is the single source of truth for versioning**: there is no separate counter file. The next `gpdat_version` for a document is `MAX(gpdat_version) + 1` from its existing rows in `sop_records`, so deleting all rows for a document naturally resets versioning back to 1.
- **Deterministic `document_id`**: derived from sanitized `document_number` + `document_name` (or filename fallback) + `document_version`, e.g. `BI-VQD-24416_BI-VQD-24416-G_v3.0`. Re-uploading the same physical document overwrites the same uploaded file (no version suffix in the filename) but creates a new `sop_records` row per `gpdat_version`.

---

## 3. Tech Stack

| Layer | Technology |
|---|---|
| Backend framework | FastAPI (Python), Uvicorn |
| Backend data | SQLite (`sop_records.db`, `logs.db`), filesystem for uploads/outputs/assets |
| PDF parsing | PyMuPDF (`fitz`), `pdfplumber` |
| DOCX parsing | `python-docx` |
| Icon detection | `imagehash` + `Pillow` (perceptual hashing) |
| Chunking | scikit-learn `TfidfVectorizer` + cosine similarity (no torch) |
| Logging | Loguru (console + file + SQLite sinks, contextualized with `job_id`/`document_id`/`request_id`/`stage`) |
| Frontend framework | React 19 + TypeScript, Vite |
| Frontend routing | `react-router-dom` v7 |
| Styling | Tailwind CSS v3, CSS variables for theming |
| Frontend icons/anim | `lucide-react`, `framer-motion`, `react-file-icon` |
| Linting | `oxlint` (frontend) |

---

## 4. Backend Specification

### 4.1 Configuration (`Settings`)

Loaded via `pydantic_settings.BaseSettings`, env prefix `SOP_`, optional `.env` file.

| Field | Default | Purpose |
|---|---|---|
| `upload_dir` | `data/uploads` | Original uploaded files, named `{document_id}{ext}` |
| `extracted_images_dir` | `data/extracted_images` | Per-document subfolder of extracted photo/figure images |
| `extracted_icons_dir` | `data/extracted_icons` | Per-document subfolder of extracted semantic icons |
| `temp_dir` | `data/temp` | Scratch space during upload (metadata pre-extraction) |
| `output_dir` | `data/output` | Final `{document_id}_v2.json` exports |
| `log_dir`, `log_file_path`, `error_file_path`, `log_db_path` | `data/logs/...` | Loguru sinks |
| `sop_db_path` | `data/sop_records.db` | SOP records SQLite DB |
| `max_upload_size_mb` | `50` | Per-file size cap |
| `allowed_extensions` | `[".pdf", ".docx"]` | Accepted upload types |
| `table_stitch_enabled`, `table_stitch_score_threshold`, `table_stitch_column_tolerance_pt`, `table_stitch_bottom_zone_pct`, `table_stitch_top_zone_pct` | — | Cross-page table merging tuning |
| `watermark_keywords` | list | Used by header/footer/watermark suppression heuristics |
| `log_level` | `INFO` | Loguru root level |

All relative paths are resolved against `project_root` and directories are created on startup (`ensure_directories`).

### 4.2 Data Storage

#### 4.2.1 `sop_records` table (SQLite, WAL mode, `sop_records.db`)

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
    status           TEXT    NOT NULL DEFAULT 'approved'
                     CHECK(status IN ('in_review','approved','rejected')),
    source_filename  TEXT,
    output_path      TEXT,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL,
    UNIQUE(document_uid, gpdat_version)
);
CREATE INDEX IF NOT EXISTS idx_sop_uid    ON sop_records(document_uid);
CREATE INDEX IF NOT EXISTS idx_sop_status ON sop_records(status);
CREATE INDEX IF NOT EXISTS idx_sop_job    ON sop_records(job_id);
```

Semantics:
- One row = one **extraction run** of an SOP. `(document_uid, gpdat_version)` is unique.
- **Upsert on pipeline completion**: `ON CONFLICT(document_uid, gpdat_version) DO UPDATE` updates all metadata columns **except `status`**, so a reviewer's decision is never silently reset by a re-run of the same version.
- **Versioning**: `gpdat_version` for a fresh row = `MAX(existing gpdat_version for this document_uid) + 1` (or `1` if none exist). This is computed lazily at upsert time — there is no independent counter, so it is self-healing: delete all rows for a document and the next upload starts again at version 1.
- **Status transitions**: any status can move to any other status (no state machine restriction) via `PATCH /sops/{id}/status`. Default value on insert is `approved`.

#### 4.2.2 Filesystem layout

```
data/
  uploads/{document_id}.{pdf|docx}                    # original file, unversioned name
  output/{document_id}_v2.json                        # exporter output (per document_id, latest run overwrites)
  extracted_images/{document_id}/{page}_{img|vec}{n}_{hash}.png
  extracted_icons/{document_id}/{page}_{img|vec}{n}_{hash}.png
  logs/app.log, error.log, logs.db
  sop_records.db
```

Because upload/output filenames are keyed by `document_id` only (not `gpdat_version`), re-uploading the same document overwrites its file in place — history across versions is tracked only in the `sop_records` DB rows, not as separate files on disk.

#### 4.2.3 Logs (`logs.db`)

A separate SQLite DB (WAL mode) receives structured log rows via a custom Loguru sink, tagged with `job_id`, `document_id`, `request_id`, and pipeline `stage`, enabling end-to-end tracing of a single upload or API call. Rows older than 14 days are pruned. Not required to replicate the upload/repository UX, but recommended for production traceability.

### 4.3 Domain Errors

All handled errors subclass `AppError` and are mapped centrally to a consistent JSON error body:

```json
{ "error": "<error_code>", "message": "<human text>", "detail": "<optional>", "path": "/documents/upload/batch" }
```

| Exception | HTTP | `error_code` |
|---|---|---|
| `BadRequestError` | 400 | `bad_request` |
| `UnsupportedFileTypeError` | 415 | `unsupported_file_type` |
| `FileTooLargeError` | 413 | `file_too_large` |
| `EmptyFileError` | 400 | `empty_file` |
| `DocumentNotFoundError` | 404 | `document_not_found` |
| `ParsingError` | 422 | `parsing_error` |
| `SopRecordNotFoundError` | 404 | `sop_record_not_found` |
| `RequestValidationError` (FastAPI) | 422 | `validation_error` (detail = list of field errors) |
| Unhandled `Exception` | 500 | `internal_error` |

### 4.4 Document ID & Metadata Extraction

`SOPMetadataExtractor` runs against the raw uploaded bytes **before** the full pipeline, purely to compute a stable `document_id` and preview metadata:

1. **PDF**: read the first page's tables via `pdfplumber`; classify each row's label cell against keyword sets (whole-word regex match, case-insensitive):
   - Title: `document title`, `title`
   - Name: `document name`, `doc name`
   - Number: `document number`, `doc number`, `doc no`, `sop number`, **`document id`** (an SOP that only has a "Document ID" field uses that value as `document_number`)
   - Version: `version`, `ver`, `rev`, `revision`
   - Type: `type/subtype`, `type`, `subtype`, `document type`, `doc type`
   - Rows are split into `(label, value)` pairs; a trailing cell that itself contains a second `"Label: value"` string is parsed out too (handles two label/value pairs packed into one row).
   - Cell values pass through `_clean_cell_value`, which drops any line that is ≤2 alphabetic characters standing alone (removes stray watermark-stamp fragments bleeding into a narrow cell) without a fixed watermark word list.
   - If any field is still missing, fall back to regex over the raw first-page text (`fitz`), e.g. `Document\s*Number|Document\s*ID|Number):\s*(...)`.
   - **DOCX** follows the same two-phase approach against the first 3 tables and first 20 paragraphs.
2. **`document_id` generation** (`generate_document_id`): sanitize `document_number`, `document_name` (falls back to the uploaded filename's stem if empty), and `document_version` to `[A-Za-z0-9_\-.]` (other chars → `_`, collapsed, trimmed); default missing parts to `"DOC"` / `"UNKNOWN"` / `"1.0"`. Result: `f"{number}_{name}_v{version}"`.

### 4.5 Extraction Pipeline (per document, run by `JobManager`)

Each stage below is dispatched via `asyncio.to_thread` and wrapped in `logger.contextualize(stage=...)` for traceability. `DocumentJob.progress_percentage` is updated after each group of stages.

| # | Stage | `progress_%` | Component | Purpose |
|---|---|---|---|---|
| 1 | Locate | 20 | — | Find `data/uploads/{document_id}{.pdf|.docx}` |
| 2 | Parse | 40 | `ParserFactory` → `PdfParser`/`DocxParser` | Produce a `RawDocument` (pages → elements: headings, paragraphs, tables, images) |
| 3 | Tables | — | `TableExtractor` | Detect/refine table structures, merged cells |
| 4 | Stitch | — | `CrossPageTableStitcher` | Merge tables that continue across a page break (score/column-tolerance heuristics, config-gated) |
| 5 | Icons | — | `IconExtractor` | Perceptual-hash + heuristics reclassify small images as semantic icons (vs. photos/figures) |
| 6 | Captions | 65 | `CaptionExtractor` | Associate `"Figure N:"` / `"Table N:"` caption paragraphs with the adjacent image/table |
| 7 | AST | 80 | `ASTBuilder` | Build a typed `DocumentNode` tree: headings → sections, with paragraphs/lists/tables/images/icons as children in reading order |
| 8 | Chunk | 90 | `HierarchicalChunker` → `SemanticChunker` | Produce section-level chunks, refined by TF-IDF similarity splitting. *(Computed for parity with the on-demand `/documents/{id}/chunks` endpoint; not part of the persisted v2 export.)* |
| 9 | Export | 100 | `MigrationExporter` + `sop_store.upsert_record` | Convert AST → `DocxMigrationOutput`, write `{document_id}_v2.json`, upsert the `sop_records` row |

On any exception the document's `DocumentJob.status` becomes `failed` with `error`/`message` set; the batch `BatchJob.status` becomes `completed` only if **all** documents succeeded, else `failed`, once every document reaches a terminal state.

`MigrationExporter` traversal rules (for a faithful reimplementation):
- Running headers/footers are suppressed via a fixed set of regexes (organization-specific boilerplate, e.g. `"^BI-VQD-\d+"`, `"Property of ..."`, `"Working Copy"`).
- A heading whose text matches `^(\d+)\s+([A-Z0-9\s&/\-_,]+)$` (a top-level numbered ALL-CAPS heading) starts a **new section**; any other heading becomes an in-section `heading` element.
- Icons in reading order precede the text they annotate, so an icon node is buffered and attached to the **next** element's `icons[]` (or to the last element of the last section if none follows).
- A table's cells are flattened to only genuine "merge origin" cells (`is_merge_origin=True`) with explicit `row_span`/`col_span`, ready for direct `<table>`/`.docx` reconstruction.
- Every element is stamped with its parent section's `title` as `section_name` at serialization time (so a flattened element list still carries section context, e.g. for retrieval/QA use cases).

### 4.6 v2 Migration JSON Schema

This is the **canonical content contract** the frontend renders. Retrieved via `GET /documents/v2/{document_id}/json` (with asset paths already rewritten to servable URLs — see §4.7).

```
DocxMigrationOutput
├── version: string                    // "3.1"
├── document_Uid: string
├── metadata: MigrationMetadata
└── sections: MigrationSection[]

MigrationMetadata
├── document_Uid: string
├── document_number: string | null
├── document_name: string | null
├── document_title: string | null
├── document_version: string | null
├── document_type: string | null       // e.g. "Governance and Procedure > Guidance"
├── file_type: string                  // "pdf" | "docx"
├── language: string                   // default "en"
├── page_count: int
└── gpdat_version: int                 // 1-based re-upload counter

MigrationSection
├── section_number: string | null      // e.g. "3.2", extracted from the heading text
├── title: string
├── page_start: int
├── page_end: int
└── elements: MigrationElement[]

MigrationElement                        // fields present depend on element_type; absent fields omitted from JSON
├── element_type: "heading" | "paragraph" | "list" | "table" | "image"
├── page: int
├── section_name: string               // stamped by parent section
├── level?: int                        // heading only (1-6)
├── text?: string                      // heading / paragraph
├── icons?: MigrationIconRef[]         // paragraph / image, buffered icons attached here
├── items?: string[]                   // list only
├── title?: string                     // table caption / image caption
├── num_rows?: int, num_cols?: int      // table only
├── cells?: MigrationTableCell[]        // table only
└── image_path?: string                // image only — rewritten to /documents/{id}/assets/{filename}

MigrationTableCell
├── row_index: int, col_index: int
├── row_span: int (default 1), col_span: int (default 1)
├── text: string
├── is_header: boolean
├── icon_path?: string                  // rewritten URL
└── image_path?: string                 // rewritten URL

MigrationIconRef
├── icon_id: string
├── path: string                        // rewritten URL
└── semantic_meaning?: string           // e.g. "Warning", "PPE"
```

Example (truncated, from a real extraction — `data/output/BI-VQD-24416_BI-VQD-24416-G_v3.0_v2.json`):

```json
{
  "version": "3.1",
  "document_Uid": "BI-VQD-24416_BI-VQD-24416-G_v3.0",
  "metadata": {
    "document_Uid": "BI-VQD-24416_BI-VQD-24416-G_v3.0",
    "document_number": "BI-VQD-24416",
    "document_name": "BI-VQD-24416-G",
    "document_title": "Good Writing Practice for Governance and Procedure\nDocuments",
    "document_version": "3.0",
    "document_type": "Governance and Procedure > Guidance",
    "file_type": "pdf",
    "language": "en",
    "page_count": 15,
    "gpdat_version": 1
  },
  "sections": [
    {
      "title": "0 PREAMBLE",
      "page_start": 1,
      "page_end": 2,
      "elements": [
        {
          "element_type": "table",
          "page": 1,
          "section_name": "0 PREAMBLE",
          "num_rows": 8,
          "num_cols": 2,
          "cells": [
            { "row_index": 0, "col_index": 0, "row_span": 1, "col_span": 1, "text": "Scope", "is_header": true },
            { "row_index": 0, "col_index": 1, "row_span": 1, "col_span": 1, "text": "Global", "is_header": true }
          ]
        }
      ]
    }
  ]
}
```

### 4.7 REST API Reference

Base path: none (all routers mounted at root). CORS allows `http://localhost:5173` and `http://127.0.0.1:5173` with credentials, all methods/headers.

Every response sets an `X-Request-ID` header (from `X-Request-ID` request header or a fresh 12-hex-char id); every log line during that request is contextualized with it.

#### `GET /health`
Liveness probe. → `{"status": "healthy", "service": "sop-migration-system", "version": "0.1.0"}`

#### `POST /documents/upload/batch`
Accepts one or more files, validates each independently, and enqueues a background job. **multipart/form-data**, field name `files` (repeatable).

Per-file validation (in order; failures append to `rejected_files` instead of failing the whole request):
1. Filename present.
2. Extension in `allowed_extensions` (`.pdf`, `.docx`).
3. Content readable.
4. Non-empty and ≤ `max_upload_size_mb` (default 50 MB).
5. Metadata pre-extraction succeeds and the file is written to `uploads/{document_id}{ext}` (overwriting any prior upload of the same document).

If **zero** files survive validation → `400 bad_request` with an aggregated `detail` string. Otherwise creates a `BatchJob` (all accepted documents `queued`) and returns it immediately.

Response `200` — `BatchJob`:
```json
{
  "job_id": "3fa2...uuid",
  "status": "queued",
  "created_at": "2026-08-28T05:00:00Z",
  "started_at": null,
  "completed_at": null,
  "documents": [
    { "document_id": "BI-VQD-24416_BI-VQD-24416-G_v3.0", "filename": "BI-VQD-24416_BI-VQD-24416-G_v3.0.pdf",
      "status": "queued", "progress_percentage": 0, "message": "Queued for processing",
      "result": null, "error": null, "started_at": null, "completed_at": null }
  ],
  "rejected_files": [ { "filename": "notes.txt", "reason": "Unsupported file type '.txt'. Allowed: ['.pdf', '.docx']" } ]
}
```

#### `GET /jobs/{job_id}`
Poll batch progress. → `BatchJob` (same shape as above, fields updated live). `404` if unknown job (jobs are in-memory only — cleared on server restart).

Derived fields the frontend needs to compute itself (not sent by the server):
- `total_documents = len(documents)`
- `completed_documents = count(status == completed)`
- `failed_documents = count(status == failed)`
- `progress_percentage = average(documents[].progress_percentage)` (100 if no documents)

#### `WS /jobs/{job_id}/progress`
Optional real-time alternative to polling. On connect, if the job is unknown the socket closes with code `1008`. Otherwise sends the full `BatchJob` JSON once per second until the job reaches `completed`/`failed`, then closes normally. (The reference frontend implementation uses HTTP polling, not this socket — see §5.6.)

#### `GET /sops`
List persisted SOP records, newest first.

Query params: `status` (`in_review`|`approved`|`rejected`, optional), `document_Uid` (optional exact match), `limit` (1–1000, default 100), `offset` (default 0).

Response `200` — `SopListResponse`:
```json
{ "count": 2, "records": [ /* SopRecord[] — see §4.7 schema below */ ] }
```

#### `GET /sops/{record_id}`
Fetch one record by surrogate id. `404 sop_record_not_found` if missing.

#### `PATCH /sops/{record_id}/status`
Body: `{ "status": "approved" | "in_review" | "rejected" }`. Updates `status` and `updated_at`. Returns the updated `SopRecord`. `404` if missing.

#### `DELETE /sops/{record_id}`
Deletes the row. `204 No Content`. `404` if missing. **Smart cleanup**: after deleting, counts remaining rows for the same `document_uid`; if zero remain, best-effort deletes the uploaded file, the `{document_id}_v2.json` output, and both asset directories (`extracted_images/{document_id}`, `extracted_icons/{document_id}`). If sibling rows (other `gpdat_version`s) still exist, files are kept since they're shared (unversioned filenames). Cleanup failures are logged, never raised — the DB row is the UI's source of truth.

`SopRecord` schema (JSON, camelCase preserved as backend sends it — `document_Uid` uses a capital U by design):
```json
{
  "id": 1,
  "job_id": "3fa2...uuid",
  "document_Uid": "BI-VQD-24416_BI-VQD-24416-G_v3.0",
  "document_number": "BI-VQD-24416",
  "document_name": "BI-VQD-24416-G",
  "document_title": "Good Writing Practice for Governance and Procedure Documents",
  "document_version": "3.0",
  "document_type": "Governance and Procedure > Guidance",
  "file_type": "pdf",
  "language": "en",
  "page_count": 15,
  "gpdat_version": 1,
  "status": "approved",
  "source_filename": "BI-VQD-24416_BI-VQD-24416-G_v3.0.pdf",
  "output_path": "C:/.../data/output/BI-VQD-24416_BI-VQD-24416-G_v3.0_v2.json",
  "created_at": "2026-08-27T10:12:00+00:00",
  "updated_at": "2026-08-27T10:12:00+00:00"
}
```

#### `GET /documents/v2/{document_id}/json`
Returns the exported v2 content (see §4.6) with `image_path`/`icon_path`/`path` fields rewritten from absolute on-disk paths to `/documents/{document_id}/assets/{filename}` URLs. `404 document_not_found` if the job hasn't completed / output missing. `422 parsing_error` if the stored JSON is corrupt.

#### `GET /documents/{document_id}/assets/{filename}`
Serves one extracted image/icon file. Looks for `{filename}` (basename only — path traversal in the input is neutralized) under `extracted_images_dir/{document_id}/` first, then `extracted_icons_dir/{document_id}/`. `404` if not found in either.

#### Diagnostic / lower-level endpoints (not used by the reference UI, but useful for tooling/debugging)
| Method & Path | Purpose |
|---|---|
| `GET /documents/{document_id}` | Full raw parsed document (post-parse, pre-pipeline), synchronous re-parse |
| `GET /documents/{document_id}/elements?page=` | Flat element list, optional page filter |
| `GET /documents/{document_id}/tree` | Nested AST after tables/stitch/icons/captions, synchronous |
| `GET /documents/{document_id}/chunks` | Hierarchical + semantic chunks with validation warnings, synchronous |
| `POST /documents/extract` | Legacy trigger; body `{"document_id": "..."}`, returns a parse summary |
| `GET /logs/...` | Query the structured Loguru SQLite sink (implementation detail, see `app/api/logs.py`) |

All four synchronous diagnostic endpoints **re-run the pipeline on each call** (no caching) — they exist for inspection/debugging, not for the production UI flow, which always reads the persisted `_v2.json` via `GET /documents/v2/{document_id}/json`.

### 4.8 Job & Batch Schemas (Pydantic)

```python
class JobStatus(str, Enum):
    QUEUED = "queued"; PROCESSING = "processing"; COMPLETED = "completed"; FAILED = "failed"

class RejectedFile(BaseModel):
    filename: str
    reason: str

class DocumentJob(BaseModel):
    document_id: str
    filename: str
    status: JobStatus = JobStatus.QUEUED
    progress_percentage: int = 0
    message: str = "Queued for processing"
    result: Optional[dict] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

class BatchJob(BaseModel):
    job_id: str
    status: JobStatus = JobStatus.QUEUED
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    documents: list[DocumentJob] = []
    rejected_files: list[RejectedFile] = []
```

### 4.9 Middleware & Cross-Cutting Concerns

- **CORS**: `allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"]`, `allow_credentials=True`, all methods/headers. Add the deployed frontend origin when hosting for real.
- **Request-context middleware**: stamps every request with an `X-Request-ID` (reused from the incoming header if present) and wraps the whole request in `logger.contextualize(request_id=...)`, logging `→ METHOD path` on entry and `← METHOD path [status]` on exit.
- **Exception handlers**: `AppError` (typed domain errors, logged at each error's own `log_level`), `RequestValidationError` (422, logs field errors), and a catch-all `Exception` handler (500, full traceback logged, generic message returned to the client).
- **Startup (`lifespan`)**: configures logging, ensures data directories exist, initializes the SOP SQLite store (`init_sop_store`), constructs `JobManager(settings, concurrency=1)` and starts its worker(s); shuts both down cleanly on exit.

---

## 5. Frontend Specification

### 5.1 Stack & Structure

```
frontend/
  src/
    App.tsx                     # BrowserRouter + route table
    main.tsx                    # applies persisted theme, mounts <App/>
    types.ts                    # TS mirrors of every backend schema
    styles/globals.css          # Tailwind entry + CSS-variable theme tokens
    lib/
      api.ts                    # fetch wrapper + typed endpoint calls
      useJobPolling.ts           # polling hook for BatchJob
      stats.ts                   # KPI card derivation
      sopDisplay.ts               # title/subline formatting rules
      format.ts                   # date formatting
      theme.ts                    # dark/light theme state + persistence
    components/
      Layout.tsx, Sidebar.tsx
      StatCards.tsx, SearchBar.tsx, FilterBar.tsx
      SopList.tsx, SopTable.tsx, SopGrid.tsx
      UploadSops.tsx, JobProgressBanner.tsx
      StatusBadge.tsx, FileTypeIcon.tsx, ThemeToggle.tsx
      ConfirmDialog.tsx, Toast.tsx
      ui/Button.tsx
      content/SectionNav.tsx, content/ElementRenderer.tsx
    pages/
      SopRepository.tsx          # "/" — list + upload + KPIs
      SopContentView.tsx          # "/sops/:recordId" — section viewer
```

Package versions (from `package.json`): `react`/`react-dom` ^19.2.8, `react-router-dom` ^7.18.2, `framer-motion` ^13, `lucide-react` ^1.34, `react-file-icon` ^1.6, Tailwind ^3.4.19, Vite ^8.2.2, TypeScript ~6.0.2, `oxlint` for linting.

### 5.2 Routing

```tsx
<BrowserRouter>
  <Routes>
    <Route path="/" element={<SopRepository />} />
    <Route path="/sops/:recordId" element={<SopContentView />} />
  </Routes>
</BrowserRouter>
```
`recordId` is the `SopRecord.id` **surrogate integer**, not `document_Uid`. `SopContentView` resolves it to a document via `GET /sops/{recordId}` then fetches content via `GET /documents/v2/{record.document_Uid}/json`.

### 5.3 Design Tokens & Theming

Theme is applied via a `data-theme="dark"|"light"` attribute on `<html>`, backed by CSS variables (no Tailwind dark-mode class strategy — everything reads `var(--token)`), persisted to `localStorage` key `gpdat.theme` (default `dark`).

```css
[data-theme='dark'] {
  --primary: #00e47c; --primary-dark: #00c86d;
  --bg-main: #08312a; --bg-card: #0a3d34;
  --text-main: #ffffff; --text-muted: #94a3b8;
  --border: rgba(255,255,255,0.06); --sidebar-bg: #062621;
  --nav-active-bg: rgba(0,228,124,0.15);
}
[data-theme='light'] {
  --primary: #169949; --primary-dark: #00c86d;
  --bg-main: #ffffff; --bg-card: #f8f8f8;
  --text-main: #0f172a; --text-muted: #3a474e;
  --border: #e2e8f0; --sidebar-bg: #ffffff;
  --nav-active-bg: rgba(0,228,124,0.1);
}
```
Reusable classes: `.dashboard-card` (bg-card, 1px border, 0.75rem radius) and `.btn-primary` (primary bg, dark hover). `useTheme()` hook exposes `[theme, toggleTheme]` and re-renders subscribers (plain DOM attribute mutation alone wouldn't trigger React updates).

### 5.4 Page: SOP Repository (`/`)

**Purpose**: primary landing page — browse, filter, search, upload, review-at-a-glance, and delete SOPs.

**Layout** (top to bottom, inside the shared `Layout` shell — fixed sidebar + independently-scrolling content pane):
1. Header: icon + "GP-DAT" eyebrow + "SOP Repository" title + subtitle, theme toggle button, primary "Upload SOPs" button (top right).
2. **5 KPI cards** (`StatCards`): Total SOPs, Completed, Processing, Needs Review, Failed — each with an icon in a tinted circle and a `% of total` sublabel.
3. **Job progress banner** (only while a batch is in flight/just finished): spinner/check/x icon, `"Processing uploaded SOPs..."` or `"Batch upload completed"/"finished with errors"`, counts (`N completed · N failed · N total [· N rejected before processing]`), a progress bar while not done, dismissible once done.
4. **Search bar**: single text input (`"Search by SOP title, number, filename, content..."`) + list/grid view toggle.
5. **Filter bar**: status chips (All / Approved / Needs Review / Rejected) and file-type chips (All / PDF / DOCX). Multiple filters AND together with the search text.
6. **SOP list** (table or grid, per view toggle): loading spinner state, error state, and two distinct empty states (no SOPs at all vs. no matches for active filters).
7. Modals/overlays: `UploadSops` dialog, delete `ConfirmDialog`, bottom-right `ToastStack` for success/error feedback.

**Data flow**:
- On mount, `GET /sops?limit=1000` → `sops` state.
- KPI computation (`computeStats`, pure function): `completed = sops.length`; `needsReview = count(sops.status === 'in_review')`; `processing`/`failed` are read **only from the currently active batch job** (`activeJob.documents`), not from history — the backend doesn't persist job history, so these two numbers reset on page reload once no job is active. `failed` also adds `activeJob.rejected_files.length`. `total = completed + processing + failed`.
- Client-side filtering (`useMemo`): status filter exact match, type filter case-insensitive match on `file_type`, search substring match (case-insensitive) against the joined `document_title + document_name + document_number + source_filename`.
- **Upload → poll → refresh** cycle: `UploadSops` calls `uploadBatch(files)` → sets `activeJobId` → `useJobPolling` polls `GET /jobs/{id}` every 1.5s → on terminal status, calls `onSettled` (re-fetches `GET /sops`) exactly once, so newly completed documents appear without a manual refresh.
- **Delete**: `ConfirmDialog` → `DELETE /sops/{id}` → optimistically removes the row from local `sops` state → success/error toast.

### 5.5 Page: SOP Content View (`/sops/:recordId`)

**Purpose**: read the fully extracted content of one SOP, section by section, and change its review status.

**Layout**:
1. Header: back-to-repository arrow, file-type icon, title (`displayTitle`) + subline (`displaySubline`), and on the right a `StatusBadge` plus three status-action buttons (Approve / Needs Review / Reject) — the button matching the current status is shown as the disabled "primary" variant, the other two as clickable "ghost" buttons.
2. Body: two-column layout —
   - **Left**: `SectionNav`, a sticky, independently-scrolling list of all sections (`sticky top-6 max-h-[calc(100vh-8rem)] overflow-y-auto`); each item shows section number + title + element count; clicking sets the active section index.
   - **Right**: a card showing only the **active section's** content — page range, numbered section title, then each element rendered via `ElementRenderer`, followed by Previous/Next section buttons and an "N of M" indicator.
3. Loading state (spinner + "Loading SOP content…"), not-found/error state (icon + message + back button), toasts for status-update feedback.

**Independent scrolling — important implementation detail**: the outer page shell (`Layout`) must be `h-screen overflow-hidden` (not `min-h-screen`), with only its content pane set to `overflow-y-auto`. Without a bounded-height ancestor, `overflow-y-auto` on the content pane has nothing to clip against and the *entire document* scrolls, dragging the sidebar and section nav off-screen with it. `Sidebar`'s root uses `h-full` (not `h-screen`) to fill that bounded parent. This is what makes the section nav and the content pane scroll independently of each other and of the page as a whole.

**Data flow**:
- `useParams<{recordId}>()` → `numericId = Number(recordId)`.
- On mount/`numericId` change: `GET /sops/{numericId}` → `record`; then `GET /documents/v2/{record.document_Uid}/json` → `content`. Reset `activeSection` to `0` whenever the record reloads.
- `handleStatusChange(newStatus)`: no-ops if unchanged; otherwise `PATCH /sops/{id}/status`, optimistically patches local `record.status`, shows a toast; a per-button loading spinner reflects the in-flight status value.
- Section content is **not** searched/filtered — it's a pure "click a section, see only its elements" nav, matching the source mockup exactly.

### 5.6 Component Inventory

| Component | Props | Responsibility |
|---|---|---|
| `Layout` | `children`, `breadcrumb?` | Page shell: fixed `Sidebar` + independently scrolling content pane + breadcrumb row (`GP-DAT / Documents / {breadcrumb}`) |
| `Sidebar` | — | Static branded nav (only "GP Docs" entry wired; others are deliberately absent placeholders) |
| `StatCards` | `stats: StatCardData[]` | Renders the 5 KPI cards with per-key icon/tint config |
| `SearchBar` | `value`, `onChange`, `viewMode`, `onViewModeChange` | Search input + list/grid toggle |
| `FilterBar` | `statusFilter`, `onStatusFilterChange`, `typeFilter`, `onTypeFilterChange` | Status + file-type chip groups |
| `SopList` | `records`, `viewMode`, `loading`, `error`, `hasActiveFilters`, `onDelete` | Dispatches to loading/error/empty states or `SopTable`/`SopGrid` |
| `SopTable` | `records`, `onDelete` | Row-per-SOP table: title+subline, status badge, uploaded/updated dates, View/Delete actions |
| `SopGrid` | `records`, `onDelete` | Card-per-SOP grid variant of the same data |
| `UploadSops` | `open`, `onClose`, `onUploaded(job)` | Modal: drag-and-drop + file-picker (`.pdf`/`.docx` only, client-validated), file list with per-file remove, submit → `uploadBatch` |
| `JobProgressBanner` | `job`, `onDismiss` | Live batch progress summary + bar, dismiss button once terminal |
| `StatusBadge` | `status: SopStatus \| JobStatus` | Colored pill (shared vocabulary for review status and job status) |
| `FileTypeIcon` | `fileType`, `size?` | Branded folded-corner file icon via `react-file-icon`, gray fallback for unknown types |
| `ThemeToggle` | — | Sun/moon button, calls `useTheme().toggleTheme` |
| `ConfirmDialog` | `open`, `title`, `description`, `confirmLabel?`, `busy?`, `onConfirm`, `onCancel` | Generic destructive-action confirmation modal |
| `ToastStack`/`Toast` | `toasts`, `onDismiss` | Bottom-right auto-dismissing (4s) success/error notifications |
| `Button` (ui) | `variant: 'primary'\|'ghost'\|'icon'` | Shared button primitive |
| `SectionNav` | `sections`, `activeIndex`, `onSelect` | Sticky, independently-scrolling section list for the content viewer |
| `ElementRenderer` | `element: MigrationElement` | Type-dispatch renderer: heading/paragraph/list/table/image, with an "Unsupported element type" fallback |

### 5.7 Data/State Libraries

- **`lib/api.ts`**: thin `fetch` wrapper. `API_BASE` = `import.meta.env.VITE_API_BASE ?? 'http://localhost:8000'`. `ApiError` carries `status` + backend `detail`. `handleResponse<T>` parses the backend's `{error, message, detail, path}` shape on failure. Functions: `listSops()`, `getSop(id)`, `getDocumentContent(documentUid)`, `assetUrl(path)` (prefixes `API_BASE`), `updateSopStatus(id, status)`, `deleteSop(id)`, `uploadBatch(files)`, `getJob(jobId)`.
- **`lib/useJobPolling.ts`**: `useJobPolling(jobId, onSettled): BatchJob | null`. Polls every 1500ms while `jobId` is set; stops and calls `onSettled()` exactly once when status becomes `completed`/`failed`; a transient fetch failure retries rather than aborting; cleans up its timer on unmount/`jobId` change.
- **`lib/stats.ts`**: `computeStats(sops, activeJob) → StatCardData[]` (see §5.4).
- **`lib/sopDisplay.ts`**: `displayTitle(sop)` = `document_title ?? document_name ?? source_filename ?? document_Uid`. `displaySubline(sop)` = `"{number} · {name} · {N pages} · v{version}[ (upload #{gpdat_version})]"`, omitting any missing part, omitting `name` if identical to `number`, appending the upload-count suffix only when `gpdat_version > 1`. Returns `"—"` if nothing is available.
- **`lib/format.ts`**: `formatDate(iso)` → locale short date (`"28 Aug 2026"`) or `"—"`.
- **`lib/theme.ts`**: `getTheme()`/`applyTheme()`/`useTheme()` — see §5.3.

### 5.8 TypeScript Types (mirrors backend Pydantic schemas exactly, field-for-field)

```ts
type SopStatus = 'in_review' | 'approved' | 'rejected'
interface SopRecord {
  id: number; job_id: string; document_Uid: string
  document_number: string | null; document_name: string | null
  document_title: string | null; document_version: string | null
  document_type: string | null; file_type: string; language: string
  page_count: number; gpdat_version: number; status: SopStatus
  source_filename: string | null; output_path: string | null
  created_at: string; updated_at: string
}
interface SopListResponse { count: number; records: SopRecord[] }

type JobStatus = 'queued' | 'processing' | 'completed' | 'failed'
interface RejectedFile { filename: string; reason: string }
interface DocumentJob {
  document_id: string; filename: string; status: JobStatus
  progress_percentage: number; message: string; error: string | null
  started_at: string | null; completed_at: string | null
}
interface BatchJob {
  job_id: string; status: JobStatus; created_at: string
  started_at: string | null; completed_at: string | null
  documents: DocumentJob[]; rejected_files: RejectedFile[]
}

type ViewMode = 'list' | 'grid'
type StatusFilter = SopStatus | 'all'
type FileTypeFilter = 'pdf' | 'docx' | 'all'

type MigrationElementType = 'heading' | 'paragraph' | 'list' | 'table' | 'image' | string
interface MigrationIconRef { icon_id: string; path: string; semantic_meaning?: string | null }
interface MigrationTableCell {
  row_index: number; col_index: number; row_span: number; col_span: number
  text: string; is_header: boolean; icon_path?: string | null; image_path?: string | null
}
interface MigrationElement {
  element_type: MigrationElementType; page: number; section_name?: string | null
  level?: number | null; text?: string | null; icons?: MigrationIconRef[]; items?: string[]
  title?: string | null; num_rows?: number | null; num_cols?: number | null
  cells?: MigrationTableCell[]; image_path?: string | null
}
interface MigrationSection {
  section_number?: string | null; title: string
  page_start: number; page_end: number; elements: MigrationElement[]
}
interface MigrationDocument {
  version: string; document_Uid: string
  metadata: Record<string, unknown>; sections: MigrationSection[]
}
```

---

## 6. End-to-End Flows

### 6.1 Upload → Extraction → Repository Refresh
1. User clicks **Upload SOPs**, drags/picks `.pdf`/`.docx` files (client rejects other extensions immediately with an inline error).
2. `POST /documents/upload/batch` (multipart). Backend validates each file, writes accepted ones to `uploads/{document_id}{ext}`, creates a `BatchJob` with all documents `queued`, returns it synchronously.
3. Frontend stores `job_id`, starts polling `GET /jobs/{job_id}` every 1.5s; `JobProgressBanner` renders live counts/progress.
4. Backend's single worker dequeues documents **one at a time** and runs the 9-stage pipeline (§4.5) per document, mutating that document's `DocumentJob` fields as it goes (visible on the next poll).
5. Each document's pipeline ends by writing `output/{document_id}_v2.json` and upserting a `sop_records` row (new row if `gpdat_version` increased, in-place metadata update otherwise).
6. When every document in the batch is `completed`/`failed`, `BatchJob.status` finalizes and polling stops; the frontend re-fetches `GET /sops` to pick up newly completed rows and dismiss-ably keeps the banner visible until the user closes it.

### 6.2 Review Flow
1. From the repository list or the content view, a reviewer changes status via `PATCH /sops/{id}/status`.
2. `status` values are fully interchangeable; there's no enforced review workflow ordering — the UI just always shows all three actions with the current one disabled/highlighted.

### 6.3 View Content Flow
1. `SopTable`/`SopGrid` "View SOP" links to `/sops/{record.id}`.
2. `SopContentView` resolves `id → SopRecord` (`GET /sops/{id}`) then `SopRecord.document_Uid → MigrationDocument` (`GET /documents/v2/{document_Uid}/json`).
3. User navigates sections via the left nav or Previous/Next; only the active section's elements render on the right, independently scrollable from the nav and from the fixed sidebar.
4. Image/icon URLs in the fetched JSON are already backend-rewritten to `/documents/{document_id}/assets/{filename}`; the frontend only needs to prefix them with `API_BASE` (`assetUrl()`).

### 6.4 Delete Flow ("smart cleanup")
1. `ConfirmDialog` warns that files will also be removed **if no other version remains**.
2. `DELETE /sops/{id}` removes the row; backend then counts remaining rows for that `document_uid`.
3. If none remain: best-effort delete of the upload file, the `_v2.json` output, and both asset directories. If sibling `gpdat_version` rows still exist, files are intentionally kept (they're shared, unversioned on disk).
4. Frontend removes the row optimistically from local state and shows a toast; a cleanup failure server-side is logged but never surfaces as a client error (the DB delete already succeeded).

### 6.5 Re-upload / Versioning Flow
1. Uploading a file that yields the same `document_id` as an existing record overwrites `uploads/{document_id}{ext}` in place.
2. At pipeline completion, `sop_store.upsert_record` computes `gpdat_version = MAX(existing) + 1` for that `document_uid` and inserts a **new** row (prior versions' rows, and their `status`, are untouched).
3. If instead the *same* `(document_uid, gpdat_version)` is reprocessed (e.g. a dev reload replaying the same job), the existing row's metadata is updated in place and its `status` is left exactly as the reviewer set it.
4. Deleting every row for a `document_uid` resets the next upload back to `gpdat_version = 1`, since versioning is derived live from `sop_records`, not a persisted counter.

---

## 7. Non-Functional Notes for Reimplementation

- **Concurrency**: keep the background worker pool at `concurrency=1` for any pure-Python/GIL-bound pipeline; scale by moving CPU-bound work to a real process pool or separate service if higher throughput is needed later, rather than raising thread concurrency.
- **Job state is ephemeral**: `BatchJob`/`DocumentJob` records live only in memory (`JobManager.jobs: dict`) and are lost on restart. Any "Processing"/"Failed" KPI that depends on them will reset to zero after a restart or reload with no active job — by design, not a bug. Persist job history separately if that's undesirable in a rebuild.
- **`sop_records` is the durable source of truth** for both the SOP list UI and version numbering; there is intentionally no separate counter file (a prior `upload_counters.json` design was replaced by this for exactly that reason).
- **Filenames are unversioned on disk** (`{document_id}.{ext}`, `{document_id}_v2.json`) — only the DB row is versioned via `gpdat_version`. Keep this in mind for any delete/cleanup logic: never delete shared files while sibling DB rows still reference the same `document_id`.
- **Asset URLs must be rewritten server-side** before the JSON reaches the frontend; the frontend never needs to know about `extracted_images_dir` vs. `extracted_icons_dir` — it just calls `assetUrl(path)` on whatever path is already in the JSON.
