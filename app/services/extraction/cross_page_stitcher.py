"""Cross-page table stitcher.

Detects and merges tables that span across multiple PDF pages.
Runs after TableExtractor and before IconExtractor.
"""

import re
from loguru import logger as _default_logger

from app.config.settings import Settings
from app.schemas.document import (
    RawDocument,
    ExtractedTable,
    ElementType,
    BoundingBox,
)
from app.services.extraction.base_extractor import BaseExtractor
from app.services.extraction.tables import _merge_continuation_rows


class CrossPageTableStitcher(BaseExtractor):
    """Merges continuation tables across page boundaries."""

    def __init__(self, settings: Settings, logger=None):
        self.settings = settings
        self.logger = logger or _default_logger

    def extract(self, document: RawDocument, **kwargs) -> RawDocument:
        if not self.settings.table_stitch_enabled:
            return document

        if document.metadata.file_type != "pdf":
            # DOCX handles cross-page tables natively
            return document

        self.logger.info(f"CrossPageTableStitcher: processing {document.source}")

        i = 0
        while i < len(document.pages) - 1:
            page_n = document.pages[i]
            tables_n = [el for el in page_n.elements if el.element_type == ElementType.TABLE]
            if not tables_n:
                i += 1
                continue
            last_table_n = tables_n[-1]

            for j in range(i + 1, len(document.pages)):
                page_j = document.pages[j]
                tables_j = [el for el in page_j.elements if el.element_type == ElementType.TABLE]
                if not tables_j:
                    continue
                first_table_j = tables_j[0]
                if self._should_stitch(
                    last_table_n, first_table_j, page_n, page_j, document.pages
                ):
                    self._stitch_tables(last_table_n, first_table_j, page_j)
                    continue
                break
            i += 1

        return document

    def _last_row_bbox(self, table: ExtractedTable) -> BoundingBox | None:
        """Bbox of the last data row (page-local), not the composite stitched table."""
        if table.rows:
            cells = table.rows[-1]
        elif table.headers:
            cells = table.headers
        else:
            return table.bbox
        bboxes = [c.bbox for c in cells if getattr(c, "bbox", None)]
        if not bboxes:
            return table.bbox
        return BoundingBox(
            x0=min(b.x0 for b in bboxes),
            y0=min(b.y0 for b in bboxes),
            x1=max(b.x1 for b in bboxes),
            y1=max(b.y1 for b in bboxes),
            page=bboxes[0].page,
        )

    def _should_stitch(
        self,
        table_n: ExtractedTable,
        table_n1: ExtractedTable,
        page_n,
        page_n1,
        pages=None,
    ) -> bool:
        """Evaluate if two tables are fragments of the same logical table."""
        # 1. Spatial Position Check
        if not table_n.bbox or not table_n1.bbox:
            return False

        end = self._last_row_bbox(table_n)
        if end is None:
            return False

        end_page = page_n
        if pages and end.page:
            for p in pages:
                if p.page_number == end.page:
                    end_page = p
                    break
        page_height_end = end_page.height or 792.0
        page_height_n1 = page_n1.height or 792.0

        if end.y1 < page_height_end * self.settings.table_stitch_bottom_zone_pct:
            return False

        if table_n1.bbox.y0 > page_height_n1 * self.settings.table_stitch_top_zone_pct:
            return False

        # Headings after the last row on the page where the table actually ends
        for el in end_page.elements:
            if el.element_type == ElementType.HEADING and el.bbox and el.bbox.y0 > end.y1:
                return False

        # Check for headings before table_n1 on page_n1
        for el in page_n1.elements:
            if el.bbox and el.bbox.y1 < table_n1.bbox.y0:
                if el.element_type == ElementType.HEADING:
                    return False

        # 2. Column Structure Matching
        score = 0.0

        # (a) Column Count Match (weight 0.4)
        if table_n.grid_cols == table_n1.grid_cols:
            score += 0.4
        else:
            # Strong negative signal
            return False

        # (b) Column Boundary Alignment (weight 0.4)
        avg_deviation = self._compute_boundary_deviation(table_n, table_n1)
        if avg_deviation <= 5.0:
            score += 0.4
        elif avg_deviation <= self.settings.table_stitch_column_tolerance_pt:
            score += 0.28  # 0.7 * 0.4
        elif avg_deviation <= 30.0:
            score += 0.12  # 0.3 * 0.4
        else:
            return False  # Different tables

        # (c) Header Text Similarity (weight 0.2)
        is_repeated, header_score = self._check_repeated_header(table_n, table_n1)
        score += header_score * 0.2

        if score >= self.settings.table_stitch_score_threshold:
            return True

        return False

    def _compute_boundary_deviation(self, t1: ExtractedTable, t2: ExtractedTable) -> float:
        """Compute the average deviation in x-coordinates between column boundaries."""
        def get_boundaries(t: ExtractedTable):
            b_set = set()
            # headers
            for cell in t.headers:
                if getattr(cell, 'bbox', None):
                    b_set.add(round(cell.bbox.x0, 1))
                    b_set.add(round(cell.bbox.x1, 1))
            # rows
            for row in t.rows:
                for cell in row:
                    if getattr(cell, 'bbox', None):
                        b_set.add(round(cell.bbox.x0, 1))
                        b_set.add(round(cell.bbox.x1, 1))
            return sorted(list(b_set))

        b1 = get_boundaries(t1)
        b2 = get_boundaries(t2)

        if not b1 or not b2:
            return 999.0

        # Simple approach: compare up to the minimum length
        length = min(len(b1), len(b2))
        if length == 0:
            return 999.0
            
        deviations = [abs(b1[i] - b2[i]) for i in range(length)]
        return sum(deviations) / length

    def _check_repeated_header(self, t1: ExtractedTable, t2: ExtractedTable) -> tuple[bool, float]:
        """Check if the first row of t2 is a repeated header from t1."""
        if not t1.headers:
            return False, 0.5

        header_n = [self._normalize(c.content_text) for c in t1.headers]
        
        # Determine the first row of t2 (might be in headers or rows)
        first_row_n1 = []
        if t2.headers:
            first_row_n1 = [self._normalize(c.content_text) for c in t2.headers]
        elif t2.rows:
            first_row_n1 = [self._normalize(c.content_text) for c in t2.rows[0]]

        if not first_row_n1:
            return False, 0.5

        if header_n == first_row_n1:
            return True, 1.0

        # Fuzzy match
        match_count = sum(1 for a, b in zip(header_n, first_row_n1) if a == b)
        total = max(len(header_n), len(first_row_n1))
        
        if total > 0 and (match_count / total) > 0.8:
            return True, 0.8

        return False, 0.5

    def _normalize(self, text: str) -> str:
        text = text or ""
        text = text.lower()
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    def _stitch_tables(self, base_table: ExtractedTable, continuation_table: ExtractedTable, page_n1):
        """Merge continuation_table into base_table."""
        self.logger.info(f"Stitching table from page {page_n1.page_number} into base table.")

        is_repeated, _ = self._check_repeated_header(base_table, continuation_table)
        
        rows_to_append = []
        if is_repeated:
            # If t2 has headers, they are the repeated ones, so just append t2.rows
            if continuation_table.headers:
                rows_to_append.extend(continuation_table.rows)
            # If t2 doesn't have headers but first row matched, skip first row
            elif continuation_table.rows:
                rows_to_append.extend(continuation_table.rows[1:])
        else:
            # Append everything
            if continuation_table.headers:
                rows_to_append.append(continuation_table.headers)
            rows_to_append.extend(continuation_table.rows)

        base_table.rows.extend(rows_to_append)

        if base_table.headers:
            combined = [base_table.headers] + list(base_table.rows)
            combined = _merge_continuation_rows(combined)
            base_table.headers = combined[0]
            base_table.rows = combined[1:]
        else:
            base_table.rows = _merge_continuation_rows(base_table.rows)

        # Update composite bounding box
        if base_table.bbox and continuation_table.bbox:
            base_table.bbox = BoundingBox(
                x0=min(base_table.bbox.x0, continuation_table.bbox.x0),
                y0=base_table.bbox.y0,
                x1=max(base_table.bbox.x1, continuation_table.bbox.x1),
                y1=continuation_table.bbox.y1,
                page=base_table.bbox.page,
            )

        # Update content label
        num_headers = len(base_table.headers) if base_table.headers else 0
        total_rows = len(base_table.rows) + (1 if base_table.headers else 0)
        base_table.content = f"[Table: {base_table.grid_cols} cols × {total_rows} rows (stitched)]"

        # Remove continuation table from its page
        page_n1.elements = [el for el in page_n1.elements if el is not continuation_table]

        # Re-sequence elements on page N+1
        for i, el in enumerate(page_n1.elements):
            el.sequence = i
