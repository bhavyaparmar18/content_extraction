"""Table extractor using pdfplumber for PDFs.

DOCX tables are already handled by the DocxParser. This extractor
will enrich PDF RawDocuments with structured table data, preserving
cell bounding boxes, merged cells, and detecting nested images/icons.
"""

import re
import uuid
import pdfplumber

from app.schemas.document import (
    BoundingBox,
    ElementType,
    ExtractedElement,
    ExtractedTable,
    ExtractedTableCell,
    ExtractedImage,
    ExtractedIcon,
    RawDocument,
)
from .base_extractor import BaseExtractor


_WATERMARK_LINE = re.compile(
    r"^(?:o|w|copy|working(?:\s+copy)?)$",
    re.IGNORECASE,
)


def clean_table_cell_text(text: str) -> str:
    """Drop watermark bleed (rotated 'Working Copy' / stray 'o') from a cell."""
    if not text:
        return ""
    lines = []
    for raw in text.replace("\u200b", "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if _WATERMARK_LINE.fullmatch(line):
            continue
        if len(line) <= 2 and line.isalpha():
            continue
        lines.append(line)
    return " ".join(lines).strip()


def _cell_has_content(cell: ExtractedTableCell | None) -> bool:
    if cell is None:
        return False
    if clean_table_cell_text(cell.content_text or ""):
        return True
    return bool(getattr(cell, "media_nodes", None))


def _merge_text_parts(parts: list[str]) -> str:
    cleaned: list[str] = []
    for part in parts:
        t = clean_table_cell_text(part)
        if t:
            cleaned.append(t)
    if not cleaned:
        return ""
    unique: list[str] = []
    for t in cleaned:
        if any(t == u or t in u for u in unique):
            continue
        superseded = [i for i, u in enumerate(unique) if u in t]
        if superseded:
            unique = [u for i, u in enumerate(unique) if i not in superseded]
            unique.append(t)
        else:
            unique.append(t)
    result = unique[0]
    for t in unique[1:]:
        if t in result:
            continue
        if result in t:
            result = t
        elif t not in result:
            result = f"{result} {t}"
    return result


def _pad_grid(rows: list[list[ExtractedTableCell]]) -> list[list[ExtractedTableCell]]:
    if not rows:
        return rows
    n_cols = max(len(r) for r in rows)
    padded: list[list[ExtractedTableCell]] = []
    for row in rows:
        new_row = list(row)
        while len(new_row) < n_cols:
            new_row.append(ExtractedTableCell(content_text=""))
        padded.append(new_row)
    return padded


def _combine_cells(cells: list[ExtractedTableCell]) -> ExtractedTableCell:
    texts = [c.content_text for c in cells if c]
    media: list = []
    seen_media: set[int] = set()
    bbox = None
    for c in cells:
        if not c:
            continue
        for m in getattr(c, "media_nodes", []) or []:
            if id(m) not in seen_media:
                media.append(m)
                seen_media.add(id(m))
        if c.bbox and bbox is None:
            bbox = c.bbox
        elif c.bbox and bbox is not None:
            bbox = BoundingBox(
                x0=min(bbox.x0, c.bbox.x0),
                y0=min(bbox.y0, c.bbox.y0),
                x1=max(bbox.x1, c.bbox.x1),
                y1=max(bbox.y1, c.bbox.y1),
                page=bbox.page,
            )
    return ExtractedTableCell(
        content_text=_merge_text_parts(texts),
        bbox=bbox,
        media_nodes=media,
        row_span=1,
        col_span=1,
        is_merge_origin=True,
    )


def _merge_continuation_rows(grid: list[list[ExtractedTableCell]]) -> list[list[ExtractedTableCell]]:
    """Join a data row whose key cell is empty — a page-break continuation.

    Does not merge into the header row (row 0). Wrapped infographic descriptions
    and Role/Responsibility rows that continue on the next page both match.
    """
    if len(grid) < 2:
        return grid
    out = [grid[0]]
    for row in grid[1:]:
        prev = out[-1]
        prev_left = prev[0] if prev else None
        this_left = row[0] if row else None
        left_is_empty = not _cell_has_content(this_left)
        prev_left_has_content = _cell_has_content(prev_left)
        rest_has_content = any(_cell_has_content(c) for c in row[1:])
        merging_into_header = prev is grid[0]
        if (
            not merging_into_header
            and left_is_empty
            and prev_left_has_content
            and rest_has_content
            and len(prev) == len(row)
        ):
            out[-1] = [_combine_cells([a, b]) for a, b in zip(prev, row)]
            continue
        out.append(row)
    return out


def collapse_sparse_grid(rows: list[list[ExtractedTableCell]]) -> list[list[ExtractedTableCell]]:
    """Drop empty padding columns, merge split description columns, join wrap rows.

    pdfplumber treats colored fills / inner icon padding / watermarks as extra
    grid lines, which turns a 2-column infographic legend into a 6×6 sparse
    table. This reconstructs the visual 2-column layout.
    """
    grid = _pad_grid(rows)
    if not grid:
        return grid

    n_cols = len(grid[0])
    occupied = [
        c for c in range(n_cols)
        if any(_cell_has_content(row[c]) for row in grid)
    ]
    if not occupied:
        return grid

    groups: list[list[int]] = []
    for col in occupied:
        if not groups:
            groups.append([col])
            continue
        prev = groups[-1]
        collides = any(
            any(_cell_has_content(row[c]) for c in prev) and _cell_has_content(row[col])
            for row in grid
        )
        if collides:
            groups.append([col])
        else:
            prev.append(col)

    collapsed = [
        [_combine_cells([row[c] for c in group]) for group in groups]
        for row in grid
    ]
    collapsed = _merge_continuation_rows(collapsed)
    for row in collapsed:
        for cell in row:
            cell.content_text = clean_table_cell_text(cell.content_text)
    return collapsed


_HEADER_LABEL = re.compile(
    r"^(role|responsibility|infographics?|description|term|meaning|name|definition|abbreviation)s?$",
    re.IGNORECASE,
)


def is_shaded_callout(rows: list[list[ExtractedTableCell]]) -> bool:
    """True when pdfplumber saw a colored text box, not a real data table."""
    if not rows or not rows[0]:
        return False
    n_cols = len(rows[0])
    if n_cols > 2:
        return False
    if n_cols == 1:
        first = clean_table_cell_text(rows[0][0].content_text)
        return not _HEADER_LABEL.match(first or "")
    return not any(clean_table_cell_text(row[0].content_text) for row in rows)


def callout_rows_to_elements(
    rows: list[list[ExtractedTableCell]],
    page: int,
    bbox: BoundingBox | None,
) -> list:
    """Flatten a callout box to icon(s) plus one paragraph."""
    texts: list[str] = []
    media: list = []
    seen: set[int] = set()
    for row in rows:
        for cell in row:
            t = clean_table_cell_text(cell.content_text or "")
            if t:
                texts.append(t)
            for m in getattr(cell, "media_nodes", None) or []:
                if id(m) not in seen:
                    media.append(m)
                    seen.add(id(m))
    merged = _merge_text_parts(texts)
    elements = list(media)
    if merged:
        elements.append(
            ExtractedElement(
                element_type=ElementType.PARAGRAPH,
                content=merged,
                page=page,
                bbox=bbox,
            )
        )
    return elements


class TableExtractor(BaseExtractor):
    """Extracts tables from PDF files, maps cells, and injects nested media."""

    def extract(self, document: RawDocument) -> RawDocument:
        if document.metadata.file_type != "pdf":
            self.logger.debug("TableExtractor: skipping non-PDF document.")
            return document

        self.logger.info(f"TableExtractor: processing {document.source}")

        try:
            with pdfplumber.open(document.source) as pdf:
                for page_idx, page in enumerate(pdf.pages):
                    if page_idx >= len(document.pages):
                        break

                    tables = page.find_tables()
                    if not tables:
                        continue

                    # Filter out nested tables (e.g. icons that pdfplumber thinks are mini-tables)
                    filtered_tables = []
                    for t in tables:
                        is_nested = False
                        for other in tables:
                            if t == other:
                                continue
                            # check if t is completely inside other
                            if (t.bbox[0] >= other.bbox[0] and t.bbox[1] >= other.bbox[1] and
                                t.bbox[2] <= other.bbox[2] and t.bbox[3] <= other.bbox[3]):
                                is_nested = True
                                break
                        if not is_nested:
                            filtered_tables.append(t)
                    tables = filtered_tables

                    # Get media on this page to check for intersections
                    doc_page = document.pages[page_idx]
                    page_media = [
                        el for el in doc_page.elements
                        if el.element_type in (ElementType.IMAGE, ElementType.ICON)
                        and el.bbox is not None
                    ]
                    page_text = [
                        el for el in doc_page.elements
                        if el.element_type not in (ElementType.IMAGE, ElementType.ICON, ElementType.TABLE)
                        and el.bbox is not None
                    ]

                    new_elements = []
                    elements_to_remove = set()
                    media_to_delete_from_disk = set()

                    for table in tables:
                        table_consumed = set()
                        table_delete_disk = set()
                        extracted = table.extract()
                        if not extracted or not any(extracted):
                            continue

                        grid_cols = len(extracted[0]) if extracted else 0
                        table_bbox = BoundingBox(
                            x0=table.bbox[0],
                            y0=table.bbox[1],
                            x1=table.bbox[2],
                            y1=table.bbox[3],
                            page=page_idx + 1,
                        )

                        # Filter out images that are actually just the table grid
                        for media in page_media:
                            mb = media.bbox
                            if mb:
                                overlap_x0 = max(mb.x0, table_bbox.x0)
                                overlap_y0 = max(mb.y0, table_bbox.y0)
                                overlap_x1 = min(mb.x1, table_bbox.x1)
                                overlap_y1 = min(mb.y1, table_bbox.y1)
                                
                                if overlap_x0 < overlap_x1 and overlap_y0 < overlap_y1:
                                    overlap_area = (overlap_x1 - overlap_x0) * (overlap_y1 - overlap_y0)
                                    media_area = (mb.x1 - mb.x0) * (mb.y1 - mb.y0)
                                    table_area = (table_bbox.x1 - table_bbox.x0) * (table_bbox.y1 - table_bbox.y0)
                                    
                                    if media_area > 0 and table_area > 0:
                                        is_vector = "VectorGraphic" in getattr(media, 'content', '')
                                        media_w = mb.x1 - mb.x0
                                        media_h = mb.y1 - mb.y0
                                        table_w = table_bbox.x1 - table_bbox.x0
                                        table_h = table_bbox.y1 - table_bbox.y0

                                        # Vector graphics from pdf_parser include a 5-point visual margin
                                        margin = 10.0
                                        is_inside = (
                                            mb.x0 >= table_bbox.x0 - margin and
                                            mb.y0 >= table_bbox.y0 - margin and
                                            mb.x1 <= table_bbox.x1 + margin and
                                            mb.y1 <= table_bbox.y1 + margin
                                        )

                                        if is_vector:
                                            # If it's a vector graphic inside the expanded table box, and it spans a large portion of width or height
                                            if is_inside and (media_w / table_w > 0.3 or media_h / table_h > 0.3 or overlap_area / table_area > 0.2):
                                                table_consumed.add(id(media))
                                                table_delete_disk.add(id(media))
                                        else:
                                            # Regular images require stricter matching to be considered "just a table border"
                                            if (overlap_area / media_area > 0.85) and (overlap_area / table_area > 0.85):
                                                table_consumed.add(id(media))
                                                table_delete_disk.add(id(media))

                        # Match cells with coordinates
                        # table.cells is a list of rows, each row is a list of (x0, y0, x1, y1)
                        # The extracted text is in 'extracted' which matches table.cells
                        structured_rows = []
                        for r_idx, (text_row, row_obj) in enumerate(zip(extracted, table.rows)):
                            structured_cells = []
                            for c_idx, (cell_text, cell_bbox_tuple) in enumerate(zip(text_row, row_obj.cells)):
                                cell_bbox = None
                                if cell_bbox_tuple:
                                    cell_bbox = BoundingBox(
                                        x0=cell_bbox_tuple[0],
                                        y0=cell_bbox_tuple[1],
                                        x1=cell_bbox_tuple[2],
                                        y1=cell_bbox_tuple[3],
                                        page=page_idx + 1,
                                    )
                                    
                                # Initialize cell
                                cell = ExtractedTableCell(
                                    content_text="",
                                    bbox=cell_bbox,
                                )

                                # Intersection with media and text
                                if cell_bbox:
                                    # Match high-quality text from PyMuPDF
                                    cell_texts = []
                                    for text_el in page_text:
                                        tb = text_el.bbox
                                        center_x = (tb.x0 + tb.x1) / 2
                                        center_y = (tb.y0 + tb.y1) / 2
                                        if (cell_bbox.x0 <= center_x <= cell_bbox.x1 and
                                            cell_bbox.y0 <= center_y <= cell_bbox.y1):
                                            cell_texts.append(text_el.content)
                                            table_consumed.add(id(text_el))
                                            
                                    if cell_texts:
                                        cell.content_text = "\n".join(cell_texts).strip()
                                    else:
                                        cell.content_text = str(cell_text).strip() if cell_text else ""

                                    for media in page_media:
                                        mb = media.bbox
                                        center_x = (mb.x0 + mb.x1) / 2
                                        center_y = (mb.y0 + mb.y1) / 2
                                        # Check if media center point is inside cell bbox
                                        if (cell_bbox.x0 <= center_x <= cell_bbox.x1 and
                                            cell_bbox.y0 <= center_y <= cell_bbox.y1):
                                            cell.media_nodes.append(media)
                                            table_consumed.add(id(media))
                                            
                                structured_cells.append(cell)
                            structured_rows.append(structured_cells)

                        # Very basic merge detection based on None cells in pdfplumber output
                        # In pdfplumber, a merged cell typically has content in the top-left cell, 
                        # and None in the continuation cells.
                        for r_idx, row in enumerate(structured_rows):
                            for c_idx, cell in enumerate(row):
                                if cell.content_text == "" and not cell.media_nodes:
                                    # It might be a continuation. Look left and up
                                    # This is a simplified merge detection heuristic.
                                    if c_idx > 0 and structured_rows[r_idx][c_idx-1].content_text:
                                        # Horizontal merge
                                        origin = structured_rows[r_idx][c_idx-1]
                                        origin.col_span += 1
                                        cell.is_merge_origin = False
                                        cell.merge_origin_ref = "horizontal"
                                    elif r_idx > 0 and structured_rows[r_idx-1][c_idx].content_text:
                                        # Vertical merge
                                        origin = structured_rows[r_idx-1][c_idx]
                                        origin.row_span += 1
                                        cell.is_merge_origin = False
                                        cell.merge_origin_ref = "vertical"

                        structured_rows = collapse_sparse_grid(structured_rows)
                        grid_cols = len(structured_rows[0]) if structured_rows else 0

                        if is_shaded_callout(structured_rows):
                            # Colored icon+text boxes are not tables. Leave the original
                            # lines and small icons on the page so list detection and
                            # Y-binding still work. Only drop the fill/grid artwork.
                            elements_to_remove.update(table_delete_disk)
                            media_to_delete_from_disk.update(table_delete_disk)
                            continue

                        elements_to_remove.update(table_consumed)
                        media_to_delete_from_disk.update(table_delete_disk)

                        headers = structured_rows[0] if structured_rows else []
                        data_rows = structured_rows[1:] if len(structured_rows) > 1 else []

                        table_el = ExtractedTable(
                            content=f"[Table: {len(headers)} cols × {len(data_rows)} rows]",
                            page=page_idx + 1,
                            sequence=0,
                            bbox=table_bbox,
                            grid_cols=grid_cols,
                            headers=headers,
                            rows=data_rows,
                        )
                        new_elements.append(table_el)

                    if new_elements:
                        # Filter out elements that got embedded inside tables
                        import pathlib
                        filtered_elements = []
                        for el in doc_page.elements:
                            if id(el) in elements_to_remove:
                                # If we are dropping an image (e.g. a vector graphic grid), delete it from disk
                                if id(el) in media_to_delete_from_disk and el.element_type == ElementType.IMAGE and getattr(el, 'image_path', ''):
                                    try:
                                        pathlib.Path(el.image_path).unlink(missing_ok=True)
                                    except Exception as err:
                                        self.logger.warning(f"Could not delete table vector image {el.image_path}: {err}")
                            else:
                                filtered_elements.append(el)
                                
                        doc_page.elements = filtered_elements
                        
                        doc_page.elements.extend(new_elements)
                        
                        # Re-sort elements on this page by their Y-coordinate
                        doc_page.elements.sort(
                            key=lambda el: el.bbox.y0 if el.bbox else 0.0
                        )
                        
                        # Re-assign sequences
                        for i, el in enumerate(doc_page.elements):
                            el.sequence = i

        except Exception as e:
            self.logger.error(f"TableExtractor failed on {document.source}: {e}")

        return document
