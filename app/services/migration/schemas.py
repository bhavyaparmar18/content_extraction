"""Schemas for the LLM-driven SOP Content Migration Engine.

This module defines all Pydantic models for:
- Template inspection (TemplateRawProfile)
- Content summarization (ContentSummary - unified for Mode A and Mode B)
- Mode B LLM section semantic profiling (LLMSectionProfile)
- LLM migration planning (MigrationPlan, SectionPlan, ElementPlacement)
- Validation and QA reporting (MigrationQAReport, MigrationResult)
"""

from __future__ import annotations

from typing import Optional, Any
from pydantic import BaseModel, Field


# ── 1. Template Inspection Schemas ─────────────────────────────────────

class TemplateParagraphInfo(BaseModel):
    """One paragraph from the template document body."""
    index: int                                  # Position in document body (0-based)
    text: str                                   # Full text content
    style_name: str                             # "Heading 1", "Normal", "List Bullet", etc.
    is_blue_instruction: bool = False           # True if font color is blue (instructional text)
    is_bold: bool = False
    heading_level: Optional[int] = None         # 1, 2, 3 or None for non-headings
    font_color_hex: Optional[str] = None


class TemplateTableInfo(BaseModel):
    """One table from the template document."""
    index: int                                  # Table position in document body (0-based)
    num_rows: int
    num_cols: int
    preceding_heading: Optional[str] = None     # Nearest heading above this table
    header_row_text: list[str] = Field(default_factory=list)
    has_placeholder_text: bool = False          # Contains ${...}, [Insert ...], <<...>>
    sample_cells: list[str] = Field(default_factory=list)
    is_vault_token_table: bool = False          # Contains ${vault:...} cover page system tokens
    is_document_history_table: bool = False     # Template's real Document History revision table
    is_instructional_table: bool = False        # Contains blue instruction text or template example boxes


class TemplateRawProfile(BaseModel):
    """Complete machine-readable structural snapshot of a .docx template."""
    filename: str
    total_paragraphs: int
    total_tables: int
    paragraphs: list[TemplateParagraphInfo] = Field(default_factory=list)
    tables: list[TemplateTableInfo] = Field(default_factory=list)
    header_text: str = ""
    footer_text: str = ""


# ── 2. Content Summarization Schemas (Unified Mode A & B) ─────────────

class ContentElementSummary(BaseModel):
    """Summary of one extracted element for LLM context."""
    index: int                                  # Position within section's elements array
    element_type: str                           # "heading", "paragraph", "table", "image", "list"
    text_preview: str = ""                      # First 120 chars (Mode A) or synopsis (Mode B)
    level: Optional[int] = None                 # Heading level
    num_rows: Optional[int] = None
    num_cols: Optional[int] = None
    has_icons: bool = False
    icon_count: int = 0
    has_icon_in_cells: bool = False
    image_path_basename: Optional[str] = None   # Filename only (not full path)
    list_items_count: Optional[int] = None
    page: int = 0

    # Mode B enrichments (populated when use_llm_section_summarizer=true)
    semantic_role: Optional[str] = None          # "policy_statement", "callout_box", "flowchart_figure", etc.
    callout_candidate_type: Optional[str] = None # "executive_summary", "explanation", "attention", "key_takeaway"


class ContentSectionSummary(BaseModel):
    """Summary of one extracted section."""
    section_number: Optional[str] = None
    title: str
    page_start: int = 1
    page_end: int = 1
    total_elements: int = 0
    element_type_counts: dict[str, int] = Field(default_factory=dict)
    elements: list[ContentElementSummary] = Field(default_factory=list)

    # Mode B enrichments:
    semantic_purpose: Optional[str] = None      # 2-3 sentence section purpose summary
    taxonomy_category: Optional[str] = None     # "Purpose", "Applicability", "Process", etc.
    key_topics: list[str] = Field(default_factory=list)


class ContentSummary(BaseModel):
    """Unified content summary passed to Migration Planner LLM."""
    document_id: str
    document_type: Optional[str] = None
    total_sections: int = 0
    summarizer_mode: str = "programmatic"       # "programmatic" (Mode A) or "llm_semantic" (Mode B)
    sections: list[ContentSectionSummary] = Field(default_factory=list)


# ── 3. Mode B Per-Section LLM Structured Output ────────────────────────

class LLMElementDescriptor(BaseModel):
    """Per-element semantic annotation from the section summarizer LLM."""
    element_index: int
    semantic_role: str = "general_paragraph"    # "section_heading", "general_paragraph", "policy_statement",
                                                # "instruction_step", "data_table", "callout_box",
                                                # "flowchart_figure", "illustrative_image", "glossary_entry",
                                                # "raci_matrix", "reference_list", "general_list"
    summary: str = ""
    callout_candidate_type: Optional[str] = None  # "executive_summary", "explanation", "attention", "key_takeaway"


class LLMSectionProfile(BaseModel):
    """Structured output from per-section LLM summarizer worker."""
    semantic_purpose: str                       # 2-3 sentence overview of section's functional intent
    taxonomy_category: str                      # Standard SOP category
    key_topics: list[str] = Field(default_factory=list)
    element_descriptors: list[LLMElementDescriptor] = Field(default_factory=list)


# ── 4. LLM Migration Planner Structured Output ─────────────────────────

class ElementPlacement(BaseModel):
    """Exact placement instruction for one extracted element in output .docx."""
    source_section_title: str                   # e.g. "6 PRINCIPLES FOR DOCUMENT WRITING"
    source_element_index: int                   # Index within source section elements
    source_element_type: str                    # "heading", "paragraph", "table", "image", "list"
    target_section_heading: str                 # Target template section
    placement_order: int                        # Ordering within section (0, 1, 2, ...)
    action: str                                 # "insert_heading", "insert_paragraph", "insert_list",
                                                # "insert_table", "insert_image", "insert_callout",
                                                # "populate_placeholder", "skip"

    heading_level: Optional[int] = None
    heading_style: Optional[str] = None         # "Heading 1", "Heading 2", "Heading 3"
    callout_type: Optional[str] = None          # "executive_summary", "explanation", "attention", "key_takeaway"
    callout_background_hex: Optional[str] = None
    callout_border_hex: Optional[str] = None
    target_table_index: Optional[int] = None    # For populate_placeholder
    embed_icons_inline: bool = False
    notes: str = ""


class SectionPlan(BaseModel):
    """Migration instructions for one section in the output .docx."""
    template_section_heading: str
    template_heading_level: int = 1
    template_paragraph_indices_to_delete: list[int] = Field(default_factory=list)
    source_sections_mapped: list[str] = Field(default_factory=list)
    elements: list[ElementPlacement] = Field(default_factory=list)

    has_source_content: bool = True
    fallback_action: Optional[str] = None       # "insert_none", "insert_na", "delete_section"
    fallback_text: Optional[str] = None

    is_unmapped_source: bool = False            # True if section came from source with no template counterpart
    insertion_after_section: Optional[str] = None  # Which template section to insert after


class PlaceholderTablePlan(BaseModel):
    """Instructions for populating or deleting a template placeholder table."""
    table_index: int
    table_purpose: str
    parent_section_heading: str
    action: str                                 # "populate" | "delete"
    source_section_title: Optional[str] = None
    source_element_index: Optional[int] = None
    column_mapping: Optional[dict[str, str]] = None
    sort_alphabetically: bool = False
    population_notes: str = ""


class CalloutStyleDef(BaseModel):
    """Dynamic callout box style definition discovered from template."""
    callout_type: str                           # "executive_summary", "explanation", "attention", "key_takeaway"
    display_name: str
    background_color_hex: str
    left_border_color_hex: str
    icon_description: Optional[str] = None


class MigrationPlan(BaseModel):
    """Complete element-level migration blueprint produced by LLM Planner."""
    template_name: str
    document_type_detected: Optional[str] = None

    # Typography
    font_family: str = "Arial"
    font_size_body_pt: float = 10.0
    font_size_heading1_pt: float = 14.0
    font_size_heading2_pt: float = 12.0
    font_size_heading3_pt: float = 11.0

    # Global rules
    preserve_headers_footers: bool = True
    toc_auto_generated: bool = True
    skip_cover_page: bool = True

    # Section-by-section plan
    section_plans: list[SectionPlan] = Field(default_factory=list)
    placeholder_tables: list[PlaceholderTablePlan] = Field(default_factory=list)
    tables_to_delete: list[int] = Field(default_factory=list)
    callout_styles: list[CalloutStyleDef] = Field(default_factory=list)

    # Quality signals
    overall_confidence: float = 0.0
    warnings: list[str] = Field(default_factory=list)
    reasoning_summary: str = ""


# ── 5. Validation & Result Schemas ─────────────────────────────────────

class MigrationQAReport(BaseModel):
    """Post-migration quality assurance report for human review."""
    status: str = "pass"                        # "pass" | "pass_with_warnings" | "needs_review"

    # Content coverage
    total_source_sections: int = 0
    total_source_elements: int = 0
    total_placed_elements: int = 0
    total_skipped_elements: int = 0
    content_coverage_pct: float = 100.0

    # Section mapping
    sections_mapped: int = 0
    sections_unmapped_from_source: int = 0
    sections_with_no_content: list[str] = Field(default_factory=list)
    sections_deleted: list[str] = Field(default_factory=list)

    # Quality checks
    blue_text_remaining: int = 0
    heading_style_issues: list[str] = Field(default_factory=list)
    low_confidence_warnings: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    # LLM usage
    summarizer_mode: str = "programmatic"
    llm_calls_made: int = 0
    llm_total_tokens: int = 0


class MigrationResult(BaseModel):
    """Top-level result envelope returned by DocxMigrator.migrate()."""
    output_path: str
    plan: MigrationPlan
    qa_report: MigrationQAReport
