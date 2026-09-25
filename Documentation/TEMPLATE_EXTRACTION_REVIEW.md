# Template Extraction — Review Findings & Improvement Plan

**Status:** Draft for review
**Scope:** Template Management feature (upload → extract → JSON → migration)
**Artifact reviewed:** `data/template_output/Template_Main_GP_Docs_v1.json` (2,841 lines, 11 sections, 106 instructions, 14 icons)
**Reference template:** `Template Main GP Docs` (Boehringer Ingelheim GP Docs master template)

---

## 1. Executive Summary

The template extraction pipeline was built and runs end-to-end: it uploads a `.docx`, parses it, detects blue instruction text, extracts icons, splits global rules from section content, and writes a structured JSON file. Section detection and global-rule separation work correctly.

However, the feature does not yet deliver its business purpose. Three issues block it:

1. **The migration engine never reads the extracted JSON.** It re-parses the raw `.docx` with the older, thinner `TemplateInspector`. Everything the extraction pipeline produces is currently write-only.
2. **Template formatting attributes are not captured.** Background/shading colours are not extracted at all, and merged table cells are duplicated rather than merged — so the two formatting rules the template enforces (coloured infographic callouts, role-responsibility matrix layout) cannot be reproduced.
3. **Icons carry no meaning.** All 14 extracted icons are labelled `semantic_meaning: "unknown"`, so there is no basis for deciding which icon belongs where in a migrated SOP.

The net effect: a migrated SOP today would not honour the template's icon rules, would not reproduce the coloured callout boxes, and would render complex tables incorrectly.

None of these are architectural dead-ends. The pipeline structure is sound; the gaps are additive fixes plus one wiring change.

---

## 2. Business Requirements vs. Current State

The template drives migration through four mechanisms. Current coverage:

| # | Requirement | Current state | Severity |
|---|---|---|---|
| 1 | **Global instructions** (blue text before first section) must be captured as document-wide rules | Captured correctly — 13 global instructions extracted | Works |
| 2 | **Section-level instructions** (blue text within each section) must guide content for that section | Captured, but as unstructured prose; text is partially mangled | Partial |
| 3 | **Icons** — migrated SOP must use only template icons, placed per their associated rule | Icon files extracted, but meaning is `unknown` and migration pulls icons from the *source SOP* instead | **Not met** |
| 4 | **Background / font colours** — coloured callout boxes must carry the correct colour + description | Not extracted at all; migration uses hardcoded colour guesses | **Not met** |
| 5 | **Table formatting** — tables must reproduce template structure | Merged cells duplicated; no widths, borders, shading, or text rotation | **Not met** |

---

## 3. Detailed Findings

Findings are ordered by priority. Each includes the evidence, the impact, and the recommended fix.

---

### P0-1 — Migration does not consume the extracted template JSON

**What:** When a migration is triggered with a `template_id`, the API resolves the record and passes only the raw uploaded `.docx` forward:

```python
# app/api/migration.py (lines 142-143)
if record and record.get("upload_path"):
    target_template_path = Path(record["upload_path"])
```

The migrator then runs `TemplateInspector` on that `.docx`, producing a `TemplateRawProfile` that contains paragraph text, blue flags, and table statistics — but no icons, no colours, and no section contract. The `output_path` column (pointing at the extracted JSON) is never read by the migration flow.

**Impact:** The entire template extraction feature has no effect on migration output. Any schema improvement is invisible until this is wired.

**Fix:** Have `DocxMigrator` load the extracted `TemplateExtractionOutput` JSON as its primary template contract, keeping `TemplateInspector` only as a fallback for ad-hoc uploaded templates that have not been extracted yet.

---

### P0-2 — Background / shading colours are never extracted

**What:** The DOCX shading element (`w:shd`) is never read anywhere in the parser layer. A search across `app/services/parser/docx_parser.py` for `shd`, `fill`, `background`, or `highlight_color` returns no matches. Consequently the entire 2,841-line output JSON contains **zero** `background_color` values.

The four coloured infographic boxes in the template (Executive Summary = blue, Explanation = green, Attention = pink, Key-take-away = yellow) were extracted as plain paragraphs. The only surviving trace of colour is the prose inside them:

```json
{
  "element_type": "paragraph",
  "text": "Explanation section (more detailed information on the subject). It is provided with green colour .",
  "font_color_hex": "0075FF",
  "icons": [ { "semantic_meaning": "unknown", ... } ]
}
```

**Secondary defect — field overloading:** `TemplateDocxParser` writes the *font* colour into a field named `highlight_color`:

```python
# app/services/parser/template_parser.py (line 152)
base_element.highlight_color = color_hex
```

`TemplateExtractionService` then reads that same field into `background_color`:

```python
# app/services/extraction/template_extractor.py (lines 552-553)
if not background_color:
    background_color = getattr(item, "highlight_color", None)
```

So even if shading were populated, font colour would leak into the background colour field.

**Impact:** Coloured callout boxes cannot be reproduced from template data. Migration currently falls back to invented colours (see P1-3).

**Fix:**
- Read `w:shd/@w:fill` from both `tcPr` (table cell shading) and `pPr` (paragraph shading) in the parser.
- Store it in a dedicated `shading_hex` / `background_color` field, separate from font colour.
- Rename the font-colour field to `font_color_hex` throughout to remove the overload.

---

### P0-3 — Merged table cells are duplicated instead of merged

**What:** Cells spanning multiple grid positions are emitted once per position, each carrying the full span value. From the extracted "Table B" (role-responsibility matrix) header row:

```json
{ "row_index": 0, "col_index": 0, "row_span": 1, "col_span": 2, "text": "Process Step" },
{ "row_index": 0, "col_index": 1, "row_span": 1, "col_span": 2, "text": "Process Step" },
{ "row_index": 0, "col_index": 2, "row_span": 1, "col_span": 5, "text": "Tasks for"    },
{ "row_index": 0, "col_index": 3, "row_span": 1, "col_span": 5, "text": "Tasks for"    },
{ "row_index": 0, "col_index": 4, "row_span": 1, "col_span": 5, "text": "Tasks for"    },
{ "row_index": 0, "col_index": 5, "row_span": 1, "col_span": 5, "text": "Tasks for"    },
{ "row_index": 0, "col_index": 6, "row_span": 1, "col_span": 5, "text": "Tasks for"    }
```

"Process Step" appears twice, "Tasks for" five times. The correct structure is 6 columns: `Process Step` (col 0, **row**_span 2) and `Tasks for` (col 1, col_span 5). The extractor reported `num_cols: 7`. The vertical merge on "Process Step" was also flattened — it reappears as a separate cell in row 1.

Root cause: `_convert_table` filters on `is_merge_origin`, but that flag is not being set correctly, so python-docx's repeated-cell behaviour passes through unfiltered.

**Missing formatting attributes:** A search of the output JSON for `width`, `alignment`, `text_direction`, `borders`, `style_name`, `bold`, or `col_widths` returns **no matches**. The rotated vertical header text (`[Role 1]` … `[Role 5]`) has no `text_direction` marker.

**Impact:** Any table with merged cells migrates with a wrong column count and duplicated headers. The role-responsibility matrix — a mandatory template table — cannot be reproduced.

**Fix:**
- Correct the merge-origin detection (compare `tc` element identity across grid positions, the standard python-docx approach).
- Add table fidelity fields: `col_widths_pt`, `header_rows`, `style_name`, and per-cell `shading_hex`, `text_direction`, `valign`, `bold`.

---

### P1-1 — All icons have `semantic_meaning: "unknown"`

**What:** Every one of the 14 extracted icons is unclassified. The cause is that the perceptual-hash reference library is an empty stub:

```json
// data/config/icon_library.json
{ "warning": [], "ppe": [], "info": [] }
```

`IconExtractor` compares each candidate against this library and falls back to `"unknown"`:

```python
# app/services/extraction/icons.py (line 118)
semantic_meaning=matched_meaning or "unknown",
```

**Impact:** The migration planner has no basis for deciding which icon applies to which content. The rule "every icon is associated with a particular description or instruction" cannot be enforced.

**Fix:** Two viable approaches, not mutually exclusive:
- **Seed the library** from this master template once — each icon's meaning is derivable from the blue instruction text sitting beside it, which the pipeline already captures cleanly in `associated_text`.
- **LLM labelling at extraction time** — pass each icon's `associated_text` to the summariser model to produce a `semantic_meaning` and a `usage_rule`. More robust for templates we have not seen before.

---

### P1-2 — Icon IDs are random UUIDs; duplicates get different IDs

**What:** The same physical image file receives a new UUID on each occurrence. `tpl_img35_4e310735a6.png` appears in the output with three different `icon_id` values (lines 782, 2139, 2371 of the output JSON).

**Impact:** Impossible to build a stable icon → meaning registry. IDs change on every re-extraction, so nothing downstream can reference an icon reliably.

**Fix:** Key icons by content hash (already computed for deduplication) and promote them to a top-level `icon_library` array. Elements then reference icons by `icon_key` instead of embedding duplicate objects.

---

### P1-3 — Callout styles are hardcoded; callout icons come from the source SOP

**What:** The migration engine's callout colours are invented constants, not template-derived:

```python
# app/services/migration/callout_builder.py (lines 18-47)
DEFAULT_CALLOUT_STYLES = {
    "executive_summary": CalloutStyleDef(
        background_color_hex="#D9E1F2",
        left_border_color_hex="#2F5597",
        icon_description="Document / Summary icon",
    ),
    "explanation": CalloutStyleDef(
        background_color_hex="#E2EFDA",
        left_border_color_hex="#385723",
        icon_description="Question mark icon",
    ),
    ...
}
```

Icons are described in prose (`"Question mark icon"`) rather than referenced by file. The icon actually embedded is taken from the **source SOP**, not the template:

```python
# app/services/migration/callout_builder.py (lines 88-96)
icon_path = None
if source_element:
    if source_element.icons:
        icon_path = source_element.icons[0].path
```

`plan.callout_styles` is populated by the LLM planner, which is also guessing colours rather than reading them from the template.

**Impact:** Directly violates the rule "the migrated SOP should only use icons present in the template." Callout colours will not match the approved template palette.

**Fix:** Emit a `callout_styles` registry in the template JSON built from actual shading values, and have `CalloutBuilder` resolve both colour and icon from it. Remove the hardcoded defaults (or keep them only as a last-resort fallback).

---

### P2-1 — Blue run text is mangled

**What:** Blue runs are stripped individually then joined with spaces:

```python
# app/services/parser/template_parser.py (lines 147-150)
if run_blue and run.text.strip():
    blue_parts.append(run.text.strip())

instruction_text = " ".join(blue_parts) if blue_parts else para.text.strip()
```

Word splits text into runs arbitrarily (spell-check state, formatting boundaries), so this corrupts the text. Observed in the output:

- `"Id entif y where this document is applicable ."`
- `"Directive/SOP / Work Instruction/ Guidance"`
- `"It is provided with yellow colo u r ."`

**Impact:** Instruction text fed to the LLM planner is degraded, reducing plan quality. Also looks broken in the UI.

**Fix:** Concatenate raw `run.text` with `"".join(...)` and strip once at the end.

---

### P2-2 — Absolute machine-specific paths in output

**What:** Every asset path is absolute:

```json
"image_path": "C:\\POCs\\content_extraction\\data\\template_icons\\Template_Main_GP_Docs\\tpl_img18_aca4277a1f.png"
```

**Impact:** JSON is not portable across machines or environments, and cannot be served directly to the frontend without rewriting.

**Fix:** Store paths relative to the data root; resolve to absolute at consumption time, and rewrite to servable URLs in the API layer (the SOP side already does this via `_rewrite_asset_paths`).

---

### P2-3 — `STYLE_INSTRUCTION` sentinel stored in a hex colour field

**What:** When a blue instruction is detected via paragraph style name rather than colour value, the literal string `"STYLE_INSTRUCTION"` is written into `font_color_hex`. Roughly half the extracted instructions carry this value instead of a hex code.

**Impact:** Type pollution — consumers cannot parse the field as a colour. Also loses the real colour information.

**Fix:** Add a separate `detection_method` field (`"run_color" | "paragraph_color" | "style_name" | "theme_color"`) and keep `font_color_hex` strictly hex-or-null.

---

### P2-4 — Icon/instruction tables are flattened, discarding their container

**What:** `_convert_table` classifies 2-column icon+text tables as layout containers and drops the table entirely:

```python
# app/services/extraction/template_extractor.py (lines 657-669)
is_layout_container = (
    num_cols == 2
    and len(table_instructions) == num_rows
    and len(table_icon_refs) == num_rows
    and ...
)
if is_layout_container:
    return None, table_instructions   # table not emitted
```

**Impact:** Reasonable for plain icon+text instruction rows, but the same path destroys the coloured infographic boxes, which are also 2-column icon+text tables — and those carry the shading that must be preserved.

**Fix:** Once shading extraction exists, only unwrap when the row has **no** background colour. Shaded rows should be promoted to a `callout` element type instead of being flattened.

---

## 4. Proposed Target JSON Structure

The conceptual shift: today the JSON describes *what the template looks like*. For migration it must describe *what the migrated SOP is required to obey*.

### 4.1 Top-level envelope

```json
{
  "version": "2.0",
  "template_id": "Template_Main_GP_Docs",
  "template_name": "Main Template",
  "metadata": { "...": "unchanged" },

  "icon_library":    [ /* new — see 4.2 */ ],
  "callout_styles":  [ /* new — see 4.3 */ ],
  "global_rules":    { /* restructured — see 4.4 */ },
  "sections":        [ /* restructured — see 4.5 */ ],

  "totals": { "sections": 11, "instructions": 106, "icons": 9, "callouts": 4 }
}
```

### 4.2 Icon library (new, top-level, deduplicated)

Replaces inline duplicated icon objects with random UUIDs.

```json
"icon_library": [
  {
    "icon_key": "applicability_roles",
    "content_hash": "842cc359b1",
    "asset_path": "template_icons/Template_Main_GP_Docs/tpl_img23.png",
    "semantic_meaning": "target_roles",
    "display_name": "Person / Roles",
    "usage_rule": "Use in APPLICABILITY when describing which roles must follow the document",
    "source_instruction": "Explain which target roles must follow this document, ensuring accurate training assignment...",
    "allowed_sections": ["APPLICABILITY"],
    "render": { "width_pt": 26, "height_pt": 26 },
    "occurrences": 1
  }
]
```

`semantic_meaning` + `usage_rule` are what allow the planner to decide *where* an icon belongs. Elements reference icons by `icon_key`.

### 4.3 Callout style registry (new)

Built from real template shading. Replaces `CalloutBuilder.DEFAULT_CALLOUT_STYLES`.

```json
"callout_styles": [
  {
    "callout_type": "explanation",
    "display_name": "Explanation",
    "background_color_hex": "#00FF00",
    "left_border_color_hex": "#385723",
    "border_width_pt": 3.5,
    "icon_key": "explanation_question",
    "font_color_hex": "#0075FF",
    "trigger_instruction": "Use \"Explanation\" infographic in the document as needed to accompany more difficult parts of the text",
    "placement_rule": "as_needed",
    "template_source": { "section": "PROCESS", "page": 11 }
  }
]
```

The `trigger_instruction` is already captured today as blue text; pairing it with the shaded row immediately below yields type + colour + icon in a single pass.

### 4.4 Structured global rules (restructured)

Hard constraints should be machine-enforceable rather than re-derived by the LLM on every run.

```json
"global_rules": {
  "instructions": [
    {
      "instruction_id": "gr_009",
      "text": "Change the font - Arial is the official font to be used",
      "scope": "global",
      "directive_type": "prohibition",
      "machine_rule": { "rule": "font_family", "value": "Arial", "enforce": "hard" }
    },
    {
      "instruction_id": "gr_003",
      "text": "Follow the instructions in blue text and delete the blue text before finalization.",
      "scope": "global",
      "directive_type": "requirement",
      "machine_rule": { "rule": "strip_blue_text", "value": true, "enforce": "hard" }
    }
  ]
}
```

`directive_type` vocabulary: `prohibition`, `requirement`, `guidance`, `placeholder_hint`, `icon_usage`, `formatting`.

Hard rules from the template's "Do NOT" list that can be enforced programmatically rather than by the LLM:

| Template rule | Machine rule |
|---|---|
| Arial is the official font | `font_family = Arial` |
| Do not change Header and Footer | `preserve_headers_footers = true` |
| Do not add new chapters (subchapters allowed) | `allow_new_h1 = false` |
| Do not create/change TOC manually | `toc_auto_generated = true` |
| Delete blue text before finalization | `strip_blue_text = true` |
| Do not change the initial page | `skip_cover_page = true` |

### 4.5 Section contract (restructured)

The key distinction migration needs: **black text = skeleton to preserve verbatim**, **blue text = instruction to follow then delete**.

```json
{
  "section_number": "2",
  "title": "APPLICABILITY",
  "heading_style": "Heading 1",
  "required": true,
  "content_editable": false,
  "allows_subsections": true,
  "placeholders": ["${vault:title__v}", "[Role 1]"],
  "skeleton_elements":      [ /* black content copied verbatim into output */ ],
  "authoring_instructions": [ /* blue content — followed, then removed */ ],
  "icons_expected":  ["applicability_roles", "applicability_units", "applicability_geography"],
  "callouts_allowed": ["executive_summary", "explanation"]
}
```

### 4.6 Table element with formatting fidelity

```json
{
  "element_type": "table",
  "table_role": "role_responsibility_matrix",
  "style_name": "BI Table Grid",
  "num_rows": 7,
  "num_cols": 6,
  "header_rows": 2,
  "col_widths_pt": [180, 40, 40, 40, 40, 40],
  "constraints": { "max_pages": 1 },
  "cells": [
    {
      "row_index": 0, "col_index": 0, "row_span": 2, "col_span": 1,
      "text": "Process Step",
      "shading_hex": "#FFFFFF", "text_direction": "horizontal",
      "valign": "center", "bold": true
    },
    {
      "row_index": 0, "col_index": 1, "row_span": 1, "col_span": 5,
      "text": "Tasks for",
      "shading_hex": "#FFFFFF", "text_direction": "horizontal",
      "valign": "center", "bold": true
    },
    {
      "row_index": 1, "col_index": 1, "row_span": 1, "col_span": 1,
      "text": "[Role 1]",
      "shading_hex": "#DEEAF6", "text_direction": "btLr",
      "valign": "bottom", "bold": false
    }
  ]
}
```

`"Table cannot exceed one page"` is currently a blue instruction; it becomes a `constraints` entry the validator can check.

---

## 5. Implementation Plan

Estimates are rough and assume familiarity with the existing pipeline.

### Phase 1 — Unblock (highest value, smallest change)

| # | Task | Files | Est. |
|---|---|---|---|
| 1.1 | Wire `DocxMigrator` to load the extracted template JSON; keep `TemplateInspector` as fallback | `app/api/migration.py`, `app/services/migration/docx_migrator.py` | 1–2 d |
| 1.2 | Extract `w:shd` shading (cell + paragraph level) | `app/services/parser/docx_parser.py`, `template_parser.py` | 1 d |
| 1.3 | Fix merged-cell duplication (`is_merge_origin` detection) | `app/services/extraction/template_extractor.py` | 1 d |
| 1.4 | Separate `font_color_hex` from `background_color` (remove `highlight_color` overload) | `template_parser.py`, `template_extractor.py`, `app/schemas/template.py` | 0.5 d |

### Phase 2 — Make the JSON migration-ready

| # | Task | Files | Est. |
|---|---|---|---|
| 2.1 | Top-level `icon_library` with content-hash keys; elements reference by `icon_key` | `app/schemas/template.py`, `template_extractor.py` | 1 d |
| 2.2 | Populate `semantic_meaning` + `usage_rule` (seed library and/or LLM labelling) | `app/services/extraction/icons.py`, new labelling step | 1–2 d |
| 2.3 | Build `callout_styles` registry from template shading | `template_extractor.py`, `app/schemas/template.py` | 1 d |
| 2.4 | Drive `CalloutBuilder` from the registry; source icons from template, not source SOP | `app/services/migration/callout_builder.py`, `docx_migrator.py` | 1 d |
| 2.5 | Table fidelity fields (`col_widths_pt`, `header_rows`, per-cell shading / direction / valign / bold) | `docx_parser.py`, `template_extractor.py` | 1–2 d |

### Phase 3 — Structure and hygiene

| # | Task | Files | Est. |
|---|---|---|---|
| 3.1 | Structured instructions (`directive_type`, `machine_rule`) + validator enforcement | `app/schemas/template.py`, `migration_validator.py` | 1–2 d |
| 3.2 | Section contract (`skeleton_elements` vs `authoring_instructions`, `placeholders`, `required`) | `template_extractor.py`, `app/schemas/template.py` | 1–2 d |
| 3.3 | Fix blue-run text join (`"".join`) | `template_parser.py` | 0.5 h |
| 3.4 | Relative asset paths + API URL rewriting | `template_extractor.py`, `app/api/templates.py` | 0.5 d |
| 3.5 | Replace `STYLE_INSTRUCTION` sentinel with `detection_method` field | `template_parser.py`, `app/schemas/template.py` | 0.5 d |
| 3.6 | Promote shaded 2-column rows to `callout` elements instead of flattening | `template_extractor.py` | 0.5 d |

**Rough total:** ~12–17 developer-days.

---

## 6. Verification Plan

Re-extract the master template after each phase and assert against the output JSON:

| Check | Expected result |
|---|---|
| Shading extracted | ≥ 4 elements carry a non-null `background_color` / `shading_hex` (the four infographic callouts) |
| Merged cells correct | Table B reports `num_cols: 6`; `"Process Step"` appears once with `row_span: 2`; `"Tasks for"` once with `col_span: 5` |
| Icon meanings | Zero icons with `semantic_meaning: "unknown"` |
| Icon stability | Re-extracting twice produces identical `icon_key` values; each physical image appears once in `icon_library` |
| Callout registry | 4 entries with colours matching the template (not the hardcoded `#D9E1F2` / `#E2EFDA` / `#FCE4D6` / `#FFF2CC` set) |
| Text integrity | No mangled instruction strings (`"Id entif y"`, `"colo u r"`) |
| Path portability | No absolute paths (`C:\\`) in the output JSON |
| End-to-end | Migrate one SOP with a selected template; the output `.docx` contains template icons only, correct callout colours, and a correctly structured role matrix |

Regression: existing SOP extraction tests must continue to pass, since the parser changes touch shared code (`docx_parser.py`).

---

## 7. Decisions Needed

1. **Icon meaning strategy** — seed a static icon library for known templates (deterministic, cheap, needs manual curation per template), or LLM-label at extraction time (generalises to new templates, adds cost and non-determinism)? A hybrid — seeded library first, LLM fallback for unmatched icons — is likely the best balance.
2. **Schema version bump** — introduce the restructured output as `version: "2.0"` and re-extract existing templates, or extend `1.0` additively for backward compatibility?
3. **Scope of hard-rule enforcement** — how many of the "Do NOT" rules should be enforced programmatically in the validator versus left to the LLM planner? Programmatic enforcement is more reliable but less flexible for Guidance documents, where the template explicitly allows chapter adjustments.
4. **Shaded-row handling** — should every shaded 2-column row become a callout, or only those matching a known `callout_type`? Affects whether unrecognised coloured boxes are preserved or dropped.
5. **Priority** — is Phase 1 (wiring + the two formatting blockers) sufficient for the next demo, with Phases 2–3 scheduled after?

---

## Appendix — Files Reviewed

| File | Role |
|---|---|
| `data/template_output/Template_Main_GP_Docs_v1.json` | Extraction output under review |
| `app/schemas/template.py` | Template output schema |
| `app/services/parser/template_parser.py` | DOCX parsing + blue-font detection |
| `app/services/extraction/template_extractor.py` | Pipeline orchestration + output building |
| `app/services/extraction/icons.py` | Icon detection and classification |
| `app/services/migration/callout_builder.py` | Callout box rendering |
| `app/services/migration/template_inspector.py` | Legacy template profiling (migration-time) |
| `app/services/migration/schemas.py` | Migration plan / callout style models |
| `app/api/migration.py` | Migration endpoint and template resolution |
| `app/schemas/migration.py` | Migration element / table cell models |
| `data/config/icon_library.json` | Icon reference hash library (currently empty) |
| `template_management_implementation_plan.md` | Original feature plan |
