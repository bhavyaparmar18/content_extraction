"""Tests for sparse infographic-table collapse."""

from app.schemas.document import ExtractedImage, ExtractedTableCell
from app.services.extraction.tables import collapse_sparse_grid, clean_table_cell_text


def _img(name: str) -> ExtractedImage:
    return ExtractedImage(image_path=name, page=1)


def _cell(text: str = "", media=None) -> ExtractedTableCell:
    return ExtractedTableCell(content_text=text, media_nodes=media or [])


def test_clean_table_cell_text_drops_watermark_letter():
    assert clean_table_cell_text("o\nExecutive Summary/Introduction – short description of") == (
        "Executive Summary/Introduction – short description of"
    )


def test_collapse_sparse_infographic_grid():
    rows = [
        [_cell(), _cell("Infographics"), _cell(), _cell(), _cell("Description"), _cell()],
        [
            _cell(),
            _cell(media=[_img("checklist.png")]),
            _cell(),
            _cell(),
            _cell("o\nExecutive Summary/Introduction – short description of"),
            _cell(),
        ],
        [
            _cell(),
            _cell(),
            _cell(),
            _cell(),
            _cell(
                "Executive Summary/Introduction – short description of what you can expect from the following chapter."
            ),
            _cell(),
        ],
        [
            _cell(),
            _cell(media=[_img("question.png")]),
            _cell(),
            _cell("Explanation – additional information to the topic"),
            _cell(),
            _cell(),
        ],
        [
            _cell(),
            _cell(media=[_img("warning.png")]),
            _cell(),
            _cell(),
            _cell("Attention – notice taken of something interesting or"),
            _cell(),
        ],
        [
            _cell(),
            _cell(),
            _cell(),
            _cell(),
            _cell("Attention – notice taken of something interesting or important"),
            _cell(),
        ],
    ]
    collapsed = collapse_sparse_grid(rows)
    assert len(collapsed) == 4
    assert len(collapsed[0]) == 2
    assert collapsed[0][0].content_text == "Infographics"
    assert collapsed[0][1].content_text == "Description"
    assert collapsed[1][0].media_nodes[0].image_path == "checklist.png"
    assert "expect from the following chapter" in collapsed[1][1].content_text
    assert collapsed[2][1].content_text.startswith("Explanation")
    assert collapsed[3][1].content_text.endswith("important")
    assert len(collapsed[3][0].media_nodes) == 1


def test_collapse_leaves_dense_two_column_table():
    rows = [
        [_cell("Term"), _cell("Meaning")],
        [_cell("SOP"), _cell("Standard Operating Procedure")],
        [_cell("GxP"), _cell("Good Practice regulations")],
    ]
    collapsed = collapse_sparse_grid(rows)
    assert len(collapsed) == 3
    assert len(collapsed[0]) == 2
    assert collapsed[1][0].content_text == "SOP"
    assert collapsed[2][1].content_text.startswith("Good Practice")


def test_merge_page_break_continuation_into_role_row():
    rows = [
        [_cell("Role"), _cell("Responsibility")],
        [_cell("Change Owner", media=[_img("person.png")]), _cell("Initiate the change")],
        [_cell(), _cell("Sign for correctness and completeness of Change Plan")],
        [_cell("Assessor(s)"), _cell("Perform the impact assessment")],
    ]
    collapsed = collapse_sparse_grid(rows)
    assert len(collapsed) == 3
    assert collapsed[1][0].content_text == "Change Owner"
    assert "Initiate the change" in collapsed[1][1].content_text
    assert "Sign for correctness" in collapsed[1][1].content_text
    assert collapsed[2][0].content_text == "Assessor(s)"


def test_does_not_merge_empty_key_into_header():
    rows = [
        [_cell("Role"), _cell("Responsibility")],
        [_cell(), _cell("Initiate Amendments")],
        [_cell("Action Owner(s)"), _cell("Complete the required action")],
    ]
    collapsed = collapse_sparse_grid(rows)
    assert len(collapsed) == 3
    assert collapsed[0][0].content_text == "Role"
    assert collapsed[1][1].content_text == "Initiate Amendments"


def test_shaded_callout_vs_real_table():
    from app.services.extraction.tables import is_shaded_callout, callout_rows_to_elements

    process = [
        [_cell(media=[_img("checklist.png")]), _cell("1. Start a Change Control process when the")],
        [_cell(), _cell("decision that a change control is required has been taken.")],
        [_cell(), _cell("2. Three different processes are defined.")],
    ]
    assert is_shaded_callout(process)
    elements = callout_rows_to_elements(process, page=11, bbox=None)
    texts = [el.content for el in elements if getattr(el, "content", "")]
    assert any("Start a Change Control" in t for t in texts)
    assert any("Three different processes" in t for t in texts)
    assert not any(getattr(el, "element_type", None) and el.element_type == "table" for el in elements)

    note = [[_cell("This section describes the regular Change Control process. Use this")]]
    assert is_shaded_callout(note)

    roles = [
        [_cell("Role"), _cell("Responsibility")],
        [_cell("Change Owner"), _cell("Initiate the change")],
    ]
    assert not is_shaded_callout(roles)

    infographic = [
        [_cell("Infographics"), _cell("Description")],
        [_cell(media=[_img("a.png")]), _cell("Explanation")],
    ]
    assert not is_shaded_callout(infographic)
