"""Unit tests for Mode A ContentSummarizer."""

import pytest
from app.schemas.migration import (
    DocxMigrationOutput,
    MigrationMetadata,
    MigrationSection,
    MigrationElement,
    MigrationTableCell,
    MigrationIconRef,
)
from app.services.migration.content_summarizer import ContentSummarizer


@pytest.fixture
def sample_extracted_output() -> DocxMigrationOutput:
    return DocxMigrationOutput(
        document_id="test_doc_123",
        metadata=MigrationMetadata(
            document_id="test_doc_123",
            document_type="Governance and Procedure > Guidance",
            title="Good Writing Practice",
        ),
        sections=[
            MigrationSection(
                title="0 PREAMBLE",
                section_number="0",
                elements=[
                    MigrationElement(element_type="table", num_rows=4, num_cols=2),
                ],
            ),
            MigrationSection(
                title="1 PURPOSE",
                section_number="1",
                elements=[
                    MigrationElement(
                        element_type="paragraph",
                        text="This Guidance provides instruction on writing good SOPs and GP documents.",
                        icons=[MigrationIconRef(icon_id="ic1", path="data/icons/vec1.png")],
                    ),
                ],
            ),
            MigrationSection(
                title="6 PRINCIPLES FOR DOCUMENT WRITING",
                section_number="6",
                elements=[
                    MigrationElement(element_type="heading", level=2, text="6.1 LANGUAGE AND WORDING"),
                    MigrationElement(element_type="paragraph", text="Active voice is key."),
                    MigrationElement(element_type="image", title="Flow Chart", image_path="data/images/img1.png"),
                    MigrationElement(
                        element_type="table",
                        num_rows=2,
                        num_cols=2,
                        cells=[
                            MigrationTableCell(row_index=0, col_index=0, text="Term", is_header=True),
                            MigrationTableCell(row_index=0, col_index=1, text="Def", is_header=True),
                            MigrationTableCell(row_index=1, col_index=0, text="SOP", icon_path="data/icons/ic2.png"),
                            MigrationTableCell(row_index=1, col_index=1, text="Standard Operating Procedure"),
                        ],
                    ),
                ],
            ),
        ],
    )


def test_content_summarizer_skip_preamble(sample_extracted_output):
    summarizer = ContentSummarizer()
    summary = summarizer.summarize(sample_extracted_output, skip_preamble=True)

    assert summary.document_id == "test_doc_123"
    assert summary.summarizer_mode == "programmatic"
    # Preamble should be skipped
    assert len(summary.sections) == 2
    assert all(s.title != "0 PREAMBLE" for s in summary.sections)

    sec1 = summary.sections[0]
    assert sec1.title == "1 PURPOSE"
    assert len(sec1.elements) == 1
    assert sec1.elements[0].has_icons is True
    assert sec1.elements[0].icon_count == 1

    sec6 = summary.sections[1]
    assert sec6.title == "6 PRINCIPLES FOR DOCUMENT WRITING"
    assert len(sec6.elements) == 4
    # Check image element summary
    assert sec6.elements[2].element_type == "image"
    assert sec6.elements[2].image_path_basename == "img1.png"
    # Check table element summary with cell icons
    assert sec6.elements[3].element_type == "table"
    assert sec6.elements[3].has_icon_in_cells is True


def test_content_summarizer_include_preamble(sample_extracted_output):
    summarizer = ContentSummarizer()
    summary = summarizer.summarize(sample_extracted_output, skip_preamble=False)
    assert len(summary.sections) == 3
    assert summary.sections[0].title == "0 PREAMBLE"
