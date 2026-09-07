"""Tests for stitching tables that continue across pages."""

from app.config.settings import Settings
from app.schemas.document import (
    BoundingBox,
    ElementType,
    ExtractedTable,
    ExtractedTableCell,
    PageContent,
    RawDocument,
    DocumentMetadata,
)
from app.services.extraction.cross_page_stitcher import CrossPageTableStitcher


def _box(page, y0, y1, x0=72, x1=500):
    return BoundingBox(x0=x0, y0=y0, x1=x1, y1=y1, page=page)


def _cell(text, page, y0, y1, x0=72, x1=280):
    return ExtractedTableCell(
        content_text=text,
        bbox=_box(page, y0, y1, x0, x1),
    )


def _roles_table(page, y0, y1, rows, headers=True):
    hdr = [
        _cell("Role", page, y0, y0 + 20, 72, 200),
        _cell("Responsibility", page, y0, y0 + 20, 210, 500),
    ] if headers else []
    data = []
    for i, (left, right) in enumerate(rows):
        ry0 = y0 + 25 + i * 40
        data.append([
            _cell(left, page, ry0, ry0 + 30, 72, 200),
            _cell(right, page, ry0, ry0 + 30, 210, 500),
        ])
    last_y1 = data[-1][0].bbox.y1 if data else y1
    return ExtractedTable(
        content="roles",
        page=page,
        bbox=_box(page, y0, last_y1),
        grid_cols=2,
        headers=hdr,
        rows=data,
    )


def test_stitcher_skips_empty_page_and_merges_continuation_row():
    page9 = _roles_table(
        9, 600, 780,
        [("Change Owner", "Initiate the change")],
    )
    page9.rows[-1][0].bbox = _box(9, 700, 760, 72, 200)
    page9.rows[-1][1].bbox = _box(9, 700, 760, 210, 500)
    page9.bbox = _box(9, 600, 760)

    page11 = _roles_table(
        11, 80, 200,
        [("", "Sign for correctness of Change Plan"), ("Assessor(s)", "Perform assessments")],
    )

    doc = RawDocument(
        source="test.pdf",
        metadata=DocumentMetadata(file_type="pdf", page_count=3),
        pages=[
            PageContent(page_number=9, elements=[page9], width=612, height=792),
            PageContent(page_number=10, elements=[], width=612, height=792),
            PageContent(page_number=11, elements=[page11], width=612, height=792),
        ],
    )
    CrossPageTableStitcher(Settings()).extract(doc)

    tables = [el for p in doc.pages for el in p.elements if el.element_type == ElementType.TABLE]
    assert len(tables) == 1
    roles = [row[0].content_text for row in tables[0].rows]
    assert roles[0] == "Change Owner"
    assert "Sign for correctness" in tables[0].rows[0][1].content_text
    assert roles[1] == "Assessor(s)"
    assert not any(el.element_type == ElementType.TABLE for el in doc.pages[2].elements)
