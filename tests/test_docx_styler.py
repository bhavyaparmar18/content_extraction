"""Unit tests for DocxStyler and CalloutBuilder."""

import pytest
from pathlib import Path
from docx import Document

from app.schemas.migration import MigrationElement, MigrationTableCell
from app.services.migration.docx_styler import DocxStyler
from app.services.migration.callout_builder import CalloutBuilder
from app.services.migration.schemas import CalloutStyleDef


def test_docx_styler_headings_and_paragraphs(tmp_path):
    styler = DocxStyler()
    doc = Document()

    h1 = styler.insert_heading(doc, "1 PURPOSE", level=1, font_family="Arial", font_size_pt=14.0)
    assert h1.text == "1 PURPOSE"
    assert h1.style.name.startswith("Heading")

    p1 = styler.insert_paragraph(doc, "This is a body paragraph.", font_family="Arial", font_size_pt=10.0)
    assert p1.text == "This is a body paragraph."

    styler.insert_list(doc, ["Item 1", "Item 2"], font_family="Arial")

    out_file = tmp_path / "styled.docx"
    doc.save(str(out_file))
    assert out_file.exists()


def test_callout_builder_shading_and_borders(tmp_path):
    builder = CalloutBuilder()
    doc = Document()

    elem = MigrationElement(
        element_type="paragraph",
        text="Executive Summary: Learn what to expect from this section.",
    )
    style = CalloutStyleDef(
        callout_type="executive_summary",
        display_name="Executive Summary",
        background_color_hex="#D9E1F2",
        left_border_color_hex="#2F5597",
    )

    tbl = builder.build(doc, elem, style=style, font_family="Arial")
    assert len(tbl.rows) == 1
    assert len(tbl.columns) == 1
    assert "Executive Summary" in tbl.cell(0, 0).text

    out_file = tmp_path / "callout.docx"
    doc.save(str(out_file))
    assert out_file.exists()
