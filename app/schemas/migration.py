"""Schemas for Clean .docx-Ready Document Migration Output.

This module defines the simplified section-wise reading-order JSON structure
designed specifically for migrating extracted SOP content into Microsoft Word
(.docx) or other document authoring systems.
"""

from __future__ import annotations

from typing import Optional, Any
from pydantic import BaseModel, ConfigDict, Field


class MigrationMetadata(BaseModel):
    """Clean metadata summary for a document."""
    model_config = ConfigDict(populate_by_name=True)

    document_id: str = Field(default="", alias="document_Uid")
    document_number: Optional[str] = None
    document_name: Optional[str] = None
    document_title: Optional[str] = None
    document_version: Optional[str] = None
    document_type: Optional[str] = None   # Type/Subtype from preamble table
    title: Optional[str] = None  # deprecated; prefer document_title
    file_type: str = ""
    language: str = "en"
    page_count: int = 0
    gpdat_version: int = 0
    duplicate_upload_count: int = 0  # deprecated alias of gpdat_version


class MigrationIconRef(BaseModel):
    """Reference to an inline or attached icon in a paragraph or element."""
    icon_id: str
    path: str
    semantic_meaning: Optional[str] = None


class MigrationHighlightSpan(BaseModel):
    """A highlighted range within an element's text."""
    text: str = ""
    color_name: str = ""
    color_hex: str = ""
    start_offset: int = 0
    end_offset: int = 0

    def to_clean_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "text": self.text,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
        }
        if self.color_name:
            data["color_name"] = self.color_name
        if self.color_hex:
            data["color_hex"] = self.color_hex
        return data


class MigrationContentBlock(BaseModel):
    """One ordered block inside a callout: a paragraph or a list."""
    type: str
    text: Optional[str] = None
    items: list[str] = Field(default_factory=list)
    bold: bool = False
    background_color: Optional[str] = None
    highlights: list[MigrationHighlightSpan] = Field(default_factory=list)

    def to_clean_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {"type": self.type}
        if self.text:
            data["text"] = self.text
        if self.items:
            data["items"] = self.items
        if self.bold:
            data["bold"] = True
        if self.background_color:
            data["background_color"] = self.background_color
        if self.highlights:
            data["highlights"] = [span.to_clean_dict() for span in self.highlights]
        return data


class MigrationTableCell(BaseModel):
    """A genuine origin cell in a table, ready for .docx table construction."""
    row_index: int
    col_index: int
    row_span: int = 1
    col_span: int = 1
    text: str = ""
    icon_path: Optional[str] = None
    image_path: Optional[str] = None
    is_header: bool = False
    background_color: Optional[str] = None  # Hex color e.g. "#FFFF00" for highlighted cells

    def to_clean_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "row_index": self.row_index,
            "col_index": self.col_index,
            "row_span": self.row_span,
            "col_span": self.col_span,
            "text": self.text,
            "is_header": self.is_header,
        }
        if self.icon_path is not None:
            d["icon_path"] = self.icon_path
        if self.image_path is not None:
            d["image_path"] = self.image_path
        if self.background_color is not None:
            d["background_color"] = self.background_color
        return d


class MigrationElement(BaseModel):
    """A single linear document element in reading order.

    Supported element_type values:
    - 'heading': uses level, text
    - 'paragraph': uses text, icons
    - 'list': uses items (list of strings), icons
    - 'callout': uses content (ordered paragraph/list blocks), icons, background_color
    - 'table': uses title, num_rows, num_cols, cells
    - 'image': uses title/caption, image_path
    - 'float': a picture with text wrapped beside it. Uses image_path,
      image_align, wrap, image_width_in, image_height_in, and content

    ``section_name`` is stamped by the parent ``MigrationSection`` during
    serialisation so every element carries its section context for QA retrieval.
    """
    element_type: str
    page: int = 0
    section_name: Optional[str] = None   # set by parent MigrationSection on export
    level: Optional[int] = None
    text: Optional[str] = None
    icons: list[MigrationIconRef] = Field(default_factory=list)
    items: list[str] = Field(default_factory=list)
    background_color: Optional[str] = None
    highlights: list[MigrationHighlightSpan] = Field(default_factory=list)
    content: list[MigrationContentBlock] = Field(default_factory=list)
    title: Optional[str] = None
    num_rows: Optional[int] = None
    num_cols: Optional[int] = None
    cells: list[MigrationTableCell] = Field(default_factory=list)
    image_path: Optional[str] = None
    image_align: Optional[str] = None       # left | right | center, for a float
    wrap: Optional[str] = None              # square | tight | through
    image_width_in: Optional[float] = None
    image_height_in: Optional[float] = None

    def to_clean_dict(self, section_name: Optional[str] = None) -> dict[str, Any]:
        """Serialise to a plain dict.

        Args:
            section_name: Override the element's ``section_name`` field.  The
                parent ``MigrationSection.to_clean_dict`` passes the section
                title here so every element always carries its section context.
        """
        effective_section = section_name or self.section_name
        d: dict[str, Any] = {
            "element_type": self.element_type,
            "page": self.page,
        }
        if effective_section is not None:
            d["section_name"] = effective_section
        if self.level is not None:
            d["level"] = self.level
        if self.text is not None:
            d["text"] = self.text
        if self.background_color is not None:
            d["background_color"] = self.background_color
        if self.highlights:
            d["highlights"] = [span.to_clean_dict() for span in self.highlights]
        if self.icons:
            d["icons"] = [icon.model_dump(exclude_none=True) for icon in self.icons]
        if self.items:
            d["items"] = self.items
        if self.content:
            d["content"] = [block.to_clean_dict() for block in self.content]
        if self.title is not None:
            d["title"] = self.title
        if self.num_rows is not None:
            d["num_rows"] = self.num_rows
        if self.num_cols is not None:
            d["num_cols"] = self.num_cols
        if self.cells:
            d["cells"] = [c.to_clean_dict() for c in self.cells]
        if self.image_path is not None:
            d["image_path"] = self.image_path
        if self.image_align is not None:
            d["image_align"] = self.image_align
        if self.wrap is not None:
            d["wrap"] = self.wrap
        if self.image_width_in:
            d["image_width_in"] = round(self.image_width_in, 2)
        if self.image_height_in:
            d["image_height_in"] = round(self.image_height_in, 2)
        return d


class MigrationSection(BaseModel):
    """A chapter or section of the document, containing reading-order elements."""
    section_number: Optional[str] = None
    title: str
    page_start: int = 1
    page_end: int = 1
    elements: list[MigrationElement] = Field(default_factory=list)

    def to_clean_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "title": self.title,
            "page_start": self.page_start,
            "page_end": self.page_end,
            # Stamp section_name on every element so each carries its section
            # context when used standalone for QA retrieval.
            "elements": [e.to_clean_dict(section_name=self.title) for e in self.elements],
        }
        if self.section_number is not None:
            d["section_number"] = self.section_number
        return d


class DocxMigrationOutput(BaseModel):
    """Top-level Clean .docx Document Migration Output envelope."""
    model_config = ConfigDict(populate_by_name=True)

    version: str = "3.1"
    document_id: str = Field(alias="document_Uid")
    metadata: MigrationMetadata = Field(default_factory=MigrationMetadata)
    sections: list[MigrationSection] = Field(default_factory=list)

    def to_clean_dict(self) -> dict[str, Any]:
        meta = self.metadata.model_dump(exclude_none=True, by_alias=True)
        meta.pop("title", None)
        meta.pop("duplicate_upload_count", None)
        if not meta.get("file_type"):
            meta.pop("file_type", None)
        if not meta.get("gpdat_version"):
            meta.pop("gpdat_version", None)
        return {
            "version": self.version,
            "document_Uid": self.document_id,
            "metadata": meta,
            "sections": [s.to_clean_dict() for s in self.sections],
        }
