"""Mode A: Programmatic content summarizer for fast truncation-based summaries."""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from loguru import logger

from app.schemas.migration import DocxMigrationOutput, MigrationSection
from app.services.migration.schemas import (
    ContentSummary,
    ContentSectionSummary,
    ContentElementSummary,
)


class ContentSummarizer:
    """Mode A — Fast programmatic truncation-based content summarizer (zero LLM calls)."""

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

    def _summarize_section(self, sec: MigrationSection) -> ContentSectionSummary:
        """Condense a single MigrationSection into ContentSectionSummary."""
        elements: list[ContentElementSummary] = []
        type_counts: dict[str, int] = {}

        for i, elem in enumerate(sec.elements):
            et = elem.element_type
            type_counts[et] = type_counts.get(et, 0) + 1

            # Determine if any cell has icon_path
            has_cell_icons = any(getattr(c, "icon_path", None) is not None for c in elem.cells)

            # Basename for image
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

        return ContentSectionSummary(
            section_number=sec.section_number,
            title=sec.title,
            page_start=sec.page_start,
            page_end=sec.page_end,
            total_elements=len(sec.elements),
            element_type_counts=type_counts,
            elements=elements,
        )
