"""Concrete DOCX parser using python-docx.

Extracts paragraphs with style-based classification, tables,
embedded images, and document-level metadata from .docx files.
"""

from __future__ import annotations

import hashlib
import math
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
    ExtractedFloat,
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

    # Word's highlight palette (w:highlight/@w:val). White is not a highlight.
    _HIGHLIGHT_HEX: dict[str, str] = {
        "black": "000000",
        "blue": "0000FF",
        "cyan": "00FFFF",
        "darkBlue": "00008B",
        "darkCyan": "008B8B",
        "darkGray": "A9A9A9",
        "darkGreen": "006400",
        "darkMagenta": "8B008B",
        "darkRed": "8B0000",
        "darkYellow": "808000",
        "green": "00FF00",
        "lightGray": "D3D3D3",
        "magenta": "FF00FF",
        "red": "FF0000",
        "yellow": "FFFF00",
    }

    # Geometry for floating pictures. These describe Word's wrap model, not
    # any one SOP: a side wrap only groups following blocks while they still
    # start beside the picture.
    _EMU_PER_INCH = 914400
    _TWIP_PER_INCH = 1440
    _MIN_SIDE_COLUMN_IN = 1.25
    _CHAR_WIDTH_EM = 0.45
    _SIDE_WRAPS = {
        "wrapSquare": "square",
        "wrapTight": "tight",
        "wrapThrough": "through",
    }
    _WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"

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
        self._doc = doc
        self._default_font_pt = self._document_font_pt(doc)

        body_blocks = list(doc.element.body)
        index = 0
        while index < len(body_blocks):
            block = body_blocks[index]
            tag = block.tag
            if tag == qn('w:p'):
                para = Paragraph(block, doc)
                # Check for a page break BEFORE classifying so the element lands
                # on the correct (new) page.
                if self._paragraph_starts_new_page(para):
                    self._current_page += 1

                element = self._classify_paragraph(para, sequence)
                layout = None
                if element is None or element.element_type != ElementType.HEADING:
                    layout = self._side_float(block)

                if layout is not None:
                    float_el, consumed, extra_images = self._build_float(
                        body_blocks, index, layout, element, doc, sequence, extracted_image_hashes,
                    )
                    if float_el is not None:
                        elements.append(float_el)
                        sequence += 1
                        for img_el in extra_images:
                            img_el.sequence = sequence
                            elements.append(img_el)
                            sequence += 1
                        index += consumed
                        continue

                if element is not None:
                    elements.append(element)
                    sequence += 1

                # Extract inline images from this paragraph in document order.
                # A picture that shares a list paragraph must stay tied to that
                # item, otherwise the list is split around the image.
                anchor_is_list_item = element is not None and element.element_type in (
                    ElementType.LIST_ITEM,
                    ElementType.NUMBERED_STEP,
                )
                inline_images = self._extract_inline_images(
                    block, doc, sequence, extracted_image_hashes,
                    anchor_is_list_item=anchor_is_list_item,
                )
                for img_el in inline_images:
                    elements.append(img_el)
                    sequence += 1

            elif tag == qn('w:tbl'):
                table = DocxTable(block, doc)
                table_element = self._extract_table(table, sequence, doc=doc, extracted_hashes=extracted_image_hashes)
                if table_element is not None:
                    elements.append(table_element)
                    sequence += 1
            index += 1

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

    # ── Shading / formatting helpers ─────────────────────────────────

    @staticmethod
    def _shading_fill(props_el) -> Optional[str]:
        """Return the ``w:shd`` fill hex from a ``tcPr``/``pPr``, or None when unset.

        Word writes ``w:fill="auto"`` for "no fill", which is not a colour.
        """
        from docx.oxml.ns import qn

        if props_el is None:
            return None
        shd = props_el.find(qn('w:shd'))
        if shd is None:
            return None
        fill = (shd.get(qn('w:fill')) or "").strip().upper().lstrip("#")
        # ``FFFFFF`` is the default "no colour" Word writes onto runs and
        # paragraph marks; treating it as a background highlights the document.
        if len(fill) != 6 or fill in {"AUTO", "NIL", "NONE", "FFFFFF"}:
            return None
        return fill

    def _ensure_numbering(self, para) -> None:
        """Map ``numId`` → ``{ilvl: numFmt}`` from ``word/numbering.xml`` once."""
        if getattr(self, "_num_formats", None) is not None:
            return
        self._num_formats = {}
        try:
            root = para.part.numbering_part._element
        except Exception:
            return

        from docx.oxml.ns import qn

        abstracts: dict[str, dict[str, str]] = {}
        for abstract in root.findall(qn("w:abstractNum")):
            abstract_id = abstract.get(qn("w:abstractNumId"))
            if abstract_id is None:
                continue
            levels: dict[str, str] = {}
            for lvl in abstract.findall(qn("w:lvl")):
                ilvl = lvl.get(qn("w:ilvl"))
                fmt = lvl.find(qn("w:numFmt"))
                if ilvl is not None and fmt is not None:
                    levels[ilvl] = fmt.get(qn("w:val")) or "decimal"
            abstracts[abstract_id] = levels

        for num in root.findall(qn("w:num")):
            num_id = num.get(qn("w:numId"))
            abstract_ref = num.find(qn("w:abstractNumId"))
            if not num_id or abstract_ref is None:
                continue
            levels = dict(abstracts.get(abstract_ref.get(qn("w:val")) or "", {}))
            for override in num.findall(qn("w:lvlOverride")):
                ilvl = override.get(qn("w:ilvl"))
                lvl = override.find(qn("w:lvl"))
                if ilvl is None or lvl is None:
                    continue
                fmt = lvl.find(qn("w:numFmt"))
                if fmt is not None:
                    levels[ilvl] = fmt.get(qn("w:val")) or "decimal"
            self._num_formats[num_id] = levels

    def _list_from_numbering(self, para) -> tuple[Optional[ElementType], Optional[int]]:
        """Classify a paragraph from ``w:numPr``, independent of its style name.

        ``numId`` 0 and ``numFmt`` ``none`` mean numbering was removed. Bullets
        stay unordered; every other format is an ordered step.
        """
        from docx.oxml.ns import qn

        self._ensure_numbering(para)
        pPr = para._element.find(qn("w:pPr"))
        if pPr is None:
            return None, None
        numPr = pPr.find(qn("w:numPr"))
        if numPr is None:
            return None, None

        num_id_el = numPr.find(qn("w:numId"))
        ilvl_el = numPr.find(qn("w:ilvl"))
        num_id = num_id_el.get(qn("w:val")) if num_id_el is not None else None
        ilvl = ilvl_el.get(qn("w:val")) if ilvl_el is not None else "0"
        if not num_id or num_id == "0":
            return None, None

        try:
            ilvl_int = int(ilvl)
        except ValueError:
            ilvl_int = 0

        levels = self._num_formats.get(num_id, {})
        fmt = levels.get(ilvl)
        if fmt is None:
            fmt = levels.get("0", "decimal")
        if fmt == "none":
            return None, None
        if fmt == "bullet":
            return ElementType.LIST_ITEM, ilvl_int
        return ElementType.NUMBERED_STEP, ilvl_int

    @staticmethod
    def _iter_content_runs(para):
        """Yield the runs that make up a paragraph's visible text, in order.

        Includes direct runs, hyperlink runs, and runs stored in a content
        control (``w:sdt``). ``para.text`` skips content controls, which is
        where the preamble table keeps its values. Paragraph-mark properties
        (``pPr/rPr``) are not runs and are never yielded.
        """
        yield from DocxParser._iter_block_runs(para._element)

    @staticmethod
    def _iter_block_runs(element):
        from docx.oxml.ns import qn

        # Tag comparison rather than xpath: content controls inserted from raw
        # XML do not always carry the ``w`` prefix on their own nsmap.
        for child in element:
            if child.tag == qn("w:r"):
                yield child
            elif child.tag == qn("w:hyperlink"):
                yield from (inner for inner in child if inner.tag == qn("w:r"))
            elif child.tag == qn("w:sdt"):
                content = child.find(qn("w:sdtContent"))
                if content is None:
                    continue
                for inner in content:
                    if inner.tag == qn("w:p"):
                        yield from DocxParser._iter_block_runs(inner)
                    elif inner.tag == qn("w:hyperlink"):
                        yield from (run for run in inner if run.tag == qn("w:r"))
                    elif inner.tag == qn("w:r"):
                        yield inner

    @classmethod
    def _visible_text(cls, para) -> str:
        """Paragraph text, including content-control values."""
        return "".join(run.text or "" for run in cls._iter_content_runs(para))

    @staticmethod
    def _cell_paragraphs(tc, doc) -> list:
        """Paragraphs in a cell, including those wrapped in a content control.

        python-docx's ``cell.paragraphs`` only returns direct ``w:p`` children,
        so a value stored as ``w:tc/w:sdt/w:sdtContent/w:p`` is invisible.
        """
        from docx.oxml.ns import qn
        from docx.text.paragraph import Paragraph

        found = []
        for child in tc:
            if child.tag == qn("w:p"):
                found.append(Paragraph(child, doc))
            elif child.tag == qn("w:sdt"):
                content = child.find(qn("w:sdtContent"))
                if content is None:
                    continue
                for paragraph in content.findall(qn("w:p")):
                    found.append(Paragraph(paragraph, doc))
        return found

    @classmethod
    def cell_visible_text(cls, cell) -> str:
        """Cell text, including values stored in content controls."""
        paragraphs = cls._cell_paragraphs(cell._tc, cell)
        parts = [text for paragraph in paragraphs if (text := cls._visible_text(paragraph).strip())]
        if parts:
            return "\n".join(parts)
        return (cell.text or "").strip()

    def _run_highlight(self, rPr) -> tuple[Optional[str], Optional[str]]:
        """Return ``(color_name, color_hex)`` for one run, or ``(None, None)``.

        Marker-pen ``w:highlight`` wins over character shading. ``none`` and
        white fills are not highlights.
        """
        from docx.oxml.ns import qn

        if rPr is None:
            return None, None
        highlight = rPr.find(qn("w:highlight"))
        if highlight is not None:
            name = (highlight.get(qn("w:val")) or "").strip()
            if name and name.lower() != "none":
                return name, self._HIGHLIGHT_HEX.get(name)
        fill = self._shading_fill(rPr)
        if fill:
            return None, fill
        return None, None

    def _paragraph_highlights(self, para, stripped: str) -> list:
        """Run-level highlights whose offsets index *stripped* (``para.text.strip()``)."""
        from docx.oxml.ns import qn

        from app.schemas.document import ExtractedHighlightSpan

        pieces: list[tuple[str, Optional[str], Optional[str]]] = []
        for run in self._iter_content_runs(para):
            text = run.text or ""
            if not text:
                continue
            name, color_hex = self._run_highlight(run.find(qn("w:rPr")))
            pieces.append((text, name, color_hex))

        raw = "".join(text for text, _, _ in pieces)
        lead = len(raw) - len(raw.lstrip())
        limit = len(stripped)

        merged: list[tuple[int, int, Optional[str], Optional[str]]] = []
        cursor = 0
        for text, name, color_hex in pieces:
            start, end = cursor, cursor + len(text)
            cursor = end
            if name is None and color_hex is None:
                continue
            if merged and merged[-1][1] == start and merged[-1][2] == name and merged[-1][3] == color_hex:
                prev = merged[-1]
                merged[-1] = (prev[0], end, name, color_hex)
            else:
                merged.append((start, end, name, color_hex))

        spans = []
        for start, end, name, color_hex in merged:
            clipped_start = max(0, start - lead)
            clipped_end = min(limit, end - lead)
            if clipped_end <= clipped_start:
                continue
            piece = stripped[clipped_start:clipped_end]
            if not piece.strip():
                continue
            spans.append(
                ExtractedHighlightSpan(
                    text=piece,
                    color_name=name or "",
                    color_hex=color_hex or "",
                    start_offset=clipped_start,
                    end_offset=clipped_end,
                )
            )
        return spans

    @classmethod
    def _paragraph_is_bold(cls, para) -> bool:
        """True when every visible run of *para* is explicitly bold."""
        from docx.oxml.ns import qn

        seen = False
        for run in cls._iter_content_runs(para):
            if not (run.text or "").strip():
                continue
            seen = True
            rPr = run.find(qn("w:rPr"))
            bold = rPr.find(qn("w:b")) if rPr is not None else None
            if bold is None:
                return False
            val = (bold.get(qn("w:val")) or "true").lower()
            if val in {"0", "false", "off"}:
                return False
        return seen

    # ── Paragraph classification ────────────────────────────────────

    def _classify_paragraph(
        self, para, sequence: int
    ) -> Optional[ExtractedElement]:
        """Classify a python-docx paragraph into a typed ExtractedElement."""
        text = self._visible_text(para).strip()
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
        list_type, ilvl = self._list_from_numbering(para)

        element: ExtractedElement
        if style_name in self._HEADING_STYLES:
            element = ExtractedHeading(
                content=text,
                page=current_page,
                sequence=sequence,
                level=self._HEADING_STYLES[style_name],
                style_name=style_name,
            )
        elif list_type is not None:
            element = ExtractedElement(
                element_type=list_type,
                content=text,
                page=current_page,
                sequence=sequence,
                outline_level=ilvl,
            )
        elif style_name in self._LIST_STYLES:
            # Style-name fallback for files whose numbering part is missing.
            element_type = ElementType.LIST_ITEM
            if "Number" in style_name:
                element_type = ElementType.NUMBERED_STEP
            element = ExtractedElement(
                element_type=element_type,
                content=text,
                page=current_page,
                sequence=sequence,
            )
        else:
            element = ExtractedElement(
                element_type=ElementType.PARAGRAPH,
                content=text,
                page=current_page,
                sequence=sequence,
            )

        from docx.oxml.ns import qn
        element.shading_hex = self._shading_fill(para._element.find(qn('w:pPr')))
        element.highlight_spans = self._paragraph_highlights(para, element.content)
        if (
            len(element.highlight_spans) == 1
            and element.highlight_spans[0].start_offset == 0
            and element.highlight_spans[0].end_offset == len(element.content)
        ):
            span = element.highlight_spans[0]
            element.highlight_color = span.color_name or span.color_hex or None
        if self._paragraph_is_bold(para):
            element.metadata["bold"] = True
        return element

    # ── Table extraction ────────────────────────────────────────────

    def _extract_table(
        self, table, sequence: int, doc: Optional[DocxDocument] = None,
        extracted_hashes: set[str] | None = None,
    ) -> Optional[ExtractedTable]:
        """Convert a python-docx table into an ExtractedTable with merged cell detection and cell media extraction."""
        from docx.oxml.ns import qn
        from app.schemas.document import ExtractedTableCell
        
        rows_data: list[list[ExtractedTableCell]] = []

        # ``row.cells`` is grid-aligned: a merged cell is repeated once per grid
        # position it covers, and a vertically merged position returns a wrapper
        # around the *origin* row's ``<w:tc>``. Reading gridSpan/vMerge off those
        # wrappers would therefore duplicate content, so the merge structure is
        # taken from the row's own ``tc_lst`` and walked in lockstep.
        last_origin_row_at_col: dict[int, int] = {}

        for row_idx, row in enumerate(table.rows):
            cell_row: list[ExtractedTableCell] = []
            grid_cells = row.cells
            grid_pos = 0

            for tc in row._tr.tc_lst:
                tcPr = tc.find(qn('w:tcPr'))

                col_span = 1
                if tcPr is not None:
                    gridSpan = tcPr.find(qn('w:gridSpan'))
                    if gridSpan is not None:
                        col_span = int(gridSpan.get(qn('w:val'), '1'))

                vMerge = tcPr.find(qn('w:vMerge')) if tcPr is not None else None
                is_vertical_continuation = (
                    vMerge is not None
                    and vMerge.get(qn('w:val'), 'continue') != 'restart'
                )

                for span_idx in range(col_span):
                    if grid_pos >= len(grid_cells):
                        break
                    cell = grid_cells[grid_pos]

                    if is_vertical_continuation:
                        # Extend the origin's row_span once per covered row.
                        origin_row = last_origin_row_at_col.get(grid_pos)
                        if span_idx == 0 and origin_row is not None:
                            rows_data[origin_row][grid_pos].row_span += 1
                        cell_row.append(
                            ExtractedTableCell(
                                content_text="",
                                is_merge_origin=False,
                                merge_origin_ref="vertical",
                            )
                        )
                        grid_pos += 1
                        continue

                    if span_idx > 0:
                        cell_row.append(
                            ExtractedTableCell(
                                content_text="",
                                is_merge_origin=False,
                                merge_origin_ref="horizontal",
                            )
                        )
                        grid_pos += 1
                        continue

                    # Extract inline images from table cell
                    cell_media = []
                    if doc is not None and extracted_hashes is not None:
                        cell_media = self._extract_inline_images(tc, doc, sequence, extracted_hashes)
                        sequence += len(cell_media)

                    text_direction = None
                    valign = None
                    if tcPr is not None:
                        td = tcPr.find(qn('w:textDirection'))
                        if td is not None:
                            text_direction = td.get(qn('w:val')) or None
                        va = tcPr.find(qn('w:vAlign'))
                        if va is not None:
                            valign = va.get(qn('w:val')) or None

                    cell_metadata: dict = {}
                    left_border = self._cell_left_border_color(tcPr)
                    if left_border:
                        cell_metadata["border_left_color_hex"] = left_border

                    paragraphs = self._cell_paragraphs(tc, doc) if doc is not None else []
                    blocks: list[ExtractedElement] = []
                    for paragraph in paragraphs:
                        block = self._classify_paragraph(paragraph, sequence + len(blocks))
                        if block is not None:
                            blocks.append(block)
                    content_text = "\n".join(block.content for block in blocks) or cell.text.strip()

                    cell_row.append(
                        ExtractedTableCell(
                            content_text=content_text,
                            col_span=col_span,
                            row_span=1,  # extended as vMerge continuations are seen
                            is_merge_origin=True,
                            media_nodes=cell_media,
                            shading_hex=self._shading_fill(tcPr),
                            text_direction=text_direction,
                            valign=valign,
                            bold=any(self._paragraph_is_bold(paragraph) for paragraph in paragraphs),
                            blocks=blocks,
                            metadata=cell_metadata,
                        )
                    )
                    last_origin_row_at_col[grid_pos] = row_idx
                    grid_pos += 1

            rows_data.append(cell_row)

        if not rows_data:
            return None

        # One entry per grid position, so the widest row is the grid width.
        max_cols = max(len(row) for row in rows_data)

        headers = rows_data[0] if rows_data else []
        data_rows = rows_data[1:] if len(rows_data) > 1 else []

        return ExtractedTable(
            content=f"[Table: {len(headers)} cols × {len(data_rows)} rows]",
            page=getattr(self, '_current_page', 1),
            sequence=sequence,
            grid_cols=max_cols,
            headers=headers,
            rows=data_rows,
            style_name=self._table_style_name(table),
            col_widths_pt=self._table_col_widths_pt(table),
            header_rows=self._table_header_row_count(table),
        )

    @staticmethod
    def _cell_left_border_color(tcPr) -> Optional[str]:
        """Return the cell's left border colour hex — the accent bar on callouts."""
        from docx.oxml.ns import qn

        if tcPr is None:
            return None
        borders = tcPr.find(qn('w:tcBorders'))
        if borders is None:
            return None
        left = borders.find(qn('w:left'))
        if left is None:
            return None
        color = (left.get(qn('w:color')) or "").strip().upper().lstrip("#")
        if len(color) != 6 or color == "AUTO":
            return None
        return color

    @staticmethod
    def _table_style_name(table) -> Optional[str]:
        """Return the table's ``w:tblStyle`` value, or None."""
        from docx.oxml.ns import qn

        tblPr = table._tbl.find(qn('w:tblPr'))
        if tblPr is None:
            return None
        style = tblPr.find(qn('w:tblStyle'))
        if style is None:
            return None
        return style.get(qn('w:val')) or None

    @staticmethod
    def _table_col_widths_pt(table) -> list[float]:
        """Return the declared column widths in points (``w:tblGrid`` is in twips)."""
        from docx.oxml.ns import qn

        grid = table._tbl.find(qn('w:tblGrid'))
        if grid is None:
            return []
        widths: list[float] = []
        for col in grid.findall(qn('w:gridCol')):
            raw = col.get(qn('w:w'))
            if raw is None:
                continue
            try:
                widths.append(round(int(raw) / 20.0, 1))
            except ValueError:
                continue
        return widths

    @staticmethod
    def _table_header_row_count(table) -> int:
        """Count leading rows flagged as repeating headers (``w:tblHeader``)."""
        from docx.oxml.ns import qn

        count = 0
        for row in table.rows:
            trPr = row._tr.find(qn('w:trPr'))
            if trPr is not None and trPr.find(qn('w:tblHeader')) is not None:
                count += 1
            else:
                break
        return count

    # ── Floating pictures ───────────────────────────────────────────

    @staticmethod
    def _document_font_pt(doc) -> float:
        """Body font size from the Normal style, or 11pt when the style has none."""
        try:
            size = doc.styles["Normal"].font.size
            if size is not None:
                return float(size.pt)
        except (KeyError, AttributeError):
            pass
        return 11.0

    def _content_width_inches(self, block) -> float:
        """Text column width for the section that contains ``block``.

        Uses that section's page size and left/right margins. Falls back to a
        6.5 inch column when the section properties are missing.
        """
        from docx.oxml.ns import qn

        sect = None
        node = block
        while node is not None:
            found = node.find(qn("w:pPr") + "/" + qn("w:sectPr")) if node.tag == qn("w:p") else None
            if found is None:
                found = node.find(qn("w:sectPr"))
            if found is not None:
                sect = found
                break
            node = node.getnext()
        if sect is None and getattr(self, "_doc", None) is not None:
            sect = self._doc.element.body.find(qn("w:sectPr"))
        if sect is None:
            return 6.5
        page = sect.find(qn("w:pgSz"))
        margins = sect.find(qn("w:pgMar"))
        if page is None or margins is None:
            return 6.5
        width = page.get(qn("w:w"))
        left = margins.get(qn("w:left"))
        right = margins.get(qn("w:right"))
        if not (width and width.isdigit() and left and left.isdigit() and right and right.isdigit()):
            return 6.5
        inches = (int(width) - int(left) - int(right)) / self._TWIP_PER_INCH
        return inches if inches > 1 else 6.5

    def _side_float(self, paragraph_element) -> Optional[dict]:
        """Layout of a picture whose text wraps beside it, or None.

        Inline pictures and top-and-bottom wraps stay ordinary images. A side
        wrap is ignored when the picture leaves less than a readable text
        column, because the following paragraphs then sit below it.
        """
        content_width = self._content_width_inches(paragraph_element)
        chosen = None
        for anchor in paragraph_element.iter(f"{{{self._WP}}}anchor"):
            if (anchor.get("behindDoc") or "0") == "1":
                continue
            wrap = None
            for child in anchor:
                name = child.tag.split("}")[-1]
                if name in self._SIDE_WRAPS:
                    wrap = self._SIDE_WRAPS[name]
                    break
            if wrap is None:
                continue
            extent = anchor.find(f"{{{self._WP}}}extent")
            if extent is None:
                continue
            cx = extent.get("cx") or ""
            cy = extent.get("cy") or ""
            if not (cx.isdigit() and cy.isdigit()):
                continue
            width_in = int(cx) / self._EMU_PER_INCH
            height_in = int(cy) / self._EMU_PER_INCH
            if width_in <= 0 or height_in <= 0:
                continue
            dist_l = int(anchor.get("distL") or 0) / self._EMU_PER_INCH
            dist_r = int(anchor.get("distR") or 0) / self._EMU_PER_INCH
            text_width = content_width - width_in - dist_l - dist_r
            if text_width < self._MIN_SIDE_COLUMN_IN:
                continue
            if chosen is not None and height_in <= chosen["height_in"]:
                continue
            vertical_offset = 0.0
            position_v = anchor.find(f"{{{self._WP}}}positionV")
            if position_v is not None and (position_v.get("relativeFrom") or "") == "paragraph":
                offset = position_v.find(f"{{{self._WP}}}posOffset")
                if offset is not None and (offset.text or "").lstrip("-").isdigit():
                    vertical_offset = max(0.0, int(offset.text) / self._EMU_PER_INCH)
            blip = None
            for candidate in anchor.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip"):
                blip = candidate
                break
            rid = None
            if blip is not None:
                rid = blip.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed")
            chosen = {
                "wrap": wrap,
                "align": self._float_align(anchor, content_width, width_in),
                "width_in": width_in,
                "height_in": height_in,
                "span_in": height_in + vertical_offset,
                "text_width_in": text_width,
                "rid": rid,
            }
        return chosen

    def _float_align(self, anchor, content_width: float, width_in: float) -> str:
        """Left, right, or center from the picture's horizontal position."""
        position_h = anchor.find(f"{{{self._WP}}}positionH")
        if position_h is None:
            return "left"
        align = position_h.find(f"{{{self._WP}}}align")
        if align is not None and (align.text or "") in {"left", "right", "center"}:
            return align.text
        offset = position_h.find(f"{{{self._WP}}}posOffset")
        if offset is None or not (offset.text or "").lstrip("-").isdigit():
            return "left"
        origin = int(offset.text) / self._EMU_PER_INCH
        if origin <= content_width * 0.15:
            return "left"
        if content_width - (origin + width_in) <= content_width * 0.15:
            return "right"
        return "center"

    def _paragraph_font_pt(self, para) -> float:
        from docx.oxml.ns import qn

        size = para._element.find(".//" + qn("w:sz"))
        if size is not None:
            raw = size.get(qn("w:val")) or ""
            if raw.isdigit():
                return int(raw) / 2
        try:
            style_size = para.style.font.size if para.style is not None else None
            if style_size is not None:
                return float(style_size.pt)
        except AttributeError:
            pass
        return getattr(self, "_default_font_pt", 11.0)

    def _paragraph_metrics(self, para) -> tuple[float, float, float]:
        """``(space before, line height, space after)`` in inches."""
        from docx.oxml.ns import qn

        font_pt = self._paragraph_font_pt(para)
        before = after = 0.0
        line_in = font_pt * 1.15 / 72.0
        props = para._element.find(qn("w:pPr"))
        spacing = props.find(qn("w:spacing")) if props is not None else None
        if spacing is None and para.style is not None:
            style_element = getattr(para.style, "element", None)
            style_props = style_element.find(qn("w:pPr")) if style_element is not None else None
            spacing = style_props.find(qn("w:spacing")) if style_props is not None else None
        if spacing is None:
            return before, line_in, after

        def _twips(name: str) -> float:
            raw = spacing.get(qn(name)) or ""
            return int(raw) / self._TWIP_PER_INCH if raw.isdigit() else 0.0

        before = _twips("w:before")
        after = _twips("w:after")
        line_raw = spacing.get(qn("w:line")) or ""
        rule = (spacing.get(qn("w:lineRule")) or "auto").lower()
        if line_raw.isdigit():
            line_val = int(line_raw)
            if rule == "auto":
                line_in = (font_pt * 1.15 / 72.0) * (line_val / 240.0)
            else:
                line_in = line_val / self._TWIP_PER_INCH
        return before, max(line_in, font_pt / 72.0), after

    def _block_height_inches(self, para, text_width_in: float) -> float:
        """Estimated height of a paragraph set in the column beside a picture."""
        before, line_in, after = self._paragraph_metrics(para)
        text = self._visible_text(para).strip()
        if not text:
            return before + line_in + after
        char_width = self._paragraph_font_pt(para) * self._CHAR_WIDTH_EM / 72.0
        chars_per_line = max(8.0, text_width_in / char_width) if char_width else 40.0
        lines = max(1, math.ceil(len(text) / chars_per_line))
        return before + lines * line_in + after

    @staticmethod
    def _has_picture(element) -> bool:
        return (
            next(element.iter("{http://schemas.openxmlformats.org/drawingml/2006/main}blip"), None)
            is not None
            or next(element.iter("{urn:schemas-microsoft-com:vml}imagedata"), None) is not None
        )

    def _build_float(
        self, blocks, start: int, layout: dict, anchor_element, doc, sequence: int, extracted_hashes: set,
    ) -> tuple[Optional[ExtractedFloat], int, list[ExtractedImage]]:
        """Group the anchor paragraph and the blocks that still start beside it.

        Stops at a heading, a table, a page break, or another picture. Those
        change the flow, so they stay outside the float. Returns the element,
        how many body blocks it consumed, and any other pictures from the
        anchor paragraph.
        """
        from docx.oxml.ns import qn
        from docx.text.paragraph import Paragraph

        anchor = blocks[start]
        rid = layout.get("rid")
        images = self._extract_inline_images(
            anchor, doc, sequence, extracted_hashes, only_rid=rid,
        )
        if not images:
            return None, 1, []
        picture = images[0]
        extras = (
            self._extract_inline_images(
                anchor, doc, sequence + 1, extracted_hashes, skip_rids={rid},
            )
            if rid
            else []
        )
        content: list[ExtractedElement] = []
        if anchor_element is not None:
            content.append(anchor_element)
        used = self._block_height_inches(
            Paragraph(anchor, doc), layout["text_width_in"],
        )
        consumed = 1
        for offset in range(start + 1, len(blocks)):
            nxt = blocks[offset]
            if nxt.tag != qn("w:p"):
                break
            if self._has_picture(nxt):
                break
            nxt_para = Paragraph(nxt, doc)
            if self._paragraph_starts_new_page(nxt_para):
                break
            if used >= layout["span_in"]:
                break
            classified = self._classify_paragraph(nxt_para, sequence + len(content))
            if classified is not None and classified.element_type == ElementType.HEADING:
                break
            if classified is not None:
                content.append(classified)
            used += self._block_height_inches(nxt_para, layout["text_width_in"])
            consumed += 1

        if not content:
            return None, 1, []
        return (
            ExtractedFloat(
                content=content[0].content,
                page=getattr(self, "_current_page", 1),
                sequence=sequence,
                image_path=picture.image_path,
                content_hash=picture.content_hash,
                align=layout["align"],
                wrap=layout["wrap"],
                image_width_in=layout["width_in"],
                image_height_in=layout["height_in"],
                blocks=content,
            ),
            consumed,
            extras,
        )

    # ── Image extraction ────────────────────────────────────────────

    def _extract_inline_images(
        self, paragraph_element, doc: DocxDocument, start_sequence: int,
        extracted_hashes: set[str],
        anchor_is_list_item: bool = False,
        only_rid: str | None = None,
        skip_rids: set | None = None,
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
            if only_rid is not None and rid != only_rid:
                continue
            if skip_rids and rid in skip_rids:
                continue
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
                        self._stamp_list_anchor(
                            ExtractedImage(
                                content=f"[Image: {save_path.name}]",
                                page=getattr(self, '_current_page', 1),
                                sequence=sequence,
                                image_path=str(save_path),
                                content_hash=img_hash,
                            ),
                            anchor_is_list_item,
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
                    self._stamp_list_anchor(
                        ExtractedImage(
                            content=f"[Image: {filename}]",
                            page=getattr(self, '_current_page', 1),
                            sequence=sequence,
                            image_path=str(save_path),
                            content_hash=img_hash,
                        ),
                        anchor_is_list_item,
                    )
                )
                sequence += 1

            except Exception:
                self.logger.warning(
                    f"DocxParser: failed to extract inline image from rId {rid}"
                )
                continue

        return images

    @staticmethod
    def _stamp_list_anchor(image: ExtractedImage, anchor_is_list_item: bool) -> ExtractedImage:
        """Remember that this picture lived inside a list paragraph."""
        if anchor_is_list_item:
            image.metadata["anchor_is_list_item"] = True
        return image

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
                        content_hash=img_hash,
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

