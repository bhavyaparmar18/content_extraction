# Implementation Walkthrough: Layout Extraction Fixes

This document summarizes the changes made to resolve the limitations in cross-page table stitching and inline icon alignment.

## 1. Cross-Page Table Stitching

Previously, the pipeline processed tables strictly on a per-page basis. This resulted in tables spanning multiple pages being split into separate `ExtractedTable` objects.

**What was changed:**
- Created `app/services/extraction/cross_page_stitcher.py` which implements a `CrossPageTableStitcher` pipeline pass.
- Integrated the stitcher into `job_manager.py`, `api/extract.py`, and `api/documents.py` to run immediately after the standard `TableExtractor`.
- Added configuration thresholds to `app/config/settings.py` to control stitching sensitivity:
  - `table_stitch_enabled` (Default: `True`)
  - `table_stitch_score_threshold` (Default: `0.7`)
  - `table_stitch_column_tolerance_pt` (Default: `15.0`)
  - `table_stitch_bottom_zone_pct` (Default: `0.75`)
  - `table_stitch_top_zone_pct` (Default: `0.20`)

**How it works:**
The stitcher evaluates the last table on Page N against the first table on Page N+1. It checks spatial positioning (does it span across the page break?) and scores the match based on column count, vertical column boundary alignment, and fuzzy matching of repeated headers. If a match is found, it appends the data rows from Page N+1 into the base table, drops any repeated headers, and recalculates a unified bounding box spanning both pages.

## 2. Inline Icon Alignment (Spatial Grouping)

Previously, the XY-cut reading order algorithm naively sorted leaf blocks by `y0` (top edge). If an inline warning icon's bounding box started even 0.1 points higher than its adjacent text, it was sorted before the text, causing the exporter to attach the icon to the previous section/chunk.

**What was changed:**
- Modified `app/services/layout/pdf_layout_analyzer.py` to include a new `_group_inline_icons` pass.
- This pass runs after the standard reading order sorting but before column region assignment.

**How it works:**
The layout analyzer identifies icon candidates and searches for horizontally adjacent text blocks (paragraphs, headings, table cells) that share the same vertical band (`max(y0) < min(y1)`). Once the closest text block is identified, the elements list is mutated so that the icon is bound exactly adjacent to its target text block, regardless of minor `y0` differences. This ensures deterministic behavior when the migration exporter processes the AST.

> [!TIP]
> Both features are now active in the default configuration. When reprocessing PDFs, tables split across pages will now be merged, and icons should accurately align with their intended paragraphs.
