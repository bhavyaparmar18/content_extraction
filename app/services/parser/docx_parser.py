"""Concrete DOCX parser using python-docx.

Extracts paragraphs with style-based classification, tables,
embedded images, and document-level metadata from .docx files.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from docx import Document as DocxDocument
from docx.opc.constants import RELATIONSHIP_TYPE as RT

from app.config.settings import Settings
from app.services.extraction.metadata_extractor import SOPMetadataExtractor
from app.schemas.document import (
    BoundingBox,
    DocumentMetadata,
    ElementType,
    ExtractedElement,
    ExtractedHeading,
    ExtractedImage,
    ExtractedTable,
    PageContent,
    RawDocument,
)
from .base_parser import BaseParser


class DocxParser(BaseParser):
    """Parse .docx files into a structured RawDocument."""

    # Map python-docx style names → our ElementType & heading level.
    _HEADING_STYLES: dict[str, int] = {
        "Title": 1,
        "Heading 1": 1,
        "Heading 2": 2,
        "Heading 3": 3,
        "Heading 4": 4,
        "Heading 5": 5,
        "Heading 6": 6,
    }

    _LIST_STYLES: set[str] = {
        "List Bullet",
        "List Bullet 2",
        "List Bullet 3",
        "List Number",
        "List Number 2",
        "List Number 3",
        "List Paragraph",
    }

    # ── Public interface ────────────────────────────────────────────

    def parse(self, file_path: str, document_id: str | None = None) -> RawDocument:
        """Open *file_path*, extract content, and return a RawDocument."""
        self._validate_file(file_path)
        self.logger.info(f"DocxParser: opening {file_path}")
        self.current_document_id = document_id

        doc = DocxDocument(file_path)

        metadata = self._extract_metadata(doc, file_path, document_id=document_id)
        elements: list[ExtractedElement] = []
        sequence = 0
        self._current_page = 1  # Track current page number while iterating

        # --- Iterate body in document order (paragraphs + tables interleaved) ---
        from docx.table import Table as DocxTable
        from docx.text.paragraph import Paragraph
        from docx.oxml.ns import qn

        extracted_image_hashes: set[str] = set()  # track inline-extracted images to avoid duplicates
        self._extracted_hash_paths: dict[str, Path] = {}

        for block in doc.element.body:
            tag = block.tag
            if tag == qn('w:p'):
                para = Paragraph(block, doc)
                # Check for a page break BEFORE classifying so the element lands
                # on the correct (new) page.
                if self._paragraph_starts_new_page(para):
                    self._current_page += 1

                element = self._classify_paragraph(para, sequence)
                if element is not None:
                    elements.append(element)
                    sequence += 1

                # Extract inline images from this paragraph in document order
                inline_images = self._extract_inline_images(block, doc, sequence, extracted_image_hashes)
                for img_el in inline_images:
                    elements.append(img_el)
                    sequence += 1

            elif tag == qn('w:tbl'):
                table = DocxTable(block, doc)
                table_element = self._extract_table(table, sequence, doc=doc, extracted_hashes=extracted_image_hashes)
                if table_element is not None:
                    elements.append(table_element)
                    sequence += 1

        # --- Images fallback (relationship-based, catches images not found inline) ---
        image_elements = self._extract_images(doc, sequence, skip_hashes=extracted_image_hashes)
        elements.extend(image_elements)

        # Group elements into per-page PageContent objects.
        pages = self._group_elements_into_pages(elements)

        self.logger.info(
            f"DocxParser: extracted {len(elements)} element(s) across "
            f"{len(pages)} page(s) from {file_path}"
        )

        return RawDocument(
            source=file_path,
            metadata=metadata,
            pages=pages,
        )

    # ── Metadata ────────────────────────────────────────────────────

    def _extract_metadata(
        self, doc: DocxDocument, file_path: str, document_id: str | None = None
    ) -> DocumentMetadata:
        """Pull document-level metadata from DOCX core properties and first-page table."""
        props = doc.core_properties
        file_stat = Path(file_path).stat()

        doc_title, doc_name, doc_num, doc_ver, doc_type = SOPMetadataExtractor.extract_from_file(
            file_path, fallback_filename=Path(file_path).name
        )
        gpdat_version = self._next_gpdat_version(document_id)

        return DocumentMetadata(
            title=doc_title or props.title or "",
            author=props.author or "",
            subject=props.subject or "",
            creator=props.last_modified_by or "",
            creation_date=(
                props.created.isoformat() if props.created else ""
            ),
            modification_date=(
                props.modified.isoformat() if props.modified else ""
            ),
            page_count=0,  # Not available at parse time in python-docx
            file_type="docx",
            file_size_bytes=file_stat.st_size,
            document_title=doc_title,
            document_name=doc_name,
            document_number=doc_num,
            document_version=doc_ver,
            document_type=doc_type,
            gpdat_version=gpdat_version,
        )

    # ── Page-break detection ─────────────────────────────────────────

    def _paragraph_starts_new_page(self, para) -> bool:
        """Return True if *para* triggers a new page in the rendered document.

        python-docx doesn't expose page breaks through its high-level API, so
        we inspect the raw OOXML directly.  We check three sources (in order of
        reliability):

        1. ``<w:lastRenderedPageBreak/>`` — inserted by Word/LibreOffice when
           the document is saved after a full render.  Marks *layout-driven*
           overflow breaks as well as explicit ones.  Most accurate when present.
        2. Explicit run break: ``<w:br w:type="page"/>`` or ``<w:br w:type="column"/>``
        3. Section break: ``<w:sectPr>`` whose ``<w:type>`` is NOT "continuous"
           (nextPage / evenPage / oddPage all start a new page).
        """
        from docx.oxml.ns import qn

        pPr = para._element.find(qn('w:pPr'))

        # ── 1. Layout-driven breaks: <w:lastRenderedPageBreak/> ──────────
        # Word / LibreOffice embed this tag inside runs when saving a rendered
        # document.  It covers both explicit and overflow page breaks, making
        # it the most complete signal when available.
        for _ in para._element.iter(qn('w:lastRenderedPageBreak')):
            return True

        # ── 2. Explicit <w:br w:type="page"/> in any run ─────────────────
        for br in para._element.iter(qn('w:br')):
            br_type = br.get(qn('w:type'), '')
            if br_type in ('page', 'column'):
                return True

        # ── 3. Section break via <w:sectPr> in paragraph props ───────────
        if pPr is not None:
            sectPr = pPr.find(qn('w:sectPr'))
            if sectPr is not None:
                type_el = sectPr.find(qn('w:type'))
                sect_type = type_el.get(qn('w:val'), 'nextPage') if type_el is not None else 'nextPage'
                # 'continuous' does NOT start a new page; everything else does
                if sect_type != 'continuous':
                    return True

        return False

    def _group_elements_into_pages(self, elements: list[ExtractedElement]) -> list[PageContent]:
        """Group a flat list of elements into PageContent objects keyed by page number."""
        from collections import defaultdict
        page_map: dict[int, list[ExtractedElement]] = defaultdict(list)
        for el in elements:
            page_map[el.page].append(el)

        if not page_map:
            # Return a single empty page so downstream code always gets at least one page.
            return [PageContent(page_number=1, elements=[])]

        return [
            PageContent(page_number=pnum, elements=page_map[pnum])
            for pnum in sorted(page_map)
        ]

    # ── Paragraph classification ────────────────────────────────────

    def _classify_paragraph(
        self, para, sequence: int
    ) -> Optional[ExtractedElement]:
        """Classify a python-docx paragraph into a typed ExtractedElement."""
        text = para.text.strip()
        if not text:
            return None

        style_name = para.style.name if para.style else "Normal"

        # Check for watermark keywords or styles
        keywords = getattr(self.settings, "watermark_keywords", []) if hasattr(self, "settings") else getattr(self.config, "watermark_keywords", [])
        if not keywords:
            keywords = ["WORKING COPY", "DRAFT", "CONFIDENTIAL", "DO NOT DISTRIBUTE", "WATERMARK"]
        
        text_upper = text.upper()
        style_upper = style_name.upper()
        
        # If the style has 'WATERMARK' in the name, or if the text matches a keyword
        if "WATERMARK" in style_upper or any(kw.upper() in text_upper for kw in keywords):
            self.logger.debug(f"DocxParser: Ignored watermark: {text[:30]}")
            return None

        current_page = getattr(self, '_current_page', 1)

        # Check if it's a heading
        if style_name in self._HEADING_STYLES:
            return ExtractedHeading(
                content=text,
                page=current_page,
                sequence=sequence,
                level=self._HEADING_STYLES[style_name],
            )

        # Check if it's a list item
        if style_name in self._LIST_STYLES:
            # Distinguish numbered lists from bullet lists
            element_type = ElementType.LIST_ITEM
            if "Number" in style_name:
                element_type = ElementType.NUMBERED_STEP
            return ExtractedElement(
                element_type=element_type,
                content=text,
                page=current_page,
                sequence=sequence,
            )

        # Default → paragraph
        return ExtractedElement(
            element_type=ElementType.PARAGRAPH,
            content=text,
            page=current_page,
            sequence=sequence,
        )

    # ── Table extraction ────────────────────────────────────────────

    def _extract_table(
        self, table, sequence: int, doc: Optional[DocxDocument] = None,
        extracted_hashes: set[str] | None = None,
    ) -> Optional[ExtractedTable]:
        """Convert a python-docx table into an ExtractedTable with merged cell detection and cell media extraction."""
        from docx.oxml.ns import qn
        from app.schemas.document import ExtractedTableCell
        
        rows_data: list[list[ExtractedTableCell]] = []

        for row_idx, row in enumerate(table.rows):
            cell_row = []
            for col_idx, cell in enumerate(row.cells):
                tc = cell._element
                tcPr = tc.find(qn('w:tcPr'))
                
                # Column span
                col_span = 1
                if tcPr is not None:
                    gridSpan = tcPr.find(qn('w:gridSpan'))
                    if gridSpan is not None:
                        col_span = int(gridSpan.get(qn('w:val'), '1'))
                
                # Row merge status
                merge_status = "none"
                if tcPr is not None:
                    vMerge = tcPr.find(qn('w:vMerge'))
                    if vMerge is not None:
                        val = vMerge.get(qn('w:val'), 'continue')
                        merge_status = val if val == 'restart' else 'continue'
                        
                # Extract inline images from table cell
                cell_media = []
                if doc is not None and extracted_hashes is not None:
                    cell_media = self._extract_inline_images(cell._element, doc, sequence, extracted_hashes)
                    sequence += len(cell_media)

                text = cell.text.strip()
                
                ext_cell = ExtractedTableCell(
                    content_text=text,
                    col_span=col_span,
                    row_span=1,  # will resolve below
                    is_merge_origin=(merge_status != "continue"),
                    media_nodes=cell_media,
                )
                if merge_status == "continue":
                    ext_cell.merge_origin_ref = "vertical"
                    
                cell_row.append(ext_cell)
            rows_data.append(cell_row)

        if not rows_data:
            return None

        # Resolve row spans
        max_cols = max(sum(c.col_span for c in row) for row in rows_data)
        
        # Simplified row span resolution logic mapping continuations to origins
        for col_idx in range(len(rows_data[0])):  # Assume rectangular grid from docx
            origin_row = None
            for row_idx, row in enumerate(rows_data):
                if col_idx < len(row):
                    cell = row[col_idx]
                    if cell.is_merge_origin:
                        origin_row = row_idx
                    elif not cell.is_merge_origin and origin_row is not None:
                        # Increment origin's row span
                        rows_data[origin_row][col_idx].row_span += 1

        headers = rows_data[0] if rows_data else []
        data_rows = rows_data[1:] if len(rows_data) > 1 else []

        return ExtractedTable(
            content=f"[Table: {len(headers)} cols × {len(data_rows)} rows]",
            page=getattr(self, '_current_page', 1),
            sequence=sequence,
            grid_cols=max_cols,
            headers=headers,
            rows=data_rows,
        )

    # ── Image extraction ────────────────────────────────────────────

    def _extract_inline_images(
        self, paragraph_element, doc: DocxDocument, start_sequence: int,
        extracted_hashes: set[str],
    ) -> list[ExtractedImage]:
        """Extract images embedded inline within a paragraph or cell XML element.

        Looks for ``<w:drawing>`` and ``<w:pict>`` elements containing image
        relationship references (``r:embed`` or ``r:id``), and resolves them
        to actual image data via the document's relationship table.
        """
        from docx.oxml.ns import qn

        images: list[ExtractedImage] = []
        sequence = start_sequence

        # Namespace for relationships
        r_ns = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

        # Collect all rId references from inline drawings/pictures
        rids: list[str] = []

        # <w:drawing> -> <wp:inline> or <wp:anchor> -> <a:graphic> -> <a:graphicData> -> <pic:pic> -> <pic:blipFill> -> <a:blip r:embed="rId...">
        for blip in paragraph_element.iter('{http://schemas.openxmlformats.org/drawingml/2006/main}blip'):
            embed = blip.get(f'{{{r_ns}}}embed')
            if embed:
                rids.append(embed)
            # Register svgBlip partners so vector duplicates are skipped by fallback
            for s in blip.xpath('.//*[local-name()="svgBlip"]'):
                s_embed = s.get(f'{{{r_ns}}}embed')
                if s_embed and s_embed in doc.part.rels:
                    try:
                        s_bytes = doc.part.rels[s_embed].target_part.blob
                        extracted_hashes.add(hashlib.md5(s_bytes).hexdigest()[:10])
                    except Exception:
                        pass

        # <w:pict> -> <v:shape> -> <v:imagedata r:id="rId...">
        for imagedata in paragraph_element.iter('{urn:schemas-microsoft-com:vml}imagedata'):
            rid = imagedata.get(f'{{{r_ns}}}id')
            if rid:
                rids.append(rid)

        for rid in rids:
            try:
                rel = doc.part.rels.get(rid)
                if rel is None or "image" not in rel.reltype:
                    continue

                image_part = rel.target_part
                image_bytes = image_part.blob
                img_hash = hashlib.md5(image_bytes).hexdigest()[:10]

                # If already extracted, reuse the saved path so subsequent occurrences (e.g. repeated icons) retain the image
                if hasattr(self, "_extracted_hash_paths") and img_hash in self._extracted_hash_paths:
                    save_path = self._extracted_hash_paths[img_hash]
                    images.append(
                        ExtractedImage(
                            content=f"[Image: {save_path.name}]",
                            page=getattr(self, '_current_page', 1),
                            sequence=sequence,
                            image_path=str(save_path),
                        )
                    )
                    sequence += 1
                    continue

                extracted_hashes.add(img_hash)

                content_type = image_part.content_type or "image/png"
                ext = content_type.split("/")[-1]
                if ext == "jpeg":
                    ext = "jpg"

                filename = f"docx_img{sequence}_{img_hash}.{ext}"
                doc_id = getattr(self, "current_document_id", None) or "default"
                save_path = self.settings.get_document_image_dir(doc_id) / filename

                save_path.write_bytes(image_bytes)
                if hasattr(self, "_extracted_hash_paths"):
                    self._extracted_hash_paths[img_hash] = save_path

                images.append(
                    ExtractedImage(
                        content=f"[Image: {filename}]",
                        page=getattr(self, '_current_page', 1),
                        sequence=sequence,
                        image_path=str(save_path),
                    )
                )
                sequence += 1

            except Exception:
                self.logger.warning(
                    f"DocxParser: failed to extract inline image from rId {rid}"
                )
                continue

        return images

    def _extract_images(
        self, doc: DocxDocument, start_sequence: int,
        skip_hashes: set[str] | None = None,
    ) -> list[ExtractedImage]:
        """Extract embedded images from the DOCX media folder (fallback).

        Images already extracted inline (tracked by *skip_hashes*) are skipped.
        """
        images: list[ExtractedImage] = []
        sequence = start_sequence

        for rel in doc.part.rels.values():
            if "image" not in rel.reltype:
                continue

            try:
                image_part = rel.target_part
                image_bytes = image_part.blob
                content_type = image_part.content_type or "image/png"
                ext = content_type.split("/")[-1]
                if ext == "jpeg":
                    ext = "jpg"

                img_hash = hashlib.md5(image_bytes).hexdigest()[:10]

                # Skip images already extracted inline
                if skip_hashes and img_hash in skip_hashes:
                    continue

                filename = f"docx_img{sequence}_{img_hash}.{ext}"
                doc_id = getattr(self, "current_document_id", None) or "default"
                save_path = self.settings.get_document_image_dir(doc_id) / filename

                save_path.write_bytes(image_bytes)

                images.append(
                    ExtractedImage(
                        content=f"[Image: {filename}]",
                        page=getattr(self, '_current_page', 1),
                        sequence=sequence,
                        image_path=str(save_path),
                    )
                )
                sequence += 1

            except Exception:
                self.logger.warning(
                    f"DocxParser: failed to extract image from relationship "
                    f"{rel.rId}"
                )
                continue

        return images

