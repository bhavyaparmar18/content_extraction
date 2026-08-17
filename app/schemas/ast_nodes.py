"""AST node types for the document extraction system.

Every structural element in a document is represented as a typed node in an
Abstract Syntax Tree (AST). This tree preserves the full hierarchy, nesting,
and relationships of the original document — making it suitable for lossless
migration into new document templates.

All nodes inherit from ``ASTNode`` which provides a unique ID, sequence number,
source location, and confidence score.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Annotated, Any, Optional, Union

from pydantic import BaseModel, Discriminator, Field, Tag

from app.schemas.document import BoundingBox, DocumentMetadata


# ── Source Location ────────────────────────────────────────────────────

class SourceLocation(BaseModel):
    """Tracks the exact origin of an extracted element."""
    page: int = 0
    bbox: Optional[BoundingBox] = None       # PDF spatial coordinates
    paragraph_index: Optional[int] = None    # DOCX paragraph ordinal
    xml_path: Optional[str] = None           # DOCX XML path for traceability


# ── Base Node ──────────────────────────────────────────────────────────

class ASTNode(BaseModel):
    """Base class for all AST nodes.

    Every node carries:
    - ``node_id``: a UUID for cross-referencing within the tree
    - ``node_type``: a discriminator string for polymorphic deserialization
    - ``sequence``: reading-order position relative to siblings
    - ``source_location``: where this element was extracted from
    - ``confidence``: how confident the extractor is in this classification (0–1)
    - ``metadata``: extensible dict for extractor-specific data
    """
    node_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    node_type: str
    sequence: int = 0
    source_location: Optional[SourceLocation] = None
    confidence: float = 1.0
    metadata: dict[str, Any] = Field(default_factory=dict)


# ── Document Node (root) ──────────────────────────────────────────────

class DocumentNode(ASTNode):
    """Root node of the AST — represents the entire document."""
    node_type: str = "document"
    doc_metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    children: list["ChildNode"] = Field(default_factory=list)


# ── Structural Nodes ──────────────────────────────────────────────────

class SectionNode(ASTNode):
    """A document section defined by a heading."""
    node_type: str = "section"
    heading: Optional["HeadingNode"] = None
    level: int = 0
    children: list["ChildNode"] = Field(default_factory=list)


class HeadingNode(ASTNode):
    """A heading element with its hierarchical level and optional numbering."""
    node_type: str = "heading"
    text: str = ""
    level: int = 1
    numbering: Optional[str] = None  # e.g., "1.2.3"


# ── Text Content Nodes ────────────────────────────────────────────────

class HighlightSpan(BaseModel):
    """A highlighted range within a paragraph's text.

    Stores the exact character offsets, the extracted text, and the
    highlight color in both named and hex forms.
    """
    text: str = ""
    highlight_color: str = ""       # Named color: "yellow", "green", "cyan", etc.
    color_hex: str = ""             # Hex value: "#FFFF00", "#00FF00", etc.
    start_offset: int = 0           # Character offset within parent paragraph text
    end_offset: int = 0             # Character offset (exclusive) within parent text


class ParagraphNode(ASTNode):
    """A paragraph of text, optionally containing highlighted spans."""
    node_type: str = "paragraph"
    text: str = ""
    highlights: list[HighlightSpan] = Field(default_factory=list)


class HighlightNode(ASTNode):
    """Standalone highlighted text block (when an entire block is highlighted)."""
    node_type: str = "highlight"
    text: str = ""
    highlight_color: str = ""
    color_hex: str = ""


# ── List Nodes ─────────────────────────────────────────────────────────

class ListType(str, Enum):
    ORDERED = "ordered"
    UNORDERED = "unordered"


class ListNode(ASTNode):
    """A list container grouping consecutive list items."""
    node_type: str = "list"
    list_type: str = ListType.UNORDERED  # "ordered" | "unordered"
    nesting_depth: int = 0
    items: list["ListItemNode"] = Field(default_factory=list)


class ListItemNode(ASTNode):
    """A single item within a list.

    May contain nested child nodes (sub-lists, images, paragraphs).
    """
    node_type: str = "list_item"
    text: str = ""
    index: Optional[int] = None  # 1-based for ordered lists
    children: list["ChildNode"] = Field(default_factory=list)



# ── Table Nodes ────────────────────────────────────────────────────────

class TableNode(ASTNode):
    """A table with row/column structure, supporting merged cells."""
    node_type: str = "table"
    row_count: int = 0
    col_count: int = 0
    grid_cols: int = 0          # Total grid columns (before merges)
    rows: list["TableRowNode"] = Field(default_factory=list)
    caption: Optional[str] = None
    has_header_row: bool = False


class TableRowNode(ASTNode):
    """A single row within a table."""
    node_type: str = "table_row"
    row_index: int = 0
    is_header: bool = False
    cells: list["TableCellNode"] = Field(default_factory=list)


class TableCellNode(ASTNode):
    """A single cell within a table row.

    Supports merged cells via ``row_span``/``col_span``. Continuation cells
    (non-origin cells in a merge group) have ``is_merge_origin=False`` and
    ``merge_origin_ref`` pointing to the origin cell's ``node_id``.
    """
    node_type: str = "table_cell"
    row_index: int = 0
    col_index: int = 0
    row_span: int = 1
    col_span: int = 1
    is_merge_origin: bool = True
    merge_origin_ref: Optional[str] = None  # node_id of the origin cell
    content: list["ChildNode"] = Field(default_factory=list)


# ── Media Nodes ────────────────────────────────────────────────────────

class ImageNode(ASTNode):
    """An extracted image with optional OCR text and caption."""
    node_type: str = "image"
    asset_path: str = ""
    alt_text: str = ""
    width: int = 0
    height: int = 0
    caption: Optional[str] = None
    image_hash: str = ""
    ocr_text: Optional[str] = None          # Text extracted via pytesseract
    ocr_confidence: Optional[float] = None  # Tesseract confidence score (0.0–1.0)


class IconCategory(str, Enum):
    """Semantic categories for classified icons."""
    SAFETY = "safety"
    STATUS = "status"
    ACTION = "action"
    INFORMATIONAL = "informational"
    REGULATORY = "regulatory"
    NAVIGATION = "navigation"
    BRANDING = "branding"
    UNKNOWN = "unknown"


class IconNode(ASTNode):
    """An icon/symbol with classification metadata."""
    node_type: str = "icon"
    asset_path: str = ""
    icon_type: str = "unknown"          # "raster" | "vector" | "font" | "emoji" | "symbol"
    semantic_meaning: str = ""          # "warning" | "ppe_required" | "prohibited" | etc.
    classification_method: str = ""     # "perceptual_hash" | "size_heuristic" | "manual"
    icon_category: str = IconCategory.UNKNOWN


class CaptionNode(ASTNode):
    """A caption associated with an image or table."""
    node_type: str = "caption"
    text: str = ""
    caption_label: Optional[str] = None       # "Figure 1", "Table 2"
    referenced_node_id: Optional[str] = None  # node_id of the parent image/table


# ── Discriminated Union for polymorphic children ──────────────────────


def _get_node_type_discriminator(v: Any) -> str:
    """Extract the node_type discriminator from a node dict or instance."""
    if isinstance(v, dict):
        return v.get("node_type", "paragraph")
    return getattr(v, "node_type", "paragraph")


# ChildNode is the discriminated union used for all heterogeneous
# ``children`` / ``content`` / ``items`` lists.  The discriminator
# ensures Pydantic serializes every subclass's full field set.
ChildNode = Annotated[
    Union[
        Annotated[DocumentNode, Tag("document")],
        Annotated[SectionNode, Tag("section")],
        Annotated[HeadingNode, Tag("heading")],
        Annotated[ParagraphNode, Tag("paragraph")],
        Annotated[HighlightNode, Tag("highlight")],
        Annotated[ListNode, Tag("list")],
        Annotated[ListItemNode, Tag("list_item")],
        Annotated[TableNode, Tag("table")],
        Annotated[TableRowNode, Tag("table_row")],
        Annotated[TableCellNode, Tag("table_cell")],
        Annotated[ImageNode, Tag("image")],
        Annotated[IconNode, Tag("icon")],
        Annotated[CaptionNode, Tag("caption")],
    ],
    Discriminator(_get_node_type_discriminator),
]

# Also export the union type under the old name for backward compat
ASTNodeUnion = ChildNode


# ── Model Rebuilds for Forward References ──────────────────────────────

# Pydantic v2 requires explicit model_rebuild() to resolve forward references
# in self-referential models (ChildNode depends on all node types being defined).
DocumentNode.model_rebuild()
SectionNode.model_rebuild()
ListNode.model_rebuild()
ListItemNode.model_rebuild()
TableNode.model_rebuild()
TableRowNode.model_rebuild()
TableCellNode.model_rebuild()
