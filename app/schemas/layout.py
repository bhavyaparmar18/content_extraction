"""PDF layout analysis schemas.

These types capture the spatial layout of a PDF page — columns, regions,
reading order — produced by the ``PDFLayoutAnalyzer``.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.document import BoundingBox, ExtractedElement


class ContentRegion(BaseModel):
    """A detected spatial region on a PDF page."""
    region_id: str
    region_type: str  # "column" | "header" | "footer" | "sidebar" | "figure" | "table"
    bbox: BoundingBox
    blocks: list[ExtractedElement] = Field(default_factory=list)


class Column(BaseModel):
    """A detected text column within a page."""
    column_index: int = 0
    bbox: BoundingBox
    block_count: int = 0


class PageLayout(BaseModel):
    """Analyzed layout of a single PDF page.

    Produced by ``PDFLayoutAnalyzer.analyze_page()`` and consumed by the
    reading-order reconstruction step before AST building.
    """
    page_number: int
    width: float
    height: float
    columns: int = 1                # detected column count
    column_details: list[Column] = Field(default_factory=list)
    regions: list[ContentRegion] = Field(default_factory=list)
    reading_order: list[str] = Field(default_factory=list)  # ordered region_ids
    headers: list[ExtractedElement] = Field(default_factory=list)
    footers: list[ExtractedElement] = Field(default_factory=list)
