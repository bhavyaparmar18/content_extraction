"""Unit tests for Section-Wise Clean .docx-Ready Document Migration Exporter (v3.1)."""

import pytest
from app.schemas.ast_nodes import (
    DocumentNode,
    SectionNode,
    HeadingNode,
    ParagraphNode,
    ListNode,
    ListItemNode,
    TableNode,
    TableRowNode,
    TableCellNode,
    IconNode,
)
from app.services.export.migration_exporter import MigrationExporter


def test_migration_exporter_basic_sections():
    """Test section-wise element grouping and metadata extraction."""
    ast = DocumentNode()
    heading = HeadingNode(level=1, text="1 PURPOSE")
    para = ParagraphNode(text="Outlines the writing of GP Docs.")
    ast.children = [heading, para]

    output = MigrationExporter.export("test_doc_001", ast)
    assert output.document_id == "test_doc_001"
    assert output.version == "3.1"
    assert len(output.sections) == 1
    sec = output.sections[0]
    assert sec.section_number == "1"
    assert sec.title == "1 PURPOSE"
    assert len(sec.elements) == 2
    assert sec.elements[0].element_type == "heading"
    assert sec.elements[0].text == "1 PURPOSE"
    assert sec.elements[1].element_type == "paragraph"
    assert sec.elements[1].text == "Outlines the writing of GP Docs."


def test_migration_exporter_inline_icons_and_clean_dict():
    """Test that IconNode items are attached to adjacent paragraphs and clean_dict omits nulls."""
    ast = DocumentNode()
    heading = HeadingNode(level=1, text="2 APPLICABILITY")
    para1 = ParagraphNode(text="This Guidance is applicable:")
    icon1 = IconNode(asset_path="data/icons/vec1.png", semantic_meaning="unknown")
    para2 = ParagraphNode(text="To all authors who write GP Docs.")
    
    ast.children = [heading, para1, icon1, para2]

    output = MigrationExporter.export("test_icons_doc", ast)
    assert len(output.sections) == 1
    sec = output.sections[0]
    # No standalone 'icon' elements should be in sec.elements
    assert all(e.element_type != "icon" for e in sec.elements)
    assert len(sec.elements) == 3  # heading, para1, para2

    # Verify icon was attached to para1 (most recent element before icon1)
    assert len(sec.elements[1].icons) == 1
    assert sec.elements[1].icons[0].path == "data/icons/vec1.png"

    # Verify clean_dict strips empty arrays and null values
    clean = output.to_clean_dict()
    assert clean["version"] == "3.1"
    clean_sec = clean["sections"][0]
    assert "num_rows" not in clean_sec["elements"][0]
    assert "cells" not in clean_sec["elements"][0]
    assert "icons" in clean_sec["elements"][1]
    assert "icons" not in clean_sec["elements"][2]


def test_migration_exporter_table_with_merged_cells_and_icons():
    """Test table conversion with merged cells (col_span/row_span) and inline icon paths."""
    ast = DocumentNode()
    
    # Create TableNode
    table = TableNode(caption="Infographics Description", grid_cols=2)
    
    # Row 0: Header row
    cell_h0 = TableCellNode(row_index=0, col_index=0, is_merge_origin=True)
    cell_h0.content = [ParagraphNode(text="Icon")]
    cell_h1 = TableCellNode(row_index=0, col_index=1, is_merge_origin=True)
    cell_h1.content = [ParagraphNode(text="Description")]
    row0 = TableRowNode(row_index=0, is_header=True, cells=[cell_h0, cell_h1])

    # Row 1: Data row with Icon
    cell_d0 = TableCellNode(row_index=1, col_index=0, row_span=1, col_span=1, is_merge_origin=True)
    icon_node = IconNode(asset_path="data/extracted_icons/page4_vec0.png", semantic_meaning="unknown")
    cell_d0.content = [icon_node]
    
    cell_d1 = TableCellNode(row_index=1, col_index=1, row_span=1, col_span=1, is_merge_origin=True)
    cell_d1.content = [ParagraphNode(text="Executive Summary")]
    row1 = TableRowNode(row_index=1, is_header=False, cells=[cell_d0, cell_d1])

    table.rows = [row0, row1]
    ast.children = [table]

    output = MigrationExporter.export("test_table_doc", ast)
    assert len(output.sections) == 1
    sec = output.sections[0]
    assert len(sec.elements) == 1
    tbl_elem = sec.elements[0]
    assert tbl_elem.element_type == "table"
    assert tbl_elem.title == "Infographics Description"
    assert tbl_elem.num_rows == 2
    assert tbl_elem.num_cols == 2
    assert len(tbl_elem.cells) == 4

    # Verify cell with icon_path
    data_cell_0 = tbl_elem.cells[2]
    assert data_cell_0.row_index == 1
    assert data_cell_0.col_index == 0
    assert data_cell_0.icon_path == "data/extracted_icons/page4_vec0.png"

    # Verify cell with text
    data_cell_1 = tbl_elem.cells[3]
    assert data_cell_1.text == "Executive Summary"


def test_migration_exporter_strips_running_headers_and_footers():
    ast = DocumentNode(document_id="test_header_footer")

    # Running top headers
    h_num = ParagraphNode(text="Number: BI-VQD-24416 Version: 3.0 Effective Date: 17 Sep 2025")
    h_docname = ParagraphNode(text="Document Name: BI-VQD-24416-G")

    # Page 1 table (must be preserved!)
    tbl = TableNode(caption="GENERAL INFORMATION")
    cell = TableCellNode(row_index=0, col_index=0, row_span=1, col_span=1, is_merge_origin=True)
    cell.content = [ParagraphNode(text="Scope: Global")]
    tbl.rows = [TableRowNode(row_index=0, is_header=True, cells=[cell])]

    # Body heading and paragraph (must be preserved!)
    sec1 = HeadingNode(level=1, text="1 PURPOSE")
    p1 = ParagraphNode(text="This guidance outlines best practices.")

    # Bottom running footers
    f_life = ParagraphNode(text="Life forward")
    f_prop = ParagraphNode(text="Property of Boehringer Ingelheim Group of Companies – Use current version only")
    f_retr = ParagraphNode(text="Retrieved by Vicki Bendell on 03 Mar 2026")

    ast.children = [h_num, h_docname, tbl, sec1, p1, f_life, f_prop, f_retr]

    output = MigrationExporter.export("test_header_footer", ast)

    # Collect all element texts from exported sections
    extracted_texts = []
    for s in output.sections:
        for el in s.elements:
            if el.text:
                extracted_texts.append(el.text)
            if el.title:
                extracted_texts.append(el.title)

    assert "Number: BI-VQD-24416 Version: 3.0 Effective Date: 17 Sep 2025" not in extracted_texts
    assert "Document Name: BI-VQD-24416-G" not in extracted_texts
    assert "Life forward" not in extracted_texts
    assert "Retrieved by Vicki Bendell on 03 Mar 2026" not in extracted_texts
    assert "Property of Boehringer Ingelheim Group of Companies – Use current version only" not in extracted_texts

    # Verify valid body text and table are present
    assert "1 PURPOSE" in [s.title for s in output.sections]
    assert "This guidance outlines best practices." in extracted_texts
    assert "GENERAL INFORMATION" in extracted_texts
