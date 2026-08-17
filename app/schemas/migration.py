"""Schemas for Clean .docx-Ready Document Migration Output.

This module defines the simplified section-wise reading-order JSON structure
designed specifically for migrating extracted SOP content into Microsoft Word
(.docx) or other document authoring systems.
"""

from __future__ import annotations

from typing import Optional, Any
from pydantic import BaseModel, Field


class MigrationMetadata(BaseModel):
    """Clean metadata summary for a document."""
    document_id: str = ""
    document_number: Optional[str] = None
    document_name: Optional[str] = None
    document_version: Optional[str] = None
    title: Optional[str] = None
    language: str = "en"
    page_count: int = 0
    duplicate_upload_count: int = 0


class MigrationIconRef(BaseModel):
    """Reference to an inline or attached icon in a paragraph or element."""
    icon_id: str
    path: str
    semantic_meaning: Optional[str] = None


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
        return d


class MigrationElement(BaseModel):
    """A single linear document element in reading order.
    
    Supported element_type values:
    - 'heading': uses level, text
    - 'paragraph': uses text, icons
    - 'list': uses items (list of strings), icons
    - 'table': uses title, num_rows, num_cols, cells
    - 'image': uses title/caption, image_path
    """
    element_type: str
    page: int = 0
    level: Optional[int] = None
    text: Optional[str] = None
    icons: list[MigrationIconRef] = Field(default_factory=list)
    items: list[str] = Field(default_factory=list)
    title: Optional[str] = None
    num_rows: Optional[int] = None
    num_cols: Optional[int] = None
    cells: list[MigrationTableCell] = Field(default_factory=list)
    image_path: Optional[str] = None

    def to_clean_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "element_type": self.element_type,
            "page": self.page,
        }
        if self.level is not None:
            d["level"] = self.level
        if self.text is not None:
            d["text"] = self.text
        if self.icons:
            d["icons"] = [icon.model_dump(exclude_none=True) for icon in self.icons]
        if self.items:
            d["items"] = self.items
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
            "elements": [e.to_clean_dict() for e in self.elements],
        }
        if self.section_number is not None:
            d["section_number"] = self.section_number
        return d


class DocxMigrationOutput(BaseModel):
    """Top-level Clean .docx Document Migration Output envelope."""
    version: str = "3.1"
    document_id: str
    metadata: MigrationMetadata = Field(default_factory=MigrationMetadata)
    sections: list[MigrationSection] = Field(default_factory=list)

    def to_clean_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "document_id": self.document_id,
            "metadata": self.metadata.model_dump(exclude_none=True),
            "sections": [s.to_clean_dict() for s in self.sections],
        }
