"""Pydantic schemas for document data contracts.

Every layer communicates through these typed models — no raw dicts.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ── Enums ──────────────────────────────────────────────────────────────

class ElementType(str, Enum):
    """Types of structural elements found inside a document."""
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST_ITEM = "list_item"
    LIST_ORDERED = "list_ordered"
    LIST_UNORDERED = "list_unordered"
    NUMBERED_STEP = "numbered_step"
    TABLE = "table"
    IMAGE = "image"
    ICON = "icon"
    CAPTION = "caption"
    HEADER = "header"
    FOOTER = "footer"
    HIGHLIGHT = "highlight"
    REFERENCE = "reference"
    UNKNOWN = "unknown"


class ChunkType(str, Enum):
    """High-level category assigned to a chunk after classification."""
    PROCEDURE = "procedure"
    SECTION = "section"
    TABLE = "table"
    REFERENCE = "reference"
    APPENDIX = "appendix"
    METADATA = "metadata"


# ── Coordinate / Position ─────────────────────────────────────────────

class BoundingBox(BaseModel):
    """Page-space bounding box for any visual element."""
    x0: float
    y0: float
    x1: float
    y1: float
    page: int


# ── Extracted Elements ─────────────────────────────────────────────────

class ExtractedElement(BaseModel):
    """Base schema for any element pulled out of a document."""
    element_type: ElementType
    content: str = ""
    page: int = 0
    sequence: int = 0
    bbox: Optional[BoundingBox] = None
    confidence: float = 1.0
    outline_level: Optional[int] = None       # DOCX outline level (0-8)
    highlight_color: Optional[str] = None     # Named highlight color if detected


class ExtractedHeading(ExtractedElement):
    """A heading with its detected hierarchical level."""
    element_type: ElementType = ElementType.HEADING
    level: int = 1


class ExtractedTableCell(BaseModel):
    """A cell within an ExtractedTable."""
    content_text: str = ""
    row_span: int = 1
    col_span: int = 1
    is_merge_origin: bool = True
    merge_origin_ref: Optional[str] = None  # node_id if we have it, or generic ref
    bbox: Optional[BoundingBox] = None
    media_nodes: list[ExtractedElement] = Field(default_factory=list)


class ExtractedTable(ExtractedElement):
    """A table represented as column headers + row data."""
    element_type: ElementType = ElementType.TABLE
    caption: str = ""
    grid_cols: int = 0
    headers: list[ExtractedTableCell] = Field(default_factory=list)
    rows: list[list[ExtractedTableCell]] = Field(default_factory=list)


class ExtractedImage(ExtractedElement):
    """An image with its file path and optional caption."""
    element_type: ElementType = ElementType.IMAGE
    image_path: str = ""
    caption: str = ""
    width: int = 0
    height: int = 0


class ExtractedIcon(ExtractedElement):
    """An icon with its semantic meaning resolved from the icon dictionary."""
    element_type: ElementType = ElementType.ICON
    icon_id: str = ""
    semantic_meaning: str = ""
    image_path: str = ""
    associated_element_seq: Optional[int] = None


# ── Raw Document ───────────────────────────────────────────────────────

class PageContent(BaseModel):
    """All elements extracted from a single page."""
    page_number: int
    elements: list[ExtractedElement] = Field(default_factory=list)
    width: float = 0.0
    height: float = 0.0


class DocumentMetadata(BaseModel):
    """Metadata pulled from the document's properties and first-page SOP table."""
    title: str = ""
    author: str = ""
    subject: str = ""
    creator: str = ""
    creation_date: str = ""
    modification_date: str = ""
    page_count: int = 0
    file_type: str = ""
    file_size_bytes: int = 0
    document_name: str = ""
    document_number: str = ""
    document_version: str = ""
    duplicate_upload_count: int = 0


class RawDocument(BaseModel):
    """Complete parser output — the input to the extraction stage."""
    source: str
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    pages: list[PageContent] = Field(default_factory=list)


# ── Structured Tree ────────────────────────────────────────────────────

class SectionNode(BaseModel):
    """A hierarchical node representing a document section."""
    node_id: str
    heading: Optional[ExtractedHeading] = None
    level: int = 0
    elements: list[ExtractedElement] = Field(default_factory=list)
    children: list["SectionNode"] = Field(default_factory=list)


class StructuredDocument(BaseModel):
    """The document represented as a nested tree of sections."""
    source: str
    metadata: DocumentMetadata
    root: SectionNode


# ── Chunks ─────────────────────────────────────────────────────────────

class ChunkMetadata(BaseModel):
    """Rich metadata attached to every chunk."""
    chunk_id: str = ""
    parent_id: Optional[str] = None
    section: str = ""
    heading: str = ""
    page: int = 0
    sequence: int = 0
    chunk_type: ChunkType = ChunkType.SECTION
    contains_table: bool = False
    contains_image: bool = False
    contains_icon: bool = False
    related_chunks: list[str] = Field(default_factory=list)
    source_coordinates: list[BoundingBox] = Field(default_factory=list)


class Chunk(BaseModel):
    """A single output chunk ready for JSON export."""
    chunk_id: str
    chunk_type: ChunkType
    heading: str = ""
    content: str = ""
    tables: list[ExtractedTable] = Field(default_factory=list)
    images: list[ExtractedImage] = Field(default_factory=list)
    icons: list[ExtractedIcon] = Field(default_factory=list)
    metadata: ChunkMetadata = Field(default_factory=ChunkMetadata)


# ── Final Output ───────────────────────────────────────────────────────

class DocumentOutput(BaseModel):
    """Top-level schema returned to the client / written to JSON."""
    document_id: str
    title: str = ""
    source_file: str = ""
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    chunks: list[Chunk] = Field(default_factory=list)
    validation_passed: bool = True
    validation_warnings: list[str] = Field(default_factory=list)
