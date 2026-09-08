# Extraction & preview changes (this branch)

Developer notes for anyone picking this up. This is not a product spec. It explains **what broke**, **why**, and **how the current code approaches it**, so the pipeline is understandable without re-deriving it from git history.

SOPs that drove most of this work:

- `BI-VQD-08384` (icons, preview crash, metadata)
- `BI-VQD-09748` (PURPOSE/Applicability bleed, infographic table, page-break rows, shaded callouts)

**Re-extract is required** after these changes. Preview reads `data/output/{document_uid}_v2.json`. Code changes do not rewrite JSON already on disk. Re-upload the PDF (or re-run the extract job) so layout, tables, and icon pairing are rebuilt.

---

## Pipeline (where each fix lives)

```
PDF
  → PDFParser          (text/images, then PDFLayoutAnalyzer reading order)
  → TableExtractor     (pdfplumber grids, collapse, callout detection)
  → CrossPageTableStitcher
  → IconExtractor
  → ASTBuilder         (sections + icon-before-text)
  → MigrationExporter  (section JSON: reclaim fragments, Y-bind icons, tables)
  → *_v2.json
  → GET /documents/v2/{id}/json  (rewrite disk paths → HTTP asset URLs)
  → ElementRenderer    (icon left of text, table cells)
```

Layout analysis runs **inside** `PDFParser.parse()`, before extractors. Tables and icons run later in the job (`job_manager` / extract API). The exporter is the last chance to repair section assignment and icon pairing using AST bounding boxes.

---

## 1. Metadata extraction

**Files:** `app/services/extraction/metadata_extractor.py`, parsers, `app/api/upload.py`, `app/schemas/document.py`, `app/schemas/migration.py`

### Problem

The old extractor mixed **Title** and **Document Name**, treated `"rev"` inside “Reviewer” as a version, and used `upload_counters.json` for duplicate-upload numbering. Rotated “Working Copy” stamps leaked 1–2 letter fragments into first-page table cells.

### Approach

`extract_from_file()` returns a **5-tuple**:

```
(document_title, document_name, document_number, document_version, document_type)
```

- **Title** and **Document Name** use disjoint keyword sets. A `"Title"` cell no longer overwrites the short SOP name (`BI-VQD-…-S`).
- `"Document ID"` fills `document_number` only when Name/Number are missing.
- Keyword match is **whole-word** so `rev` in “Reviewer” is not a version.
- Packed preamble rows (`Label: value` in a trailing cell) are split with `_row_pairs()`.
- `_clean_cell_value()` drops standalone 1–2 letter lines (watermark bleed).

`generate_document_id()` still uses `doc_name or doc_title` so the uid stays stable if name is empty.

`upload_counters.json` is gone. Versioning is `SopStore.get_next_version(document_uid)` → `MAX(gpdat_version) + 1`.

---

## 2. SOP records / v2 JSON keys

**Files:** `app/stores/sop_store.py`, parsers, `MigrationExporter._extract_metadata()`, `DocxMigrationOutput.to_clean_dict()`

`sop_records` already had the columns. Parsers and the exporter now **populate** them:

| Column | Source |
|---|---|
| `document_title` | preamble “Title” |
| `document_name` | preamble “Document Name” |
| `document_number` | Number / Document ID |
| `file_type` | `pdf` / `docx` |
| `gpdat_version` | `SopStore.get_next_version(document_uid)` |

v2 JSON uses `document_Uid` (not `document_id`) and `gpdat_version` (not `duplicate_upload_count`), plus `file_type` and `document_title`.

### Re-upload behaviour

Same `document_uid` inserts a **new** `sop_records` row with incremented `gpdat_version`. Disk artefacts are **unversioned** and overwritten: `{document_uid}_v2.json`, the upload file, and `extracted_icons/` / `extracted_images/` folders. Preview always loads the latest JSON by uid, not by `gpdat_version`.

---

## 3. Icon rendering in the SOP preview

**Files:** `app/api/documents.py` (`_rewrite_asset_paths`), `frontend/src/components/content/ElementRenderer.tsx`, `frontend/src/types.ts`

### Problem

v2 `icons` are objects `{ icon_id, path, semantic_meaning }` with Windows disk paths. The UI treated them as strings and called `.split('/')` → crash / blank PURPOSE and Applicability. Paths were never HTTP URLs.

### Approach

1. `GET /documents/v2/{id}/json` walks the JSON and rewrites `path` / `image_path` / `icon_path` to `/documents/{id}/assets/{filename}`.
2. `ElementRenderer` accepts a string **or** `{path}` and loads via that asset endpoint.
3. A per-element error boundary so one bad element cannot blank the whole page.

On disk: `data/extracted_icons/{document_uid}/` and `data/extracted_images/{document_uid}/`.

Preview paragraphs/lists use `flex-row`: icon on the **left**, text on the right (matches the original SOP left-rail layout). CSS stacking icons above text was a separate bug from pairing.

---

## 4. Left-rail icons: reading order, section bleed, pairing

These three symptoms on `BI-VQD-09748` are the same layout mistake at different layers.

**What the PDF looks like**

```
1 PURPOSE
This SOP
[target]  defines the change control process which is implemented in GOTrack…

2 APPLICABILITY
This SOP is applicable:
[person]     Employees who perform change control…
[buildings]  All areas where changes are processed…
[globe]      World wide
```

Each icon sits in a **left rail** beside its paragraph, not in a second text column.

### 4a. Why PURPOSE went empty

XY-cut (`app/services/layout/reading_order.py`) looks for a vertical whitespace gap and treats it as two columns. The icon strip is a gap. Reading order became:

1. Left column: headings + short fragments (`This SOP`, `This SOP is applicable:`)
2. Right column: the real sentences (`defines the change control…`, Employees, …)

The exporter starts a new section as soon as it sees `2 APPLICABILITY`. The PURPOSE continuation was still in the pipeline **after** that heading, so it was filed under section 2. Preview only renders `sections[i].elements` — this was not a UI routing bug.

`"This SOP"` and `"defines…"` are also two PDF text blocks (line wrap beside the icon). That is expected; they must stay in the **same section**.

### 4b. Why icons landed on the wrong sentences

After the column mix-up, several rail icons sat in the buffer and were assigned to the **next** element in AST order. Sequential “bind to next” cannot know that the target icon shares a Y band with `"defines…"` and the buildings icon with `"All areas…"`.

Earlier, the exporter also bound icons to the **previous** element, which stacked them on the first paragraph. That was inverted for left-rail SOPs (icon is drawn *before* the text in reading order).

### Approach (three layers, same idea: Y overlap, not column order)

**Layout** — `PDFLayoutAnalyzer` (`app/services/layout/pdf_layout_analyzer.py`)

- Small images/icons (`width` and `height` ≤ `_RAIL_ICON_MAX_PT` = 90pt) are **excluded from XY-cut**. They are overlays, not a text column.
- After body text is ordered, `_insert_icons_before_text()` places each icon immediately **before** the paragraph it overlaps vertically (prefer text to the right of the icon, one icon per paragraph).
- `_group_inline_icons()` is the same bind, used when icons are still mixed into the element list.

**AST** — `ASTBuilder._reorder_icons()` (`app/services/hierarchy/ast_builder.py`)

Safety net after IconExtractor has turned images into `ICON`. Looks **forward and backward** for Y overlap (≥ 30% of the smaller box). Does not bind to headings (a full-width heading would steal the icon). Result: `icon, paragraph, icon, paragraph` so the exporter’s sequential buffer is already close.

**Exporter** — `MigrationExporter` (`app/services/export/migration_exporter.py`)

1. During traverse, icons still buffer onto the **next** text element (needed for DOCX / elements with no bbox). `_spread_icons()` gives extras to following siblings that have no icon (`icon, icon, para, para` → one each).
2. `_reclaim_section_continuations()`: if the last paragraph of section N does not end with `. ! ? : ;` and a later paragraph on the **same page** starts with lowercase (`defines the…`), move that paragraph back. Skips lead-ins that end with `:` (`This SOP is applicable:`).
3. `_rebind_icons_by_y()`: if bboxes exist, strip relocatable icons and attach each to the paragraph with the best Y overlap (prefer unused targets, icon to the left of text). No bbox → leave sequential pairing (existing tests).

### Tests to read

- `tests/test_ast_phase1.py` — rail icons do not pull PURPOSE text after APPLICABILITY
- `tests/test_migration_exporter.py` — reclaim continuation; Y-rebind person vs buildings

---

## 5. Infographic / sparse tables

**Files:** `app/services/extraction/tables.py` (`collapse_sparse_grid`), `MigrationExporter._collapse_migration_cells`

### Problem

The Definitions “Infographics | Description” legend is a **2-column** colored table. pdfplumber treats fill edges, icon padding, and the “Working Copy” watermark as extra grid lines → `6×6` sparse grid:

- empty padding columns
- description split across two rows
- “Explanation” shifted into a phantom middle column
- truncated + duplicated “Attention” text
- icons stored as `image_path` instead of `icon_path`

The preview table renderer is faithful to that grid (empty cells, split wording).

### Approach

`collapse_sparse_grid()` after pdfplumber extraction (and again in the exporter as a safety net):

1. **Drop empty columns** — a column is occupied only if some cell has text or media.
2. **Merge adjacent occupied columns that never both have content in the same row** — the shifted “Explanation” column and “Description” column collapse into one.
3. **Join wrap rows** — `_merge_continuation_rows()`: if the left (key) cell is empty and the previous **data** row has a key, concatenate. Does **not** merge into the header row (that would glue a page-11 continuation onto “Role | Responsibility”).
4. **`clean_table_cell_text()`** — strip watermark letters (`o`, `Working Copy`).
5. **`_merge_text_parts()`** — if one fragment is a prefix/substring of another, keep the longer string (line wrap + full sentence).
6. Exporter: image-only cells next to text become `icon_path`.

Real dense tables (Term | Meaning, Role | Responsibility with a key on every row) collide in both columns and are left alone.

---

## 6. Tables that continue on the next page

**Files:** `app/services/extraction/cross_page_stitcher.py`, `_merge_continuation_rows()` in `tables.py`

Settings (`app/config/settings.py`):

| Setting | Default | Meaning |
|---|---|---|
| `table_stitch_enabled` | `true` | Master switch |
| `table_stitch_score_threshold` | `0.7` | Column count + x-alignment + header similarity |
| `table_stitch_column_tolerance_pt` | `15` | Max average x-boundary drift |
| `table_stitch_bottom_zone_pct` | `0.75` | Last row must end in the bottom 25% of its page |
| `table_stitch_top_zone_pct` | `0.20` | Continuation must start in the top 20% of the next page |

### Problem

Roles & Responsibilities (Change Owner) spans page 9 → 10 → 11. Two bugs:

1. **New row instead of same row.** Page 10 repeats headers, Role is empty, Responsibility continues. Stitch **appended** that as a new row. Preview only had `col_index: 1`, so the bullets rendered in the **left** (Role) column.
2. **Page 11 never joined.** Stitch only looked at consecutive pages. After 9+10 merged, page 10 had **no table**, so 10→11 was skipped. The composite bbox mixed page-10 `y1` onto page 9, so the “bottom zone” check also failed for a later stitch.

### Approach

- Walk forward across pages that have **no table**; stop when the next table is a different logical table (score fails).
- Bottom-zone / heading checks use the **last data row’s** bbox and that row’s page (`_last_row_bbox`), not the stitched composite box.
- Repeated header row on the next page is dropped (`_check_repeated_header`).
- After append, `_merge_continuation_rows()` folds `empty key | leftover bullets` into the previous data row.

A heading between the two tables (e.g. `6 PROCESS` above the continuation) still blocks a stitch — that is intentional.

---

## 7. Shaded callouts extracted as tables

**Files:** `is_shaded_callout()` in `tables.py`

### Problem

**6 PROCESS** and **6.1 CHANGE CONTROL** are colored callout boxes: icon on the left, numbered list / paragraph on the right, **no real grid**. pdfplumber still emits a table from the fill. An earlier pass flattened that grid into **one paragraph**, which:

- mashed `1.`–`4.` into a single blob and dropped the leading `1.` (AST list-prefix strip)
- swallowed the checklist icon, or failed to Y-bind it
- lost nested bullets under item 2

### Approach

Those boxes are **not tables**. After collapse, if `is_shaded_callout()` is true, TableExtractor **does not** create a table and **does not** pull the original lines/icons off the page. It only deletes large fill/grid artwork.

Detected as a callout when:

- **1 column**, and the first cell is **not** a short header label (`Role`, `Infographics`, `Description`, `Term`, …), or
- **2 columns**, and the left column has **no text** (icon-only / empty).

Not a callout when the left column has labels (real data tables).

The existing pipeline then does the rest: PDF line breaks stay as list items (`1. …`, `2. …`), rail-icon Y-binding places the checklist/warning next to that block, and the exporter restores `1.` `2.` prefixes on ordered lists.

---

## 8. What to re-run / how to verify

1. Re-upload the SOP (or trigger extract). Confirm `*_v2.json` timestamp and `gpdat_version`.
2. PURPOSE should contain `"This SOP"` **and** `"defines the change control…"`, with the target icon on the second block.
3. Applicability icons: person → employees, buildings → GxP areas, globe → worldwide.
4. Definitions infographic: 2 columns, 3 legend rows, no split/duplicate description.
5. Roles table: Change Owner is **one** row across the page break; Action Owner still its own row.
6. PROCESS / 6.1: paragraph + icon, not a grid of line fragments.

### Tests

```
pytest tests/test_metadata_extractor.py tests/test_migration_exporter.py \
       tests/test_table_cleanup.py tests/test_cross_page_stitcher.py \
       tests/test_ast_phase1.py
```

Use conda env `extraction-env`.

---

## Key files (quick map)

| File | Role |
|---|---|
| `app/services/extraction/metadata_extractor.py` | Preamble 5-tuple, watermark clean |
| `app/stores/sop_store.py` | `gpdat_version` |
| `app/services/layout/pdf_layout_analyzer.py` | No icon columns; Y-bind rail icons |
| `app/services/hierarchy/ast_builder.py` | Icon before overlapping text |
| `app/services/extraction/tables.py` | Collapse sparse grids; callouts → paragraphs |
| `app/services/extraction/cross_page_stitcher.py` | Multi-page tables + empty-key row merge |
| `app/services/export/migration_exporter.py` | Section reclaim, Y-rebind, table collapse |
| `app/api/documents.py` | Asset URL rewrite for preview |
| `frontend/src/components/content/ElementRenderer.tsx` | Icon-left layout, table cells |
