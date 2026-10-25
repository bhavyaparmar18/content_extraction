"""The English final document cut into segments (docs/translation/IMPLEMENTATION_PLAN.md, Phase T4).

A segment is one piece of English text and the place its translation goes back:
- ``claim``: a claim of a section draft (paragraph, bullet, step, caption, heading), ``{{ref:...}}`` tokens kept;
- ``table_cell``: a cell (or one paragraph of a multi-paragraph cell) of a source table row a claim cites;
- ``table_header``: a header cell, once per source table (it applies to every row unit of that table);
- ``xref``: a resolved cross-reference phrase, its new number kept as ``⟦1⟧``;
- ``template_text``: a paragraph of the template's own body text (``template_text.harvest_hook``).

Ids are given in document order: each template section in display order, each claim followed by its table header
(the first time the table appears), cells and cross-references; then the template text in body order.
Repeated strings stay separate segments here; the translator translates each distinct string once (T5).
"""

from __future__ import annotations

from typing import Iterable, Optional

from docx.oxml.ns import nsmap as DOCX_NAMESPACES
from lxml import etree

from app.schemas.v2 import (
    AssembledDocument,
    ClaimKind,
    ResolvedRef,
    SectionDraft,
    Segment,
    SegmentKind,
    SegmentLocator,
    SourceDocument,
    TemplateModel,
)

NUMBER_PLACEHOLDER = "⟦1⟧"

_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


# ── Paragraph locations ───────────────────────────────────────────────


def _step(node) -> str:
    qname = etree.QName(node)
    name = qname.localname if qname.namespace == _W_NS or not node.prefix else f"{node.prefix}:{qname.localname}"
    index = 0
    for sibling in node.itersiblings(preceding=True):
        index += sibling.tag == node.tag
    return f"{name}[{index}]"


def block_path(el, body) -> str:
    """*el*'s place under *body*: each step is a tag and its index among same-tag siblings,
    e.g. ``body/sdt[3]/sdtContent[0]/tbl[0]/tr[1]/tc[0]/p[0]`` (the WordprocessingML prefix is left out)."""
    steps = []
    node = el
    while node is not None and node is not body:
        steps.append(_step(node))
        node = node.getparent()
    if node is None:
        raise ValueError("the element is not under the body")
    return "/".join(["body", *reversed(steps)])


def find_block(body, path: str):
    """The element at *path* (``block_path``), or None when the body has no such place."""
    parts = path.split("/")
    if not parts or parts[0] != "body":
        return None
    nsmap = {**DOCX_NAMESPACES, **{k: v for k, v in body.nsmap.items() if k}}
    node = body
    for part in parts[1:]:
        name, _, rest = part.partition("[")
        try:
            index = int(rest.rstrip("]"))
        except ValueError:
            return None
        prefix, _, local = name.rpartition(":")
        namespace = nsmap.get(prefix) if prefix else _W_NS
        if namespace is None:
            return None
        tag = f"{{{namespace}}}{local}"
        matches = [child for child in node if child.tag == tag]
        if index >= len(matches):
            return None
        node = matches[index]
    return node


# ── Segments ──────────────────────────────────────────────────────────


def xref_source(ref: ResolvedRef) -> str:
    """The phrase with its new number replaced by ``⟦1⟧`` (plain when it shows no number)."""
    text = ref.text or ""
    if ref.number and ref.number_at is not None and text[ref.number_at:ref.number_at + len(ref.number)] == ref.number:
        return text[:ref.number_at] + NUMBER_PLACEHOLDER + text[ref.number_at + len(ref.number):]
    return text


def _ordered_slots(draft: SectionDraft, template: TemplateModel):
    section = next((s for s in template.sections if s.section_id == draft.target_section_id), None)
    order = {s.slot_id: s.display_order for s in section.slots} if section else {}
    return sorted(draft.slots, key=lambda s: (s.slot_id not in order, order.get(s.slot_id, 0)))


def build_segments(
    template: TemplateModel,
    drafts: Iterable[SectionDraft],
    source: SourceDocument,
    assembled: Optional[AssembledDocument],
    template_text: Iterable[tuple[str, str]] = (),
    accepted_gaps: Iterable[str] = (),
) -> list[Segment]:
    """Every segment of the final document rendered from *drafts* (accepted gap slots left out).

    *template_text* is what ``template_text.harvest_hook`` collected from the same render: (block path, text).
    """
    by_section = {d.target_section_id: d for d in drafts}
    units = {u.unit_id: u for u in source.iter_units()}
    refs: dict[str, list[tuple[int, ResolvedRef]]] = {}
    for i, ref in enumerate(assembled.refs if assembled else []):
        refs.setdefault(ref.claim_id, []).append((i, ref))
    skipped = set(accepted_gaps)

    out: list[Segment] = []

    def add(kind: SegmentKind, text: str, **locator) -> None:
        out.append(Segment(segment_id=f"SEG-{len(out) + 1:04d}", kind=kind, source_text=text,
                           locator=SegmentLocator(**locator)))

    seen_units: set[str] = set()
    seen_tables: set[str] = set()
    for section in sorted(template.sections, key=lambda s: s.display_order):
        draft = by_section.get(section.section_id)
        if draft is None:
            continue
        sid = section.section_id
        for slot in _ordered_slots(draft, template):
            if slot.slot_id in skipped:
                continue
            for claim in slot.claims:
                if claim.is_gap_marker or claim.kind == ClaimKind.FIGURE:
                    continue
                unit = units.get(claim.source_unit_ids[0]) if claim.source_unit_ids else None
                if claim.kind == ClaimKind.TABLE_ROW and unit is not None and unit.table_ref is not None:
                    table = unit.table_ref
                    if table.table_id not in seen_tables:
                        seen_tables.add(table.table_id)
                        for col, header in enumerate(table.header_cells):
                            if header.strip():
                                add(SegmentKind.TABLE_HEADER, header, section_id=sid, unit_id=unit.unit_id, col=col)
                    if unit.unit_id in seen_units:
                        continue
                    seen_units.add(unit.unit_id)
                    for cell in table.cells:
                        if len(cell.paragraphs) > 1:
                            for n, text in enumerate(cell.paragraphs):
                                if text.strip():
                                    add(SegmentKind.TABLE_CELL, text, section_id=sid, unit_id=unit.unit_id,
                                        row=table.row_index, col=cell.col, paragraph=n)
                        elif cell.text.strip():
                            add(SegmentKind.TABLE_CELL, cell.text, section_id=sid, unit_id=unit.unit_id,
                                row=table.row_index, col=cell.col)
                    continue
                if (claim.text or "").strip():  # a table row without its table renders as text
                    add(SegmentKind.CLAIM, claim.text, section_id=sid, slot_id=slot.slot_id, claim_id=claim.claim_id)
                for index, ref in refs.get(claim.claim_id, []):
                    if (ref.text or "").strip():
                        add(SegmentKind.XREF, xref_source(ref), section_id=sid, claim_id=claim.claim_id,
                            ref_index=index)

    for path, text in template_text:
        add(SegmentKind.TEMPLATE_TEXT, text, block_path=path)
    return out
