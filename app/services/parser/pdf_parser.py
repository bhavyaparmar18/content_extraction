"""Concrete PDF parser using PyMuPDF (fitz).

Extracts text blocks with coordinates/font info, embedded images,
and document-level metadata from digital PDF files.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import fitz  # PyMuPDF

from app.config.settings import Settings
from app.core import sop_store
from app.services.extraction.metadata_extractor import SOPMetadataExtractor
from app.schemas.document import (
    BoundingBox,
    DocumentMetadata,
    ElementType,
    ExtractedElement,
    ExtractedHeading,
    ExtractedImage,
    PageContent,
    RawDocument,
)
from .base_parser import BaseParser


class PDFParser(BaseParser):
    """Parse digital PDF files into a structured RawDocument."""

    # Heuristic: text whose font size is >= this is likely a heading.
    _HEADING_FONT_SIZE_THRESHOLD = 13.0

    # ── Public interface ────────────────────────────────────────────

    def parse(self, file_path: str, document_id: str | None = None) -> RawDocument:
        """Open *file_path*, extract all pages, and return a RawDocument."""
        self._validate_file(file_path)
        self.logger.info(f"PDFParser: opening {file_path}")
        self.current_document_id = document_id

        doc = fitz.open(file_path)

        metadata = self._extract_metadata(doc, file_path, document_id=document_id)
        pages: list[PageContent] = []
        
        # Load layout analyzer
        from app.services.layout.pdf_layout_analyzer import PDFLayoutAnalyzer
        layout_analyzer = PDFLayoutAnalyzer(self.settings, self.logger)

        for page_index in range(len(doc)):
            page = doc.load_page(page_index)
            page_content = self._extract_page(page, page_index + 1)
            pages.append(page_content)

        doc.close()
        self.logger.info(
            f"PDFParser: extracted {len(pages)} page(s) from {file_path}"
        )

        raw_doc = RawDocument(
            source=file_path,
            metadata=metadata,
            pages=pages,
        )

        # Apply layout analysis and reorder elements
        self.logger.info(f"PDFParser: running layout analysis on {file_path}")
        raw_doc = layout_analyzer.reorder_document(raw_doc)

        return raw_doc

    # ── Metadata ────────────────────────────────────────────────────

    def _extract_metadata(
        self, doc: fitz.Document, file_path: str, document_id: str | None = None
    ) -> DocumentMetadata:
        """Pull document-level metadata from the PDF properties and first-page table."""
        meta = doc.metadata or {}
        file_stat = Path(file_path).stat()

        doc_title, doc_name, doc_num, doc_ver, doc_type = SOPMetadataExtractor.extract_from_file(
            file_path, fallback_filename=Path(file_path).name
        )
        gpdat_version = self._resolve_gpdat_version(document_id)

        return DocumentMetadata(
            title=meta.get("title", "") or Path(file_path).stem,
            author=meta.get("author", "") or "",
            subject=meta.get("subject", "") or "",
            creator=meta.get("creator", "") or "",
            creation_date=meta.get("creationDate", "") or "",
            modification_date=meta.get("modDate", "") or "",
            page_count=len(doc),
            file_type="pdf",
            file_size_bytes=file_stat.st_size,
            document_title=doc_title,
            # No dedicated "Document Name" field on some SOPs — fall back to the
            # document number (which itself may come from a "Document ID" row).
            document_name=doc_name or doc_num,
            document_number=doc_num,
            document_version=doc_ver,
            document_type=doc_type,
            duplicate_upload_count=gpdat_version,
        )

    def _resolve_gpdat_version(self, document_id: str | None) -> int:
        """Look up the next version number for this document from sop_records history."""
        if not document_id:
            return 1
        try:
            return sop_store.next_version(document_id)
        except Exception as e:  # noqa: BLE001 - store may be uninitialized (e.g. in tests)
            self.logger.debug(f"Could not resolve gpdat_version for '{document_id}': {e}")
            return 1

    # ── Single page extraction ──────────────────────────────────────

    def _extract_page(self, page: fitz.Page, page_number: int) -> PageContent:
        """Extract all text blocks and images from a single PDF page."""
        elements: list[ExtractedElement] = []
        sequence = 0

        # --- Text blocks ---
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

        for block in blocks:
            if block["type"] != 0:  # 0 = text block
                continue

            # We will process lines and split the block if a line starts with a list marker.
            # This prevents list items from being merged with preceding paragraphs,
            # or multiple list items being merged into one element.
            sub_blocks = []
            current_sub_block = []
            force_flush = False
            
            for line in block.get("lines", []):
                logical_lines = []
                current_logical_line = []
                last_x1 = None
                
                for span in line.get("spans", []):
                    span_text = span.get("text", "").strip()
                    if not span_text:
                        continue
                        
                    x0, y0, x1, y1 = span.get("bbox", (0, 0, 0, 0))
                    if last_x1 is not None:
                        gap = x0 - last_x1
                        if gap > 15.0:
                            is_list_tab = False
                            if gap <= 50.0 and len(current_logical_line) == 1:
                                prev_text = current_logical_line[0].get("text", "").strip()
                                if re.match(r"^([\u2022\u25E6\u25A0\u2023\u2043\u2219\*\-\u25CF\u25CB]|\d+(?:\.\d+)*\.?|\([a-zA-Z0-9]{1,3}\)|[a-zA-Z]\.)(\s|$)", prev_text):
                                    is_list_tab = True
                            
                            if not is_list_tab:
                                if current_logical_line:
                                    logical_lines.append(current_logical_line)
                                current_logical_line = []
                        
                    current_logical_line.append(span)
                    last_x1 = x1
                    
                if current_logical_line:
                    logical_lines.append(current_logical_line)
                    
                for log_line in logical_lines:
                    line_parts = []
                    max_font = 0.0
                    is_bold_line = False
                    first_span_bold_line = False
                    
                    lx0 = min(s.get("bbox", (0, 0, 0, 0))[0] for s in log_line)
                    ly0 = min(s.get("bbox", (0, 0, 0, 0))[1] for s in log_line)
                    lx1 = max(s.get("bbox", (0, 0, 0, 0))[2] for s in log_line)
                    ly1 = max(s.get("bbox", (0, 0, 0, 0))[3] for s in log_line)
                    line_bbox = (lx0, ly0, lx1, ly1)
                    
                    for i, span in enumerate(log_line):
                        span_text = span.get("text", "").strip()
                        line_parts.append(span_text)
    
                        font_size = span.get("size", 0.0)
                        if font_size > max_font:
                            max_font = font_size
                        font_flags = span.get("flags", 0)
                        if font_flags & 2 ** 4:
                            is_bold_line = True
                            if i == 0 and not line_parts[:-1]:  # First text span
                                first_span_bold_line = True

                    line_text = " ".join(line_parts).strip()
                    if not line_text:
                        continue
                        
                    line_stripped = line_text.replace("\u200b", "").strip()
                    # Check if this line starts a list
                    is_bullet = bool(re.match(r"^[\u2022\u25E6\u25A0\u2023\u2043\u2219\*\-\u25CF\u25CB](\s|$)", line_stripped))
                    is_number = bool(re.match(r"^(\d{1,2}\.|\([a-zA-Z0-9]{1,2}\)|[a-zA-Z]\.)(\s|$)", line_stripped))
                    is_horizontally_split = len(logical_lines) > 1
                    
                    is_column_break = False
                    if current_sub_block:
                        prev_bbox = current_sub_block[-1][-1]
                        prev_text_str = current_sub_block[-1][0].strip()
                        gap = lx0 - prev_bbox[2]
                        # If on the same horizontal line, it's a column break
                        if abs(ly0 - prev_bbox[1]) < 5.0:
                            is_column_break = True
                            # Check if it's just a tabbed list item
                            if 0 <= gap <= 50.0 and len(current_sub_block) == 1:
                                if re.match(r"^([\u2022\u25E6\u25A0\u2023\u2043\u2219\*\-\u25CF\u25CB]|\d+(?:\.\d+)*\.?|\([a-zA-Z0-9]{1,3}\)|[a-zA-Z]\.)(\s|$)", prev_text_str):
                                    is_column_break = False
                        # If horizontally completely separated
                        elif lx0 > prev_bbox[2] + 10.0 or lx1 < prev_bbox[0] - 10.0:
                            is_column_break = True
                    
                    if is_bullet or is_number or is_horizontally_split or force_flush or is_column_break:
                        # Flush current sub-block if exists
                        if current_sub_block:
                            sub_blocks.append(current_sub_block)
                        current_sub_block = [(line_text, max_font, is_bold_line, first_span_bold_line, line_bbox)]
                    else:
                        current_sub_block.append((line_text, max_font, is_bold_line, first_span_bold_line, line_bbox))
                        
                    force_flush = is_horizontally_split
                    
            if current_sub_block:
                sub_blocks.append(current_sub_block)
                
            for sub in sub_blocks:
                full_text = " ".join([t[0] for t in sub]).strip()
                if not full_text:
                    continue
                    
                # Aggregate font size and bold for the sub-block
                sub_max_font = max(t[1] for t in sub)
                sub_is_bold = any(t[2] for t in sub)
                sub_first_bold = sub[0][3]

                # Compute bbox from the sub_block's lines
                sx0 = min(t[4][0] for t in sub)
                sy0 = min(t[4][1] for t in sub)
                sx1 = max(t[4][2] for t in sub)
                sy1 = max(t[4][3] for t in sub)

                bbox = BoundingBox(
                    x0=sx0,
                    y0=sy0,
                    x1=sx1,
                    y1=sy1,
                    page=page_number,
                )

                # Filter out watermarks
                if self._is_watermark(full_text, sub_max_font, bbox, page.rect):
                    self.logger.debug(f"PDFParser: Ignored watermark: {full_text[:30]}")
                    continue

                is_heading, level = self._classify_block(
                    text=full_text,
                    max_font_size=sub_max_font,
                    is_bold=sub_is_bold,
                    first_span_bold=sub_first_bold,
                )

                if is_heading:
                    element = ExtractedHeading(
                        content=full_text,
                        page=page_number,
                        sequence=sequence,
                        bbox=bbox,
                        level=level,
                    )
                else:
                    element_type = ElementType.PARAGRAPH
                    stripped = full_text.replace("\u200b", "").strip()
                    # Bullet patterns
                    if re.match(r"^[\u2022\u25E6\u25A0\u2023\u2043\u2219\*\-\u25CF\u25CB](\s|$)", stripped):
                        element_type = ElementType.LIST_ITEM
                    # Numbered patterns (e.g. 1., (1), a.)
                    elif re.match(r"^(\d{1,2}\.|\([a-zA-Z0-9]{1,2}\)|[a-zA-Z]\.)(\s|$)", stripped):
                        element_type = ElementType.NUMBERED_STEP
                        
                    element = ExtractedElement(
                        element_type=element_type,
                        content=full_text,
                        page=page_number,
                        sequence=sequence,
                        bbox=bbox,
                    )

                elements.append(element)
                sequence += 1

        # --- Images ---
        image_elements = self._extract_images(page, page_number, sequence)
        elements.extend(image_elements)
        sequence += len(image_elements)

        # --- Vector Graphics ---
        vector_elements = self._extract_vector_graphics(page, page_number, sequence)
        elements.extend(vector_elements)
        sequence += len(vector_elements)

        # --- Reading Order Sort ---
        # Sort elements on the page by vertical (y0) then horizontal (x0) coordinate
        # to ensure vector graphics/icons and inline media are in reading order.
        elements.sort(key=lambda el: (el.bbox.y0, el.bbox.x0) if el.bbox else (0.0, 0.0))
        for idx, el in enumerate(elements):
            el.sequence = idx

        rect = page.rect
        return PageContent(
            page_number=page_number,
            elements=elements,
            width=rect.width,
            height=rect.height,
        )

    # ── Image extraction ────────────────────────────────────────────

    def _extract_images(
        self, page: fitz.Page, page_number: int, start_sequence: int
    ) -> list[ExtractedImage]:
        """Extract embedded images from a PDF page and save to disk."""
        images: list[ExtractedImage] = []
        sequence = start_sequence

        for img_index, img_info in enumerate(page.get_images(full=True)):
            xref = img_info[0]
            
            try:
                rects = page.get_image_rects(xref)
                if not rects:
                    continue
                bbox = BoundingBox(
                    x0=rects[0].x0,
                    y0=rects[0].y0,
                    x1=rects[0].x1,
                    y1=rects[0].y1,
                    page=page_number,
                )
                
                base_image = page.parent.extract_image(xref)
            except Exception:
                self.logger.warning(
                    f"PDFParser: failed to extract image xref={xref} "
                    f"on page {page_number}"
                )
                continue

            if not base_image or not base_image.get("image"):
                continue

            image_bytes = base_image["image"]
            ext = base_image.get("ext", "png")
            img_hash = hashlib.md5(image_bytes).hexdigest()[:10]
            filename = f"page{page_number}_img{img_index}_{img_hash}.{ext}"
            doc_id = getattr(self, "current_document_id", None) or "default"
            save_path = self.settings.get_document_image_dir(doc_id) / filename

            save_path.write_bytes(image_bytes)

            images.append(
                ExtractedImage(
                    content=f"[Image: {filename}]",
                    page=page_number,
                    sequence=sequence,
                    image_path=str(save_path),
                    width=base_image.get("width", 0),
                    height=base_image.get("height", 0),
                    bbox=bbox,
                )
            )
            sequence += 1

        return images

    def _extract_vector_graphics(
        self, page: fitz.Page, page_number: int, start_sequence: int
    ) -> list[ExtractedImage]:
        """Extract vector graphics by clustering drawing paths and rendering them."""
        images: list[ExtractedImage] = []
        sequence = start_sequence

        drawings = page.get_drawings()
        if not drawings:
            return images

        # Extract bounding boxes of all drawings
        rects = []
        page_rect = page.rect
        for d in drawings:
            r = d.get("rect")
            if not r:
                continue
            
            # Filter out page-wide background shapes, large background boxes/borders, and tiny specks
            if (
                r.width > page_rect.width * 0.9
                or r.height > page_rect.height * 0.9
                or r.width > 150
                or r.height > 150
                or r.width < 3
                or r.height < 3
            ):
                continue

            # Filter out simple single filled rectangles (table cell backgrounds or borders)
            items = d.get("items", [])
            if len(items) == 1 and items[0][0] == "re":
                continue

            rects.append(r)

        if not rects:
            return images

        # Cluster rects that intersect or are close to each other
        # Using 5.0 margin to group icon lines without merging adjacent elements
        CLUSTER_MARGIN = 5.0
        clusters = []

        for r in rects:
            r_expanded = r + (-CLUSTER_MARGIN, -CLUSTER_MARGIN, CLUSTER_MARGIN, CLUSTER_MARGIN)
            matched_clusters = []
            
            for idx, c in enumerate(clusters):
                if r_expanded.intersects(c):
                    matched_clusters.append(idx)
                    
            if not matched_clusters:
                clusters.append(r)
            else:
                # Merge into the first matched cluster
                first_idx = matched_clusters[0]
                clusters[first_idx] |= r
                
                # If it matched multiple clusters, merge them all into the first
                for idx in reversed(matched_clusters[1:]):
                    clusters[first_idx] |= clusters[idx]
                    clusters.pop(idx)

        # For each cluster, add a 5-pixel visual margin and render
        VISUAL_MARGIN = 5.0
        for img_index, c_rect in enumerate(clusters):
            # If the vector cluster is essentially a 1D line (horizontal or vertical), skip it.
            # We check this before adding the visual margin.
            if c_rect.is_empty or c_rect.width < 5 or c_rect.height < 5:
                continue

            # Apply margin
            c_rect = c_rect + (-VISUAL_MARGIN, -VISUAL_MARGIN, VISUAL_MARGIN, VISUAL_MARGIN)
            # Ensure it doesn't go outside the page
            c_rect = c_rect.intersect(page_rect)

            # Render
            try:
                # Use a slightly higher DPI for clarity on vectors (150 DPI)
                pix = page.get_pixmap(clip=c_rect, dpi=150)
                image_bytes = pix.tobytes("png")
                
                img_hash = hashlib.md5(image_bytes).hexdigest()[:10]
                filename = f"page{page_number}_vec{img_index}_{img_hash}.png"
                doc_id = getattr(self, "current_document_id", None) or "default"
                save_path = self.settings.get_document_image_dir(doc_id) / filename
                save_path.write_bytes(image_bytes)
                
                bbox = BoundingBox(
                    x0=c_rect.x0,
                    y0=c_rect.y0,
                    x1=c_rect.x1,
                    y1=c_rect.y1,
                    page=page_number,
                )
                
                images.append(
                    ExtractedImage(
                        content=f"[VectorGraphic: {filename}]",
                        page=page_number,
                        sequence=sequence,
                        image_path=str(save_path),
                        width=pix.width,
                        height=pix.height,
                        bbox=bbox,
                    )
                )
                sequence += 1
            except Exception as e:
                self.logger.warning(
                    f"PDFParser: failed to render vector graphic on page {page_number}: {e}"
                )

        return images

    # ── Helpers ──────────────────────────────────────────────────────

    # Pattern for numbered headings: "1.", "1.2", "10.", "5.1.3" etc.
    # \u200b is the zero-width space inserted by Google Docs / some PDF generators
    # between the number and the heading text (e.g. "1.\u200b Executive Summary:").
    _NUMBERED_HEADING_RE = re.compile(r"^\d+(?:\.\d+)*\.?[\s\u200b]")

    # Known short bold labels that are NOT structural headings (e.g. inline callouts)
    _NON_HEADING_LABELS = frozenset({
        "note", "warning", "caution", "tip", "important",
        "see also", "example", "summary",
    })

    def _is_watermark(self, text: str, max_font_size: float, bbox: BoundingBox, page_rect: fitz.Rect) -> bool:
        """Heuristic check to determine if a block is a watermark."""
        # 1. Match against configured watermark keywords
        keywords = getattr(self.settings, "watermark_keywords", [])
        if not keywords:
            keywords = ["WORKING COPY", "DRAFT", "CONFIDENTIAL", "DO NOT DISTRIBUTE", "WATERMARK"]
        
        text_upper = text.upper()
        matches_keyword = any(kw.upper() in text_upper for kw in keywords)
        
        if not matches_keyword:
            return False
            
        # 2. Check for unusually large font size, indicative of a watermark
        if max_font_size > 30.0:
            return True
            
        # 3. Check if block is roughly central or spans a large area
        page_width, page_height = page_rect.width, page_rect.height
        bbox_width = bbox.x1 - bbox.x0
        bbox_height = bbox.y1 - bbox.y0
        
        # If it matches a keyword and takes up a large portion of the page, it's likely a watermark
        if bbox_width > page_width * 0.4 or bbox_height > page_height * 0.4:
            return True
            
        return False

    @classmethod
    def _classify_block(
        cls,
        text: str,
        max_font_size: float,
        is_bold: bool,
        first_span_bold: bool = True,
    ) -> tuple[bool, int]:
        """Classify a text block as (is_heading, level).

        Returns a tuple of:
        - ``is_heading``: True if the block should be treated as a heading.
        - ``level``: Heading level (1–6). Ignored when is_heading is False.

        ``first_span_bold`` indicates whether the first non-empty span in the
        block is bold. This is used to distinguish genuine numbered headings
        (e.g. "1. Executive Summary" where the "1." is bold) from numbered
        list items (e.g. "1. Channels..." where the "1." is plain text).

        Classification rules (applied in priority order):

        1. **Font-size rule** – any block whose largest span font size meets or
           exceeds the threshold is a heading; level is derived from font size.

        2. **Numbered heading rule** – block where ALL of these hold:
           - overall block is bold AND the first span is also bold (number is bold)
           - starts with a numbered prefix (``1.``, ``5.1``, ``10.``)
           - ≤ 12 words
           Level is determined by numbering depth: ``1.`` → 1, ``1.2`` → 2.

        3a. **Label heading rule** – bold block that:
            - has ≤ 10 words, AND
            - ends with ``:``, AND
            - contains no interior sentence-ending punctuation, AND
            - is not in the known non-heading label set.
            Treated as sub-headings at level 4.

        3b. **Short title rule** – bold block that:
            - has ≤ 6 words, AND
            - does NOT start with a numbered prefix, AND
            - contains no interior sentence-ending punctuation.
            Treated as sub-headings at level 4.
            Catches labels like "Gateway (Control Plane)", "Browser Automation".

        4. **Fallback** – everything else is a paragraph.
        """
        word_count = len(text.split())
        
        # Strip zero-width spaces (\u200b) that some PDF generators insert
        stripped = text.replace("\u200b", "").strip()

        if not stripped:
            return False, 0
            
        # Bullet list items are never headings
        if re.match(r"^[\u2022\u25E6\u25A0\u2023\u2043\u2219\*\-\u25CF\u25CB](\s|$)", stripped):
            return False, 0
            
        # Rule 1: font-size based (works for documents with proper heading sizes)
        if max_font_size >= cls._HEADING_FONT_SIZE_THRESHOLD:
            return True, cls._font_size_to_level(max_font_size)

        if not is_bold:
            return False, 0

        # Rule 2: numbered heading (e.g. "1. Executive Summary", "5.1 Security")
        # Require first_span_bold so list items like "1. Channels..." (where
        # "1." is rendered in plain ArialMT) are not mistakenly promoted.
        if first_span_bold and word_count <= 12 and cls._NUMBERED_HEADING_RE.match(stripped):
            prefix_match = re.match(r"^(\d+(?:\.\d+)*)", stripped)
            depth = prefix_match.group(1).count(".") + 1 if prefix_match else 1
            level = min(depth, 3)
            return True, level

        # Helper: does this text contain interior sentence punctuation?
        def _has_sentence_punct(s: str) -> bool:
            return bool(re.search(r"[.!?]\s", s))

        # Rule 3a: short bold label ending with ":"
        if word_count <= 10 and stripped.endswith(":"):
            lower = stripped.rstrip(":").strip().lower()
            if lower not in cls._NON_HEADING_LABELS:
                if not _has_sentence_punct(stripped[:-1]):
                    return True, 4

        # Rule 3b: short bold title-style block (no colon needed)
        # e.g. "Gateway (Control Plane)", "Browser Automation", "Security Defaults"
        if word_count <= 6 and not cls._NUMBERED_HEADING_RE.match(stripped):
            if not _has_sentence_punct(stripped):
                return True, 4

        # Rule 4: fallback — bold body text
        return False, 0

    @staticmethod
    def _font_size_to_level(font_size: float) -> int:
        """Map a font size to a rough heading level (1-6)."""
        if font_size >= 24:
            return 1
        if font_size >= 20:
            return 2
        if font_size >= 16:
            return 3
        if font_size >= 14:
            return 4
        if font_size >= 13:
            return 5
        return 6
