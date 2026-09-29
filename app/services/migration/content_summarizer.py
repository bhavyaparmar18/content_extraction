"""Mode A: Programmatic content summarizer for fast truncation-based summaries."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional
from loguru import logger

from app.schemas.migration import DocxMigrationOutput, MigrationSection
from app.services.migration.schemas import (
    ContentSummary,
    ContentSectionSummary,
    ContentElementSummary,
    AtomicBlockSummary,
)


class ContentSummarizer:
    """Mode A — Fast programmatic truncation-based content summarizer (zero LLM calls)."""

    ORDERED_PREFIX_RE = re.compile(
        r"^(?:\(?\d{1,3}[.)]|\(?[a-zA-Z][.)]|\(?[ivxIVX]{1,5}[.)])\s+"
    )

    def summarize(
        self,
        extracted: DocxMigrationOutput,
        skip_preamble: bool = True,
    ) -> ContentSummary:
        """Condense DocxMigrationOutput into a ContentSummary."""
        logger.info(f"Summarizing extracted document '{extracted.document_id}' (Mode A: programmatic)")
        sections: list[ContentSectionSummary] = []

        for sec in extracted.sections:
            if skip_preamble and sec.title.strip().startswith("0 "):
                logger.debug(f"Skipping preamble section '{sec.title}' per configuration")
                continue
            sections.append(self._summarize_section(sec))

        doc_type = extracted.metadata.document_type if extracted.metadata else None

        return ContentSummary(
            document_id=extracted.document_id,
            document_type=doc_type,
            total_sections=len(sections),
            summarizer_mode="programmatic",
            sections=sections,
        )

    @staticmethod
    def _clean_heading_number_prefix(text: str) -> str:
        """Strip leading numbering prefix (e.g. '6.1 ', '6.5.1 ', '1. ', '6 ') from heading text."""
        if not text:
            return ""
        stripped = text.strip()
        cleaned = re.sub(r"^\d{1,2}(?:\.\d{1,2})+[.)\-:\s]*\s*", "", stripped).strip()
        if cleaned and cleaned != stripped:
            return cleaned
        cleaned = re.sub(r"^\d{1,2}\.[)\-:\s]*\s*", "", stripped).strip()
        if cleaned and cleaned != stripped:
            return cleaned
        cleaned = re.sub(r"^\d{1,2}\s+(?=[A-Z])", "", stripped).strip()
        if cleaned and cleaned != stripped:
            return cleaned
        return stripped

    def _group_into_blocks(self, sec: MigrationSection) -> list[AtomicBlockSummary]:
        """Group elements in a section into AtomicBlocks (Heading + body elements)."""
        blocks: list[AtomicBlockSummary] = []
        current_block_elements: list[int] = []
        current_heading_text: Optional[str] = None
        current_heading_level: Optional[int] = None
        block_counter = 0

        norm_sec_title = re.sub(r"^\d+[\.\s]*", "", (sec.title or "").strip()).strip().lower()

        for idx, elem in enumerate(sec.elements):
            is_subheading = False
            if elem.element_type == "heading":
                raw_text = (elem.text or "").strip()
                # Must contain letters to be a valid subsection heading (prevents isolated symbol/icon headings)
                has_letters = bool(re.search(r"[a-zA-Z]{2,}", raw_text))
                if has_letters:
                    norm_text = re.sub(r"^\d+[\.\s]*", "", raw_text).strip().lower()
                    # If this heading is identical to the section title, it's not a new subsection
                    if norm_text != norm_sec_title and norm_text not in norm_sec_title and norm_sec_title not in norm_text:
                        is_subheading = True

            if is_subheading and current_block_elements:
                # Seal current block
                blocks.append(
                    self._create_block_summary(
                        sec,
                        block_id=f"{sec.section_number or 'sec'}_block_{block_counter}",
                        heading_text=current_heading_text,
                        heading_level=current_heading_level,
                        element_indices=current_block_elements,
                    )
                )
                block_counter += 1
                current_block_elements = [idx]
                current_heading_text = self._clean_heading_number_prefix(elem.text or "")
                current_heading_level = elem.level or 2
            elif is_subheading:
                current_block_elements.append(idx)
                current_heading_text = self._clean_heading_number_prefix(elem.text or "")
                current_heading_level = elem.level or 2
            else:
                current_block_elements.append(idx)

        # Seal final block
        if current_block_elements:
            blocks.append(
                self._create_block_summary(
                    sec,
                    block_id=f"{sec.section_number or 'sec'}_block_{block_counter}",
                    heading_text=current_heading_text,
                    heading_level=current_heading_level,
                    element_indices=current_block_elements,
                )
            )

        return blocks

    def _create_block_summary(
        self,
        sec: MigrationSection,
        block_id: str,
        heading_text: Optional[str],
        heading_level: Optional[int],
        element_indices: list[int],
    ) -> AtomicBlockSummary:
        """Construct AtomicBlockSummary with 1-sentence deterministic synopsis and asset tags."""
        type_counts: dict[str, int] = {}
        lead_sentence = ""
        total_images = 0
        total_tables = 0
        total_list_items = 0

        for idx in element_indices:
            elem = sec.elements[idx]
            et = elem.element_type
            type_counts[et] = type_counts.get(et, 0) + 1

            if et == "image":
                total_images += 1
            elif et == "table":
                total_tables += 1
            elif et == "list":
                total_list_items += len(elem.items) if elem.items else 0

            # Extract lead sentence from the first paragraph
            if not lead_sentence and et == "paragraph" and elem.text and elem.text.strip():
                text = elem.text.strip()
                dot_pos = text.find(". ")
                if dot_pos != -1 and dot_pos < 180:
                    lead_sentence = text[: dot_pos + 1]
                else:
                    lead_sentence = text[:140] + ("..." if len(text) > 140 else "")

        # Fallbacks if no paragraph text was present
        if not lead_sentence:
            if total_tables > 0:
                lead_sentence = f"Contains {total_tables} data table(s)"
            elif total_list_items > 0:
                lead_sentence = f"Contains list with {total_list_items} items"
            elif total_images > 0:
                lead_sentence = f"Contains {total_images} figure(s)/image(s)"

        tags = []
        if total_images > 0:
            tags.append(f"{total_images} image(s)")
        if total_tables > 0:
            tags.append(f"{total_tables} table(s)")
        if total_list_items > 0:
            tags.append(f"list ({total_list_items} items)")

        tag_str = f" [Contains: {', '.join(tags)}]" if tags else ""
        h_str = f"{heading_text}: " if heading_text else ""
        synopsis = f"{h_str}{lead_sentence}{tag_str}".strip()

        return AtomicBlockSummary(
            block_id=block_id,
            heading_text=heading_text,
            heading_level=heading_level,
            element_indices=element_indices,
            synopsis=synopsis,
            element_type_counts=type_counts,
        )

    def _summarize_section(self, sec: MigrationSection) -> ContentSectionSummary:
        """Condense a single MigrationSection into ContentSectionSummary."""
        elements: list[ContentElementSummary] = []
        type_counts: dict[str, int] = {}

        for i, elem in enumerate(sec.elements):
            et = elem.element_type
            type_counts[et] = type_counts.get(et, 0) + 1

            has_cell_icons = any(getattr(c, "icon_path", None) is not None for c in elem.cells)

            img_basename: Optional[str] = None
            if elem.image_path:
                img_basename = Path(elem.image_path).name

            elements.append(
                ContentElementSummary(
                    index=i,
                    element_type=et,
                    text_preview=(elem.text or "")[:120],
                    level=elem.level,
                    num_rows=elem.num_rows,
                    num_cols=elem.num_cols,
                    has_icons=len(elem.icons) > 0,
                    icon_count=len(elem.icons),
                    has_icon_in_cells=has_cell_icons,
                    image_path_basename=img_basename,
                    list_items_count=len(elem.items) if elem.items else None,
                    page=elem.page,
                )
            )

        blocks = self._group_into_blocks(sec)

        return ContentSectionSummary(
            section_number=sec.section_number,
            title=sec.title,
            page_start=sec.page_start,
            page_end=sec.page_end,
            total_elements=len(sec.elements),
            element_type_counts=type_counts,
            elements=elements,
            blocks=blocks,
        )
