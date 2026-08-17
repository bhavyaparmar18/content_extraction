# Highlight Color Extraction — Implementation Plan

## Background

The user wants to extract **text highlight / background colors** from PDF and DOCX documents so that highlighted spans appear in the final JSON output. This is critical for documents that use colored backgrounds to call out important text (e.g., infographic boxes with specific HEX colors like `#D2F2F7`, `#00E47C`).

### Current State

The codebase already has **scaffolding** for highlights at every layer — but none of it is wired up:

| Layer | What exists | What's missing |
|---|---|---|
| **Schemas** | `ExtractedElement.highlight_color`, `HighlightSpan` model, `HighlightNode` AST node, `ElementType.HIGHLIGHT` | ✅ Ready — no changes needed |
| **PDF Parser** | Reads PyMuPDF spans with `flags`, `size`, `font` | ❌ Does **not** read `color` or background/highlight attributes from spans |
| **DOCX Parser** | Reads paragraph text via `para.text` | ❌ Does **not** read run-level highlight or shading XML |
| **AST Builder** | `ParagraphNode.highlights: list[HighlightSpan]` field exists | ❌ Never populated — no extractor fills it |
| **Migration Exporter** | N/A | ❌ `MigrationElement` has no `highlights` field; `to_clean_dict()` doesn't serialize them |

### Design Decision: What counts as a "highlight"?

> [!IMPORTANT]
> There are two different types of "color behind text" in documents. We need to decide which to capture:
>
> **1. Text highlight** — the yellow/green/cyan marker pen effect applied to individual runs of text. In DOCX this is `<w:highlight>`, in PDF it's a text rendering annotation.
>
> **2. Paragraph/cell shading** — a background fill on an entire paragraph or table cell. In DOCX this is `<w:shd>`, in PDF this is a colored rectangle drawn behind text. This is what the infographic boxes (Light Blue `#D2F2F7`, Accent Green `#00E47C`) use.
>
> **This plan covers both**, since the existing `HighlightSpan` model already supports character-level offsets and hex colors — it can represent either.

---

## Proposed Changes

### 1. PDF Parser — Span-Level Color Extraction

#### [MODIFY] [pdf_parser.py](file:///c:/Users/Bhavya/Desktop/Content Extraction/app/services/parser/pdf_parser.py)

**What changes:** Inside `_extract_page`, where we iterate over spans in each text block, we will:

1. **Read span foreground color** via `span["color"]` (PyMuPDF provides this as an integer RGB value).
2. **Detect background rectangles** behind text by scanning `page.get_drawings()` for filled rectangles that overlap with text block bounding boxes. PyMuPDF's drawings API returns fill colors for vector rectangles.
3. **Store per-span highlight data** in a new accumulator alongside `line_parts`, tracking `(text, start_offset, end_offset, bg_color_hex)` for each span that has a non-white/non-transparent background.
4. **Attach to `ExtractedElement`:** After building the full text, populate `highlight_color` on the element if the entire block is highlighted, or store span-level data in a new `highlight_spans` field.

**Key technical details:**
- PyMuPDF `span["color"]` is an integer; convert with `"#{:06x}".format(color_int)`.
- Background detection: call `page.get_drawings()` once per page, build a list of filled rects with their fill colors, then for each text span check if its bbox is contained within a colored rect.
- Threshold: ignore white (`#ffffff`), near-white, and transparent backgrounds.

---

### 2. DOCX Parser — Run-Level Highlight Extraction

#### [MODIFY] [docx_parser.py](file:///c:/Users/Bhavya/Desktop/Content Extraction/app/services/parser/docx_parser.py)

**What changes:** In `_classify_paragraph`, instead of using `para.text` (which strips all formatting), iterate over `para.runs` to:

1. **Read `run.font.highlight_color`** — python-docx exposes this as a `WD_COLOR_INDEX` enum (e.g., `YELLOW`, `GREEN`, `TURQUOISE`).
2. **Read paragraph-level shading** via the XML: `para._element.find(qn('w:pPr')).find(qn('w:shd'))` for the `w:fill` attribute (hex color).
3. **Read run-level shading** via `run._element.find(qn('w:rPr')).find(qn('w:shd'))` for background fill on specific runs.
4. **Build highlight spans** with character offsets as text is accumulated from runs.

**Key mapping:**
```python
# python-docx highlight_color to hex
WD_COLOR_INDEX_TO_HEX = {
    "YELLOW": "#FFFF00",
    "GREEN": "#00FF00",
    "CYAN": "#00FFFF",
    "TURQUOISE": "#00FFFF",
    "BRIGHT_GREEN": "#00FF00",
    "PINK": "#FF00FF",
    "RED": "#FF0000",
    # ...etc
}
```

---

### 3. Schema Updates — Span-Level Highlight Data on ExtractedElement

#### [MODIFY] [document.py](file:///c:/Users/Bhavya/Desktop/Content Extraction/app/schemas/document.py)

Add a lightweight `ExtractedHighlightSpan` model to carry span-level highlight data through the pipeline:

```python
class ExtractedHighlightSpan(BaseModel):
    """A highlighted range within extracted element text."""
    text: str = ""
    color_name: str = ""        # "yellow", "green", "cyan", etc.
    color_hex: str = ""         # "#FFFF00", "#00E47C", etc.
    start_offset: int = 0       # character offset in parent content
    end_offset: int = 0         # character offset (exclusive)
```

Add to `ExtractedElement`:
```python
class ExtractedElement(BaseModel):
    # ... existing fields ...
    highlight_spans: list[ExtractedHighlightSpan] = Field(default_factory=list)
```

---

### 4. AST Builder — Populate ParagraphNode.highlights

#### [MODIFY] [ast_builder.py](file:///c:/Users/Bhavya/Desktop/Content Extraction/app/services/hierarchy/ast_builder.py)

In `_make_paragraph_node`, map `ExtractedElement.highlight_spans` to `ParagraphNode.highlights` (the `HighlightSpan` model already has the right fields). Also set `ExtractedElement.highlight_color` to `ParagraphNode` metadata if the whole paragraph is one color.

---

### 5. Migration Exporter — Surface Highlights in JSON Output

#### [MODIFY] [migration.py](file:///c:/Users/Bhavya/Desktop/Content Extraction/app/schemas/migration.py)

Add a `MigrationHighlightSpan` model and a `highlights` field to `MigrationElement`:

```python
class MigrationHighlightSpan(BaseModel):
    """A highlighted span within an element's text."""
    text: str
    color: str              # hex color, e.g. "#FFFF00"
    color_name: str = ""    # named color if known
    start_offset: int
    end_offset: int
```

```python
class MigrationElement(BaseModel):
    # ... existing fields ...
    highlights: list[MigrationHighlightSpan] = Field(default_factory=list)
    background_color: Optional[str] = None  # hex, if entire element has background
```

#### [MODIFY] [migration_exporter.py](file:///c:/Users/Bhavya/Desktop/Content Extraction/app/services/export/migration_exporter.py)

In the `paragraph` and `list` handlers within `traverse()`, read `HighlightSpan` data from the AST node and populate the `MigrationElement.highlights` list.

**Expected JSON output:**
```json
{
  "element_type": "paragraph",
  "page": 9,
  "text": "Executive Summary/Introduction (short description of subject).",
  "background_color": "#D2F2F7",
  "highlights": [
    {
      "text": "Executive Summary/Introduction",
      "color": "#D2F2F7",
      "color_name": "light_blue",
      "start_offset": 0,
      "end_offset": 30
    }
  ]
}
```

---

## Open Questions

> [!IMPORTANT]
> **Q1: Granularity** — Should we always produce span-level highlights (with offsets), or is element-level `background_color` sufficient when the entire paragraph/cell has one color?
> 
> My recommendation: **both** — `background_color` for whole-element coloring, `highlights` array for partial spans. The exporter only emits each when present.

> [!IMPORTANT]
> **Q2: Table cell backgrounds** — Infographic boxes in this document are structured as tables with colored cells. Should `MigrationTableCell` also get a `background_color` field?
>
> My recommendation: **yes** — add `background_color: Optional[str] = None` to `MigrationTableCell`.

> [!IMPORTANT]
> **Q3: Color naming** — Should we attempt to map hex colors to named colors (e.g., `#D2F2F7` to `"light_blue"`, `#00E47C` to `"accent_green"`), or just output raw hex?
>
> My recommendation: output **both** `color` (hex) and `color_name` (best-effort named mapping). Unknown colors get `color_name: ""`.

---

## Verification Plan

### Automated Tests
```bash
python -m pytest tests/ -v -k "highlight"
```
- Unit test: parse a DOCX with known highlighted runs — verify `highlight_spans` populated
- Unit test: parse a PDF with colored background rectangles — verify background detection
- Integration test: full pipeline on the test PDF — verify JSON output contains `highlights` / `background_color` on the infographic sections

### Manual Verification
- Re-run the pipeline on the existing test PDF (`o_BI-VQD-24416_...`) and verify:
  - The infographic table cells on pages 4, 8, 9 have `background_color` set
  - Any highlighted text spans in the document body are captured
- Compare extracted colors against the document's stated color values (`#D2F2F7`, `#00E47C`)
