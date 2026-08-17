"""Table extractor using pdfplumber for PDFs.

DOCX tables are already handled by the DocxParser. This extractor
will enrich PDF RawDocuments with structured table data, preserving
cell bounding boxes, merged cells, and detecting nested images/icons.
"""

import uuid
import pdfplumber

from app.schemas.document import (
    BoundingBox,
    ElementType,
    ExtractedTable,
    ExtractedTableCell,
    ExtractedImage,
    ExtractedIcon,
    RawDocument,
)
from .base_extractor import BaseExtractor


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
                                                elements_to_remove.add(id(media))
                                                media_to_delete_from_disk.add(id(media))
                                        else:
                                            # Regular images require stricter matching to be considered "just a table border"
                                            if (overlap_area / media_area > 0.85) and (overlap_area / table_area > 0.85):
                                                elements_to_remove.add(id(media))
                                                media_to_delete_from_disk.add(id(media))

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
                                            elements_to_remove.add(id(text_el))
                                            
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
                                            elements_to_remove.add(id(media))
                                            
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
