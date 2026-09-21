"""Schemas for Template Management, Extraction, and Migration.

This module defines Pydantic models for templates, including blue-font instructions,
icons, section-wise elements, global rules, and extraction responses.
"""

from __future__ import annotations

from typing import Optional, Any
from pydantic import BaseModel, ConfigDict, Field

from app.schemas.migration import MigrationTableCell


class TemplateIconRef(BaseModel):
    """An icon extracted from the template."""
    icon_id: str
    image_path: str
    semantic_meaning: str = "unknown"
    section_context: Optional[str] = None
    associated_text: Optional[str] = None

    def to_clean_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "icon_id": self.icon_id,
            "image_path": self.image_path,
            "semantic_meaning": self.semantic_meaning,
        }
        if self.section_context is not None:
            d["section_context"] = self.section_context
        if self.associated_text is not None:
            d["associated_text"] = self.associated_text
        return d


class TemplateInstruction(BaseModel):
    """A blue-colored instruction paragraph found in the template.

    These are the instructions written in blue font that guide
    SOP authors on what content to place in each section.
    """
    text: str
    font_color_hex: Optional[str] = None
    paragraph_index: int = 0
    section_context: Optional[str] = None
    is_global: bool = False
    icons: list[TemplateIconRef] = Field(default_factory=list)

    def to_clean_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "text": self.text,
            "paragraph_index": self.paragraph_index,
            "is_global": self.is_global,
        }
        if self.font_color_hex is not None:
            d["font_color_hex"] = self.font_color_hex
        if self.section_context is not None:
            d["section_context"] = self.section_context
        if self.icons:
            d["icons"] = [i.to_clean_dict() for i in self.icons]
        return d


class TemplateElement(BaseModel):
    """A single linear element in the template extraction output.

    Reuses the same element_type vocabulary as MigrationElement but adds
    instruction-specific fields for template blue-font text.
    """
    element_type: str  # "heading", "paragraph", "list", "table", "image", "icon", "instruction"
    page: int = 0
    section_name: Optional[str] = None
    level: Optional[int] = None
    text: Optional[str] = None
    icons: list[TemplateIconRef] = Field(default_factory=list)
    items: list[str] = Field(default_factory=list)
    title: Optional[str] = None
    num_rows: Optional[int] = None
    num_cols: Optional[int] = None
    cells: list[MigrationTableCell] = Field(default_factory=list)
    image_path: Optional[str] = None
    is_instruction: bool = False
    instruction_text: Optional[str] = None
    font_color_hex: Optional[str] = None

    def to_clean_dict(self, section_name: Optional[str] = None) -> dict[str, Any]:
        effective_section = section_name or self.section_name
        d: dict[str, Any] = {
            "element_type": self.element_type,
            "page": self.page,
            "is_instruction": self.is_instruction,
        }
        if effective_section is not None:
            d["section_name"] = effective_section
        if self.level is not None:
            d["level"] = self.level
        if self.text is not None:
            d["text"] = self.text
        if self.instruction_text is not None:
            d["instruction_text"] = self.instruction_text
        if self.font_color_hex is not None:
            d["font_color_hex"] = self.font_color_hex
        if self.icons:
            d["icons"] = [icon.to_clean_dict() for icon in self.icons]
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


class TemplateSection(BaseModel):
    """A section of the template document, containing elements in reading order."""
    section_number: Optional[str] = None
    title: str
    page_start: int = 1
    page_end: int = 1
    elements: list[TemplateElement] = Field(default_factory=list)
    instructions: list[TemplateInstruction] = Field(default_factory=list)

    def to_clean_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "title": self.title,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "elements": [e.to_clean_dict(section_name=self.title) for e in self.elements],
            "instructions": [i.to_clean_dict() for i in self.instructions],
        }
        if self.section_number is not None:
            d["section_number"] = self.section_number
        return d


class TemplateGlobalRules(BaseModel):
    """Global rules extracted from the template.

    Contains ONLY blue-font instruction paragraphs that appear before
    the first section heading. These are document-wide rules applicable
    to the entire SOP being migrated.
    """
    instructions: list[TemplateInstruction] = Field(default_factory=list)

    def to_clean_dict(self) -> dict[str, Any]:
        return {
            "instructions": [i.to_clean_dict() for i in self.instructions],
        }


class TemplateMetadata(BaseModel):
    """Metadata extracted from the template document properties."""
    template_id: str = ""
    template_name: str = ""
    author: str = ""
    creation_date: str = ""
    modification_date: str = ""
    file_type: str = "docx"
    file_size_bytes: int = 0


class TemplateExtractionOutput(BaseModel):
    """Top-level template extraction JSON envelope."""
    version: str = "1.0"
    template_id: str
    template_name: str
    metadata: TemplateMetadata = Field(default_factory=TemplateMetadata)
    global_rules: TemplateGlobalRules = Field(default_factory=TemplateGlobalRules)
    sections: list[TemplateSection] = Field(default_factory=list)
    total_instructions: int = 0
    total_icons: int = 0

    def to_clean_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "template_id": self.template_id,
            "template_name": self.template_name,
            "metadata": self.metadata.model_dump(exclude_none=True),
            "global_rules": self.global_rules.to_clean_dict(),
            "sections": [s.to_clean_dict() for s in self.sections],
            "total_instructions": self.total_instructions,
            "total_icons": self.total_icons,
        }


# --- API Request / Response Models ---

class TemplateUploadResponse(BaseModel):
    template_id: str
    template_name: str
    template_version: int
    file_type: str
    size_bytes: int
    already_uploaded: bool
    message: str


class TemplateExtractResponse(BaseModel):
    template_id: str
    status: str
    total_sections: int
    total_elements: int
    total_instructions: int
    total_icons: int
    global_rules_count: int
    message: str


class TemplateListItem(BaseModel):
    id: int
    template_uid: str
    template_name: str
    template_version: int
    total_sections: int
    total_instructions: int
    total_icons: int
    status: str
    created_at: str
