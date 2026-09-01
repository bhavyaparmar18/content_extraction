"""Migration validator service for generating post-migration QA reports."""

from __future__ import annotations

from pathlib import Path
from docx import Document
from loguru import logger

from app.schemas.migration import DocxMigrationOutput
from app.services.migration.schemas import MigrationPlan, MigrationQAReport
from app.services.migration.toc_builder import TOCBuilder
from app.services.migration.instruction_cleaner import InstructionCleaner


class MigrationValidator:
    """Validates the migrated .docx document and produces a structured QA report."""

    def __init__(self):
        self._toc_builder = TOCBuilder()
        self._cleaner = InstructionCleaner()

    def validate(
        self,
        output_path: Path | str,
        extracted: DocxMigrationOutput,
        plan: MigrationPlan,
    ) -> MigrationQAReport:
        """Validate output .docx and generate a MigrationQAReport."""
        path = Path(output_path)
        if not path.exists():
            return MigrationQAReport(
                status="needs_review",
                validation_errors=[f"Output file does not exist: {path}"],
            )

        doc = Document(str(path))

        # Check remaining blue runs (including inside table cells)
        WNS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        blue_count = 0
        for p_elem in doc.element.body.iter(f"{{{WNS}}}p"):
            try:
                from docx.text.paragraph import Paragraph
                para = Paragraph(p_elem, doc)
                if self._cleaner._has_blue_runs(para):
                    blue_count += 1
            except Exception:
                continue

        # Verify heading styles for TOC
        heading_issues = self._toc_builder.verify_heading_styles(doc)

        # Content coverage metrics
        total_source_elements = sum(
            len(s.elements) for s in extracted.sections if not s.title.strip().startswith("0 ")
        )
        total_source_sections = len(
            [s for s in extracted.sections if not s.title.strip().startswith("0 ")]
        )

        # Calculate total placed and skipped elements
        placed_elements = 0
        skipped_elements = 0
        for sp in plan.section_plans:
            for elem in sp.elements:
                if elem.action == "skip":
                    skipped_elements += 1

            for src_title in sp.source_sections_mapped:
                src_sec = next((s for s in extracted.sections if s.title == src_title), None)
                if src_sec:
                    # Explicit skips
                    skips_in_sec = sum(1 for e in sp.elements if e.source_section_title == src_title and e.action == "skip")
                    placed_elements += (len(src_sec.elements) - skips_in_sec)

        coverage_pct = (
            min(100.0, (placed_elements / total_source_elements * 100.0))
            if total_source_elements > 0
            else 100.0
        )

        # Section status counts
        mapped_count = len(
            [sp for sp in plan.section_plans if not sp.is_unmapped_source and sp.has_source_content]
        )
        unmapped_source_count = len(
            [sp for sp in plan.section_plans if sp.is_unmapped_source]
        )
        no_content_sections = [
            sp.template_section_heading
            for sp in plan.section_plans
            if not sp.has_source_content and sp.fallback_action != "delete_section"
        ]
        deleted_sections = [
            sp.template_section_heading
            for sp in plan.section_plans
            if sp.fallback_action == "delete_section"
        ]

        # Determine overall status
        status = "pass"
        recommendations = []

        if blue_count > 0:
            status = "needs_review"
            recommendations.append(f"{blue_count} blue instructional text paragraphs remain in document")

        if heading_issues:
            if status != "needs_review":
                status = "pass_with_warnings"
            recommendations.append(f"{len(heading_issues)} headings may not use native Word styles for TOC")

        if plan.warnings:
            if status == "pass":
                status = "pass_with_warnings"

        if coverage_pct < 80.0:
            if status != "needs_review":
                status = "pass_with_warnings"
            recommendations.append(f"Content coverage is {coverage_pct:.1f}% (< 80%)")

        return MigrationQAReport(
            status=status,
            total_source_sections=total_source_sections,
            total_source_elements=total_source_elements,
            total_placed_elements=placed_elements,
            total_skipped_elements=skipped_elements,
            content_coverage_pct=round(coverage_pct, 1),
            sections_mapped=mapped_count,
            sections_unmapped_from_source=unmapped_source_count,
            sections_with_no_content=no_content_sections,
            sections_deleted=deleted_sections,
            blue_text_remaining=blue_count,
            heading_style_issues=heading_issues,
            low_confidence_warnings=plan.warnings,
            validation_errors=[],
            recommendations=recommendations,
            summarizer_mode="programmatic",
            llm_calls_made=1,
            llm_total_tokens=0,
        )
