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
    ImageNode,
    SourceLocation,
)
from app.schemas.document import BoundingBox, DocumentMetadata
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


def test_migration_exporter_metadata_field_names():
    ast = DocumentNode(
        doc_metadata=DocumentMetadata(
            document_title="Good Writing Practice",
            document_name="BI-VQD-24416-G",
            document_number="BI-VQD-24416",
            document_version="3.0",
            document_type="Guidance",
            file_type="pdf",
            gpdat_version=2,
            page_count=15,
        )
    )
    output = MigrationExporter.export("BI-VQD-24416_BI-VQD-24416-G_v3.0", ast)
    dumped = output.to_clean_dict()
    assert dumped["document_Uid"] == "BI-VQD-24416_BI-VQD-24416-G_v3.0"
    meta = dumped["metadata"]
    assert meta["document_Uid"] == "BI-VQD-24416_BI-VQD-24416-G_v3.0"
    assert meta["document_title"] == "Good Writing Practice"
    assert meta["document_name"] == "BI-VQD-24416-G"
    assert meta["file_type"] == "pdf"
    assert meta["gpdat_version"] == 2
    assert "duplicate_upload_count" not in meta
    assert "title" not in meta


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
    assert all(e.element_type != "icon" for e in sec.elements)
    assert len(sec.elements) == 3  # heading, para1, para2

    # Icon precedes the text it annotates in SOP layout — bind to the next element.
    assert len(sec.elements[1].icons) == 0
    assert len(sec.elements[2].icons) == 1
    assert sec.elements[2].icons[0].path == "data/icons/vec1.png"

    clean = output.to_clean_dict()
    assert clean["version"] == "3.1"
    clean_sec = clean["sections"][0]
    assert "num_rows" not in clean_sec["elements"][0]
    assert "cells" not in clean_sec["elements"][0]
    assert "icons" not in clean_sec["elements"][1]
    assert "icons" in clean_sec["elements"][2]


def test_migration_exporter_spreads_left_rail_icons():
    ast = DocumentNode()
    ast.children = [
        HeadingNode(level=1, text="1 PURPOSE"),
        IconNode(asset_path="data/icons/a.png"),
        IconNode(asset_path="data/icons/b.png"),
        ParagraphNode(text="First."),
        ParagraphNode(text="Second."),
    ]
    sec = MigrationExporter.export("test_spread", ast).sections[0]
    paras = [e for e in sec.elements if e.element_type == "paragraph"]
    assert [i.path for i in paras[0].icons] == ["data/icons/a.png"]
    assert [i.path for i in paras[1].icons] == ["data/icons/b.png"]


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


def test_subsections_do_not_create_separate_sections():
    """Verify that subsections (level >= 2 or decimal numbering like 6.1) stay within their parent section."""
    ast = DocumentNode()
    sec6 = SectionNode(
        heading=HeadingNode(level=1, text="6 PRINCIPLES FOR DOCUMENT WRITING"),
        level=1,
        children=[
            ParagraphNode(text="Introductory text for principles."),
            SectionNode(
                heading=HeadingNode(level=2, text="6.1 LANGUAGE AND WORDING"),
                level=2,
                children=[
                    ParagraphNode(text="Keep sentences concise."),
                    SectionNode(
                        heading=HeadingNode(level=3, text="6.1.1 Active Voice"),
                        level=3,
                        children=[
                            ParagraphNode(text="Always use active verbs."),
                        ],
                    ),
                ],
            ),
            SectionNode(
                heading=HeadingNode(level=2, text="6.2 ACCESSIBILITY"),
                level=2,
                children=[
                    ParagraphNode(text="Provide accessible formats."),
                ],
            ),
        ],
    )
    sec7 = SectionNode(
        heading=HeadingNode(level=1, text="7 GUIDANCE FOR SPECIFIC DOCUMENT CHAPTERS"),
        level=1,
        children=[
            ParagraphNode(text="Chapter guidance text."),
        ],
    )
    ast.children = [sec6, sec7]

    output = MigrationExporter.export("test_subsections_doc", ast)
    # Only 2 major sections should be created: Section 6 and Section 7
    section_titles = [s.title for s in output.sections]
    assert "6 PRINCIPLES FOR DOCUMENT WRITING" in section_titles
    assert "7 GUIDANCE FOR SPECIFIC DOCUMENT CHAPTERS" in section_titles
    assert "6.1 LANGUAGE AND WORDING" not in section_titles
    assert "6.2 ACCESSIBILITY" not in section_titles
    assert len(output.sections) == 2

    # Verify that subsections 6.1, 6.1.1, and 6.2 are present as heading elements inside section 6
    sec6_out = next(s for s in output.sections if "6 PRINCIPLES" in s.title)
    elem_texts = [e.text for e in sec6_out.elements if e.element_type == "heading"]
    assert "6.1 LANGUAGE AND WORDING" in elem_texts
    assert "6.1.1 Active Voice" in elem_texts
    assert "6.2 ACCESSIBILITY" in elem_texts


def test_list_items_do_not_create_new_sections():
    """Verify that numbered tips ending with ':' and bullet items do not create sections and are classed as lists."""
    ast = DocumentNode()
    sec = SectionNode(
        heading=HeadingNode(level=1, text="6 PRINCIPLES FOR DOCUMENT WRITING"),
        level=1,
        children=[
            HeadingNode(level=1, text="1. Active Voice is Key:"),
            ParagraphNode(text="Always pair specific role names with active verbs."),
            HeadingNode(level=1, text="2. Brevity Matters:"),
            ParagraphNode(text="Write short sentences."),
            HeadingNode(level=1, text="● Important consideration"),
            ParagraphNode(text="Details about the bullet point."),
        ],
    )
    ast.children = [sec]

    output = MigrationExporter.export("test_list_headings_doc", ast)
    # Only 1 section should be created
    assert len(output.sections) == 1
    sec_out = output.sections[0]
    assert sec_out.title == "6 PRINCIPLES FOR DOCUMENT WRITING"

    # Verify list elements were produced instead of new top-level sections
    list_items = [item for e in sec_out.elements if e.element_type == "list" for item in e.items]
    assert "1. Active Voice is Key:" in list_items
    assert "2. Brevity Matters:" in list_items
    assert "● Important consideration" in list_items


def _loc(page: int, y0: float, y1: float, x0: float = 72, x1: float = 500) -> SourceLocation:
    return SourceLocation(
        page=page,
        bbox=BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1, page=page),
    )


def test_migration_exporter_reclaims_purpose_continuation():
    """Lowercase leftover after the next heading stays in PURPOSE."""
    ast = DocumentNode()
    ast.children = [
        HeadingNode(level=1, text="1 PURPOSE", source_location=_loc(3, 80, 100)),
        ParagraphNode(text="This SOP", source_location=_loc(3, 110, 125, x1=150)),
        HeadingNode(level=1, text="2 APPLICABILITY", source_location=_loc(3, 200, 220)),
        ParagraphNode(text="This SOP is applicable:", source_location=_loc(3, 230, 245)),
        ParagraphNode(
            text="defines the change control process which is implemented in GOTrack.",
            source_location=_loc(3, 140, 180, x0=120),
        ),
        ParagraphNode(
            text="Employees who perform change control.",
            source_location=_loc(3, 260, 300, x0=120),
        ),
    ]
    output = MigrationExporter.export("test_purpose_reclaim", ast)
    titles = [s.title for s in output.sections]
    assert titles[:2] == ["1 PURPOSE", "2 APPLICABILITY"]
    purpose = next(s for s in output.sections if s.section_number == "1")
    purpose_text = [e.text for e in purpose.elements if e.element_type == "paragraph"]
    assert purpose_text[0] == "This SOP"
    assert purpose_text[1].startswith("defines the change control")
    appl = next(s for s in output.sections if s.section_number == "2")
    appl_text = [e.text for e in appl.elements if e.element_type == "paragraph"]
    assert appl_text[0] == "This SOP is applicable:"
    assert all(not (t or "").startswith("defines the change") for t in appl_text)


def test_migration_exporter_rebinds_icons_by_y_overlap():
    """Sequential next-element pairing is corrected using bounding boxes."""
    ast = DocumentNode()
    ast.children = [
        HeadingNode(level=1, text="2 APPLICABILITY", source_location=_loc(3, 80, 100)),
        ParagraphNode(text="This SOP is applicable:", source_location=_loc(3, 110, 125)),
        IconNode(asset_path="data/icons/buildings.png", source_location=_loc(3, 200, 240, 72, 110)),
        IconNode(asset_path="data/icons/person.png", source_location=_loc(3, 140, 180, 72, 110)),
        ParagraphNode(
            text="Employees who perform change control.",
            source_location=_loc(3, 140, 180, 120, 500),
        ),
        ParagraphNode(
            text="All areas where changes are processed.",
            source_location=_loc(3, 200, 240, 120, 500),
        ),
    ]
    sec = MigrationExporter.export("test_icon_y", ast).sections[0]
    paras = [e for e in sec.elements if e.element_type == "paragraph"]
    by_text = {e.text: [i.path for i in e.icons] for e in paras}
    assert by_text["This SOP is applicable:"] == []
    assert by_text["Employees who perform change control."] == ["data/icons/person.png"]
    assert by_text["All areas where changes are processed."] == ["data/icons/buildings.png"]


def test_migration_exporter_collapses_sparse_infographic_table():
    """Colored-row pdfplumber grids collapse to icon | description."""
    ast = DocumentNode()
    table = TableNode(caption=None, grid_cols=6)

    def cell(r, c, text="", image=None, header=False, span=1):
        node = TableCellNode(
            row_index=r, col_index=c, row_span=1, col_span=span, is_merge_origin=True
        )
        content = []
        if text:
            content.append(ParagraphNode(text=text))
        if image:
            content.append(ImageNode(asset_path=image))
        node.content = content
        return node

    rows = []
    # Header
    rows.append(TableRowNode(row_index=0, is_header=True, cells=[
        cell(0, 0, ""),
        cell(0, 1, "Infographics", span=2),
        cell(0, 3, ""),
        cell(0, 4, "Description", span=2),
    ]))
    rows.append(TableRowNode(row_index=1, cells=[
        cell(1, 0, ""),
        cell(1, 1, image="data/extracted_images/checklist.png"),
        cell(1, 4, "o\nExecutive Summary/Introduction – short description of", span=2),
    ]))
    rows.append(TableRowNode(row_index=2, cells=[
        cell(2, 4, "Executive Summary/Introduction – short description of what you can expect from the following chapter.", span=2),
    ]))
    rows.append(TableRowNode(row_index=3, cells=[
        cell(3, 1, image="data/extracted_images/question.png"),
        cell(3, 3, "Explanation – additional information to the topic", span=2),
    ]))
    rows.append(TableRowNode(row_index=4, cells=[
        cell(4, 1, image="data/extracted_images/warning.png"),
        cell(4, 4, "Attention – notice taken of something interesting or", span=2),
    ]))
    rows.append(TableRowNode(row_index=5, cells=[
        cell(5, 4, "Attention – notice taken of something interesting or important", span=2),
    ]))
    table.rows = rows
    ast.children = [HeadingNode(level=1, text="3 DEFINITIONS & ABBREVIATIONS"), table]

    output = MigrationExporter.export("test_infographic", ast)
    tbl = next(e for s in output.sections for e in s.elements if e.element_type == "table")
    assert tbl.num_cols == 2
    assert tbl.num_rows == 4  # header + 3 legend rows
    texts = {(c.row_index, c.col_index): c.text for c in tbl.cells}
    assert texts[(0, 0)] == "Infographics"
    assert texts[(0, 1)] == "Description"
    assert "expect from the following chapter" in texts[(1, 1)]
    assert texts[(1, 1)].startswith("Executive Summary")
    assert "o" not in texts[(1, 1)][:3]
    assert texts[(2, 1)].startswith("Explanation")
    assert texts[(3, 1)].endswith("important")
    icons = [c.icon_path for c in tbl.cells if c.icon_path]
    assert len(icons) == 3
