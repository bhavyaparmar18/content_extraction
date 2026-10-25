"""Translation of a completed migration: languages, glossaries, segments and translation jobs.

See docs/translation/IMPLEMENTATION_PLAN.md. The English migrated document is cut
into segments (claims, table cells, cross-reference phrases and the template's own
body text); each language is one translation job that translates them and renders
the document again. Glossaries and language templates are optional on a job.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import Field, field_validator, model_validator

from .common import V2Model
from .job import ArtifactKind, ArtifactRef


class LanguageCode(str, Enum):
    """The target languages; values are the Word ``w:lang`` codes."""

    ZH_CN = "zh-CN"  # Chinese (Simplified)
    FR_FR = "fr-FR"
    DE_DE = "de-DE"
    IT_IT = "it-IT"
    JA_JP = "ja-JP"
    PT_BR = "pt-BR"  # Portuguese (Brazil)
    ES_ES = "es-ES"
    EL_GR = "el-GR"


SOURCE_LANGUAGE = "en"


# ── Glossary ──────────────────────────────────────────────────────────


class GlossaryEntry(V2Model):
    source_term: str
    target_term: str = Field(default="", description="Empty only when do_not_translate (then the source term is kept)")
    note: Optional[str] = None
    case_sensitive: bool = False
    do_not_translate: bool = False

    @field_validator("source_term", "target_term")
    @classmethod
    def _strip(cls, value: str) -> str:
        return " ".join(value.split())

    @model_validator(mode="after")
    def _has_target(self) -> "GlossaryEntry":
        if not self.source_term:
            raise ValueError("a glossary entry needs a source term")
        if self.do_not_translate:
            if not self.target_term:
                self.target_term = self.source_term
            elif self.target_term != self.source_term:
                raise ValueError(f"{self.source_term!r} is do-not-translate but has a different target term")
        elif not self.target_term:
            raise ValueError(f"glossary entry {self.source_term!r} has no target term")
        return self

    @property
    def key(self) -> str:
        return self.source_term if self.case_sensitive else self.source_term.casefold()


class Glossary(V2Model):
    """One glossary version: the terms a translation into ``language`` must use."""

    glossary_id: str
    version: int = Field(ge=1)
    language: LanguageCode
    name: str
    entries: list[GlossaryEntry] = Field(default_factory=list)
    style_notes: Optional[str] = Field(default=None, description="Passed to the translation prompt verbatim")

    @model_validator(mode="after")
    def _unique_terms(self) -> "Glossary":
        seen: set[str] = set()
        for entry in self.entries:
            if entry.key in seen:
                raise ValueError(f"glossary term {entry.source_term!r} is listed more than once")
            seen.add(entry.key)
        return self


# ── Segments ──────────────────────────────────────────────────────────


class SegmentKind(str, Enum):
    CLAIM = "claim"                  # Claim.text of a section draft
    TABLE_CELL = "table_cell"        # TableCell.text (or one of its paragraphs) of a source table unit
    TABLE_HEADER = "table_header"    # TableRef.header_cells
    XREF = "xref"                    # AssembledDocument.refs[].text; the number is kept as a placeholder
    TEMPLATE_TEXT = "template_text"  # the template's own body text outside the slots and the cover


class SegmentOrigin(str, Enum):
    LLM = "llm"
    REPAIR = "repair"
    HUMAN = "human"
    COPIED = "copied"  # nothing to translate (no letters, or a do-not-translate term only)


class SegmentLocator(V2Model):
    """Where a segment's text goes back; which fields are set depends on the kind."""

    section_id: Optional[str] = Field(default=None, description="claim: the target section")
    slot_id: Optional[str] = None
    claim_id: Optional[str] = Field(default=None, description="claim, xref: the claim")
    unit_id: Optional[str] = Field(default=None, description="table_cell, table_header: the table unit")
    row: Optional[int] = Field(default=None, ge=0)
    col: Optional[int] = Field(default=None, ge=0)
    paragraph: Optional[int] = Field(default=None, ge=0, description="table_cell: index into TableCell.paragraphs")
    ref_index: Optional[int] = Field(default=None, ge=0, description="xref: index into AssembledDocument.refs")
    block_path: Optional[str] = Field(default=None, description="template_text: the paragraph's place in the body")


_REQUIRED_LOCATOR = {
    SegmentKind.CLAIM: ("section_id", "slot_id", "claim_id"),
    SegmentKind.TABLE_CELL: ("unit_id", "col"),
    SegmentKind.TABLE_HEADER: ("unit_id", "col"),
    SegmentKind.XREF: ("claim_id", "ref_index"),
    SegmentKind.TEMPLATE_TEXT: ("block_path",),
}


class Segment(V2Model):
    segment_id: str = Field(description="e.g. 'SEG-0042', unique within a job")
    kind: SegmentKind
    source_text: str
    target_text: Optional[str] = Field(default=None, description="None until translated")
    origin: Optional[SegmentOrigin] = None
    locator: SegmentLocator

    @model_validator(mode="after")
    def _locator_fits_kind(self) -> "Segment":
        missing = [f for f in _REQUIRED_LOCATOR[self.kind] if getattr(self.locator, f) is None]
        if missing:
            raise ValueError(f"segment {self.segment_id} ({self.kind.value}) has no locator {', '.join(missing)}")
        if self.target_text is not None and self.origin is None:
            raise ValueError(f"segment {self.segment_id} is translated but has no origin")
        return self


class TranslationSet(V2Model):
    """The segments of one scope (a target section, or ``template`` / ``xrefs``) in one language.

    Stored as the versioned ``translation[<scope>]`` artifact; an edit makes a new version.
    """

    job_id: str
    language: LanguageCode
    scope: str
    version: int = Field(ge=1)
    segments: list[Segment] = Field(default_factory=list)
    prompt_version: Optional[str] = None
    model: Optional[str] = None

    @model_validator(mode="after")
    def _unique_ids(self) -> "TranslationSet":
        ids = [s.segment_id for s in self.segments]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"segment ids repeat: {dupes}")
        return self

    @property
    def untranslated(self) -> list[Segment]:
        return [s for s in self.segments if s.target_text is None]


# ── Jobs ──────────────────────────────────────────────────────────────


class TranslationStatus(str, Enum):
    PENDING = "PENDING"
    PREPARING = "PREPARING"
    TRANSLATING = "TRANSLATING"
    CHECKING = "CHECKING"
    REPAIRING = "REPAIRING"
    RENDERING = "RENDERING"
    REVIEW_PENDING = "REVIEW_PENDING"
    APPROVED = "APPROVED"
    FAILED_TECHNICAL = "FAILED_TECHNICAL"
    CANCELLED = "CANCELLED"


TRANSLATION_TERMINAL_STATUSES = frozenset(
    {TranslationStatus.APPROVED, TranslationStatus.FAILED_TECHNICAL, TranslationStatus.CANCELLED}
)


class TranslationJob(V2Model):
    """One language of one completed migration. The glossary and the language template are optional."""

    job_id: str = Field(description="e.g. 'TRN-20261025-1A2B3C4D'")
    migration_job_id: str
    language: LanguageCode
    glossary_id: Optional[str] = None
    glossary_version: Optional[int] = Field(default=None, ge=1)
    language_template_id: Optional[str] = None
    language_template_version: Optional[int] = Field(default=None, ge=1)
    status: TranslationStatus = TranslationStatus.PENDING
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    created_by: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    error: Optional[str] = None

    @model_validator(mode="after")
    def _versions_with_ids(self) -> "TranslationJob":
        for name in ("glossary", "language_template"):
            if (getattr(self, f"{name}_id") is None) != (getattr(self, f"{name}_version") is None):
                raise ValueError(f"{name}_id and {name}_version go together")
        return self

    @property
    def is_terminal(self) -> bool:
        return self.status in TRANSLATION_TERMINAL_STATUSES

    def latest_artifact(self, kind: ArtifactKind, scope: Optional[str] = None) -> Optional[ArtifactRef]:
        matches = [a for a in self.artifacts if a.kind == kind and a.scope == scope]
        return max(matches, key=lambda a: a.version, default=None)


# ── Language template front matter ────────────────────────────────────

CoverEnd = Literal["section_break", "page_break"]


class FrontMatterPart(V2Model):
    """One header or footer of a front-matter section."""

    kind: Literal["header", "footer"]
    type: Literal["default", "first", "even"]
    partname: str
    text: str = Field(default="", description="the first characters of its text")
    images: int = Field(default=0, ge=0)


class FrontMatterReport(V2Model):
    """What was taken from a language template: its first page, headers and footers.

    ``problems`` block marking the template ready; ``warnings`` are shown to the admin.
    """

    template_id: str
    version: int = Field(ge=1)
    language: LanguageCode
    source_filename: Optional[str] = None
    source_sha256: str = ""
    cover_end: Optional[CoverEnd] = Field(default=None, description="how the first page ends; None when not found")
    cover_blocks: int = Field(default=0, ge=0)
    cover_text: str = ""
    sections: int = Field(default=0, ge=0, description="sections in the language template")
    title_page_cover: bool = False
    title_page_body: bool = False
    even_and_odd: bool = False
    cover_parts: list[FrontMatterPart] = Field(default_factory=list)
    body_parts: list[FrontMatterPart] = Field(default_factory=list)
    styles: list[str] = Field(default_factory=list, description="style ids the first page and headers use")
    images: int = Field(default=0, ge=0)
    problems: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


class FrontMatterSwap(V2Model):
    """What ``apply_front_matter`` changed in a document."""

    blocks_removed: int = 0
    blocks_inserted: int = 0
    sections_rewired: int = 0
    parts_added: list[str] = Field(default_factory=list)
    parts_dropped: list[str] = Field(default_factory=list)
    styles_added: list[str] = Field(default_factory=list)
    styles_replaced: list[str] = Field(default_factory=list, description="styles only the front matter uses, given the language template's definition")
    warnings: list[str] = Field(default_factory=list)
