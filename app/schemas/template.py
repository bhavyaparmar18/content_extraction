"""Schemas for Template Management and Extraction — v2.0 output contract.

The v1.0 output described *what the template looks like*. v2.0 describes *what a
migrated SOP is required to obey*, which is what the migration engine needs:

- ``icon_library``   — every physical icon once, keyed by content hash. Elements
  and instructions reference entries by ``icon_key`` instead of embedding copies
  with per-occurrence UUIDs.
- ``callout_styles`` — the shaded infographic boxes with their real colours,
  replacing hardcoded style tables on the migration side.
- ``global_rules``   — instructions carrying ``directive_type`` and, where the
  rule is programmatically enforceable, a ``machine_rule``.
- ``sections``       — split into ``skeleton_elements`` (black content, copied
  verbatim) and ``authoring_instructions`` (blue content, followed then deleted).

``to_clean_dict`` on each model drops empty/None fields so the on-disk JSON stays
readable.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field


# ── Icons ──────────────────────────────────────────────────────────────

class TemplateIconRef(BaseModel):
    """A reference from an element or instruction to an ``icon_library`` entry."""
    icon_key: str
    section_context: Optional[str] = None
    associated_text: Optional[str] = None

    def to_clean_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"icon_key": self.icon_key}
        if self.section_context is not None:
            d["section_context"] = self.section_context
        if self.associated_text is not None:
            d["associated_text"] = self.associated_text
        return d


class TemplateIconEntry(BaseModel):
    """One physical icon in the template, deduplicated by content hash.

    ``semantic_meaning`` and ``usage_rule`` stay unpopulated until the icon
    labelling phase; the fields exist so that phase is a drop-in.
    """
    icon_key: str
    content_hash: Optional[str] = None
    asset_path: str = ""
    semantic_meaning: str = "unknown"
    display_name: Optional[str] = None
    usage_rule: Optional[str] = None
    source_instruction: Optional[str] = None
    allowed_sections: list[str] = Field(default_factory=list)
    occurrences: int = 0

    def to_clean_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "icon_key": self.icon_key,
            "asset_path": self.asset_path,
            "semantic_meaning": self.semantic_meaning,
            "occurrences": self.occurrences,
        }
        if self.content_hash is not None:
            d["content_hash"] = self.content_hash
        if self.display_name is not None:
            d["display_name"] = self.display_name
        if self.usage_rule is not None:
            d["usage_rule"] = self.usage_rule
        if self.source_instruction is not None:
            d["source_instruction"] = self.source_instruction
        if self.allowed_sections:
            d["allowed_sections"] = self.allowed_sections
        return d


# ── Callouts ───────────────────────────────────────────────────────────

class TemplateCalloutStyle(BaseModel):
    """A shaded infographic box, with colours read from the template itself."""
    callout_type: str
    display_name: Optional[str] = None
    background_color_hex: str = ""
    left_border_color_hex: Optional[str] = None
    border_width_pt: float = 3.5
    font_color_hex: Optional[str] = None
    icon_key: Optional[str] = None
    trigger_instruction: Optional[str] = None
    placement_rule: str = "as_needed"
    template_source: dict[str, Any] = Field(default_factory=dict)

    def to_clean_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "callout_type": self.callout_type,
            "background_color_hex": self.background_color_hex,
            "border_width_pt": self.border_width_pt,
            "placement_rule": self.placement_rule,
        }
        if self.display_name is not None:
            d["display_name"] = self.display_name
        if self.left_border_color_hex is not None:
            d["left_border_color_hex"] = self.left_border_color_hex
        if self.font_color_hex is not None:
            d["font_color_hex"] = self.font_color_hex
        if self.icon_key is not None:
            d["icon_key"] = self.icon_key
        if self.trigger_instruction is not None:
            d["trigger_instruction"] = self.trigger_instruction
        if self.template_source:
            d["template_source"] = self.template_source
        return d


# ── Instructions ───────────────────────────────────────────────────────

class DirectiveType(str, Enum):
    """What kind of obligation an instruction places on the migrated SOP."""
    PROHIBITION = "prohibition"
    REQUIREMENT = "requirement"
    GUIDANCE = "guidance"
    PLACEHOLDER_HINT = "placeholder_hint"
    ICON_USAGE = "icon_usage"
    FORMATTING = "formatting"


class InstructionScope(str, Enum):
    GLOBAL = "global"
    SECTION = "section"


class TemplateMachineRule(BaseModel):
    """A constraint the validator can enforce without consulting the LLM."""
    rule: str
    value: Any = None
    enforce: str = "hard"   # "hard" | "soft"

    def to_clean_dict(self) -> dict[str, Any]:
        return {"rule": self.rule, "value": self.value, "enforce": self.enforce}


class TemplateInstruction(BaseModel):
    """A blue-font instruction paragraph guiding SOP authors.

    These are followed during migration and then deleted from the output.
    """
    instruction_id: str = ""
    text: str
    scope: str = InstructionScope.SECTION.value
    directive_type: str = DirectiveType.GUIDANCE.value
    font_color_hex: Optional[str] = None
    color_detection_method: Optional[str] = None
    paragraph_index: int = 0
    section_context: Optional[str] = None
    is_global: bool = False
    machine_rule: Optional[TemplateMachineRule] = None
    icons: list[TemplateIconRef] = Field(default_factory=list)

    def to_clean_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "instruction_id": self.instruction_id,
            "text": self.text,
            "scope": self.scope,
            "directive_type": self.directive_type,
            "paragraph_index": self.paragraph_index,
            "is_global": self.is_global,
        }
        if self.font_color_hex is not None:
            d["font_color_hex"] = self.font_color_hex
        if self.color_detection_method is not None:
            d["color_detection_method"] = self.color_detection_method
        if self.section_context is not None:
            d["section_context"] = self.section_context
        if self.machine_rule is not None:
            d["machine_rule"] = self.machine_rule.to_clean_dict()
        if self.icons:
            d["icons"] = [i.to_clean_dict() for i in self.icons]
        return d


# ── Elements ───────────────────────────────────────────────────────────

class TemplateTableCell(BaseModel):
    """An origin cell in a template table, carrying its source formatting."""
    row_index: int
    col_index: int
    row_span: int = 1
    col_span: int = 1
    text: str = ""
    is_header: bool = False
    icon_key: Optional[str] = None
    icon_path: Optional[str] = None
    image_path: Optional[str] = None
    shading_hex: Optional[str] = None
    text_direction: Optional[str] = None
    valign: Optional[str] = None
    bold: bool = False

    def to_clean_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "row_index": self.row_index,
            "col_index": self.col_index,
            "row_span": self.row_span,
            "col_span": self.col_span,
            "text": self.text,
            "is_header": self.is_header,
        }
        if self.icon_key is not None:
            d["icon_key"] = self.icon_key
        if self.icon_path is not None:
            d["icon_path"] = self.icon_path
        if self.image_path is not None:
            d["image_path"] = self.image_path
        if self.shading_hex is not None:
            d["shading_hex"] = self.shading_hex
        if self.text_direction is not None:
            d["text_direction"] = self.text_direction
        if self.valign is not None:
            d["valign"] = self.valign
        if self.bold:
            d["bold"] = True
        return d


class TemplateElement(BaseModel):
    """A single linear element in the template skeleton.

    ``element_type`` is one of ``heading``, ``paragraph``, ``list``, ``table``,
    ``image``, ``icon`` or ``callout``.
    """
    element_type: str
    page: int = 0
    section_name: Optional[str] = None
    level: Optional[int] = None
    text: Optional[str] = None
    icons: list[TemplateIconRef] = Field(default_factory=list)
    items: list[str] = Field(default_factory=list)
    title: Optional[str] = None
    num_rows: Optional[int] = None
    num_cols: Optional[int] = None
    header_rows: Optional[int] = None
    style_name: Optional[str] = None
    col_widths_pt: list[float] = Field(default_factory=list)
    cells: list[TemplateTableCell] = Field(default_factory=list)
    image_path: Optional[str] = None
    is_instruction: bool = False
    instruction_text: Optional[str] = None
    font_color_hex: Optional[str] = None
    color_detection_method: Optional[str] = None
    shading_hex: Optional[str] = None
    callout_type: Optional[str] = None

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
        if self.color_detection_method is not None:
            d["color_detection_method"] = self.color_detection_method
        if self.shading_hex is not None:
            d["shading_hex"] = self.shading_hex
        if self.callout_type is not None:
            d["callout_type"] = self.callout_type
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
        if self.header_rows:
            d["header_rows"] = self.header_rows
        if self.style_name is not None:
            d["style_name"] = self.style_name
        if self.col_widths_pt:
            d["col_widths_pt"] = self.col_widths_pt
        if self.cells:
            d["cells"] = [c.to_clean_dict() for c in self.cells]
        if self.image_path is not None:
            d["image_path"] = self.image_path
        return d


# ── Sections ───────────────────────────────────────────────────────────

class TemplateSection(BaseModel):
    """A section contract: the skeleton to preserve and the instructions to obey.

    ``skeleton_elements`` is black template content that migration copies
    verbatim. ``authoring_instructions`` is blue content that migration follows
    and then removes from the output.
    """
    section_number: Optional[str] = None
    title: str
    heading_style: Optional[str] = None
    page_start: int = 1
    page_end: int = 1
    required: bool = True
    content_editable: bool = True
    allows_subsections: bool = True
    placeholders: list[str] = Field(default_factory=list)
    skeleton_elements: list[TemplateElement] = Field(default_factory=list)
    authoring_instructions: list[TemplateInstruction] = Field(default_factory=list)
    icons_expected: list[str] = Field(default_factory=list)
    callouts_allowed: list[str] = Field(default_factory=list)

    def to_clean_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "title": self.title,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "required": self.required,
            "content_editable": self.content_editable,
            "allows_subsections": self.allows_subsections,
            "skeleton_elements": [
                e.to_clean_dict(section_name=self.title) for e in self.skeleton_elements
            ],
            "authoring_instructions": [
                i.to_clean_dict() for i in self.authoring_instructions
            ],
        }
        if self.section_number is not None:
            d["section_number"] = self.section_number
        if self.heading_style is not None:
            d["heading_style"] = self.heading_style
        if self.placeholders:
            d["placeholders"] = self.placeholders
        if self.icons_expected:
            d["icons_expected"] = self.icons_expected
        if self.callouts_allowed:
            d["callouts_allowed"] = self.callouts_allowed
        return d


class TemplateGlobalRules(BaseModel):
    """Document-wide rules — blue instructions appearing before the first section."""
    instructions: list[TemplateInstruction] = Field(default_factory=list)

    def to_clean_dict(self) -> dict[str, Any]:
        return {
            "instructions": [i.to_clean_dict() for i in self.instructions],
        }


# ── Envelope ───────────────────────────────────────────────────────────

class TemplateMetadata(BaseModel):
    """Metadata extracted from the template document properties."""
    template_id: str = ""
    template_name: str = ""
    author: str = ""
    creation_date: str = ""
    modification_date: str = ""
    file_type: str = "docx"
    file_size_bytes: int = 0


class TemplateTotals(BaseModel):
    """Counters for the extracted template."""
    sections: int = 0
    elements: int = 0
    instructions: int = 0
    icons: int = 0
    callouts: int = 0

    def to_clean_dict(self) -> dict[str, Any]:
        return {
            "sections": self.sections,
            "elements": self.elements,
            "instructions": self.instructions,
            "icons": self.icons,
            "callouts": self.callouts,
        }


class TemplateExtractionOutput(BaseModel):
    """Top-level template extraction JSON envelope (v2.0)."""
    version: str = "2.0"
    template_id: str
    template_name: str
    metadata: TemplateMetadata = Field(default_factory=TemplateMetadata)
    icon_library: list[TemplateIconEntry] = Field(default_factory=list)
    callout_styles: list[TemplateCalloutStyle] = Field(default_factory=list)
    global_rules: TemplateGlobalRules = Field(default_factory=TemplateGlobalRules)
    sections: list[TemplateSection] = Field(default_factory=list)
    totals: TemplateTotals = Field(default_factory=TemplateTotals)

    def to_clean_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "template_id": self.template_id,
            "template_name": self.template_name,
            "metadata": self.metadata.model_dump(exclude_none=True),
            "icon_library": [i.to_clean_dict() for i in self.icon_library],
            "callout_styles": [c.to_clean_dict() for c in self.callout_styles],
            "global_rules": self.global_rules.to_clean_dict(),
            "sections": [s.to_clean_dict() for s in self.sections],
            "totals": self.totals.to_clean_dict(),
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
    total_callouts: int = 0
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
    total_callouts: int = 0
    status: str
    created_at: str
