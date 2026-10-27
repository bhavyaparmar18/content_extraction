"""The template's own body text: section headings, retained labels, callout labels, table headers, boilerplate.

``harvest_hook`` is a renderer ``body_hook``. It runs once the slots are filled and the instructions removed,
before the slot controls are unwrapped and the table of contents is rebuilt, and collects every paragraph that was
not built from the drafts. The cover page (replaced by a language template, or kept in English), the table of
contents' entries (rebuilt from the translated headings) and paragraphs without a letter are left out.
``apply_hook`` (T6) writes the translations at the same point of the same render, so the block paths match.

A paragraph's text is encoded with tags so its formatting survives translation:
- runs are grouped by formatting (``w:lang``, ``w:noProof`` and revision ids ignored); the group with the most
  characters is plain, every other group is tagged ``⟦k⟧…⟦/k⟧`` (one ``k`` per formatting);
- anything else in the line (a tab, a break, a field, a drawing, a hyperlink, an inline control) is a standalone
  ``⟦k⟧`` that the translation keeps in place.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from docx.oxml.ns import qn
from lxml import etree

from app.services.migration_v2.render.toc import _field_paragraphs, _toc_start
from app.services.migration_v2.render.xml import W_P, W_PPR, W_R, W_RPR, add_runs, ancestor, w_el

from .front_matter import FrontMatterError, find_cover
from .segments import block_path, find_block

TAG = re.compile(r"⟦(/?)(\d+)⟧")
_LETTER = re.compile(r"[^\W\d_]")

_W_T = qn("w:t")
_FLD_CHAR = qn("w:fldChar")
# Run children that are objects of their own (kept in place, never translated).
_RUN_OBJECTS = {qn(f"w:{t}") for t in ("tab", "br", "cr", "noBreakHyphen", "softHyphen", "sym", "drawing", "pict",
                                       "object", "footnoteReference", "endnoteReference", "ptab", "ruby")}
_RUN_OBJECTS.add("{http://schemas.openxmlformats.org/markup-compatibility/2006}AlternateContent")
# Paragraph children kept whole: their text is a link, a field result or a control's value.
_WHOLE = {qn(f"w:{t}") for t in ("hyperlink", "fldSimple", "sdt", "object")}
_WHOLE.add("{http://schemas.openxmlformats.org/officeDocument/2006/math}oMath")
_DESCEND = {qn(f"w:{t}") for t in ("ins", "smartTag", "customXml", "moveTo", "dir", "bdo")}
_IGNORED_RPR = {qn("w:lang"), qn("w:noProof")}


@dataclass
class TextPiece:
    text: str
    key: bytes
    rpr: Optional[object]


@dataclass
class ObjectPiece:
    elements: list            # run children (``whole`` False) or runs / paragraph children kept as they are
    whole: bool
    rpr: Optional[object] = None
    k: int = 0


@dataclass
class Encoded:
    """A paragraph's text with its formatting tags, and what each tag stands for (T6 rebuilds the runs from it)."""

    tagged: str
    text: str                                   # the plain text (objects left out)
    base_rpr: Optional[object] = None           # the untagged formatting
    groups: dict[int, Optional[object]] = field(default_factory=dict)  # k → rPr of a tagged text group
    objects: dict[int, ObjectPiece] = field(default_factory=dict)      # k → standalone object
    pieces: list = field(default_factory=list)


def rpr_key(rpr) -> bytes:
    """A run's formatting, without the language, proofing and revision-id noise."""
    if rpr is None:
        return b""
    clean = copy.deepcopy(rpr)
    for child in list(clean):
        if child.tag in _IGNORED_RPR or child.tag == qn("w:rPrChange"):
            clean.remove(child)
    for node in clean.iter():
        for attr in [a for a in node.attrib if etree.QName(a).localname.startswith("rsid")]:
            del node.attrib[attr]
    return b"" if len(clean) == 0 else etree.tostring(clean)


def _pieces(p) -> list:
    pieces: list = []
    field_runs: list = []
    depth = 0

    def run(r) -> None:
        nonlocal depth, field_runs
        chars = r.findall(_FLD_CHAR)
        if depth or any(c.get(qn("w:fldCharType")) == "begin" for c in chars):
            field_runs.append(r)
            for c in chars:
                kind = c.get(qn("w:fldCharType"))
                depth += kind == "begin"
                depth -= kind == "end"
            if depth <= 0:
                depth = 0
                pieces.append(ObjectPiece(field_runs, whole=True))
                field_runs = []
            return
        rpr = r.find(W_RPR)
        for child in r:
            if child.tag == _W_T:
                if child.text:
                    pieces.append(TextPiece(child.text, rpr_key(rpr), rpr))
            elif child.tag in _RUN_OBJECTS:
                pieces.append(ObjectPiece([child], whole=False, rpr=rpr))

    def walk(node) -> None:
        for child in node:
            if child.tag == W_R:
                run(child)
            elif depth:  # a field spanning other paragraph content stays one object
                field_runs.append(child)
            elif child.tag in _WHOLE:
                pieces.append(ObjectPiece([child], whole=True))
            elif child.tag in _DESCEND:
                walk(child)

    walk(p)
    if field_runs:  # a field that does not end in this paragraph
        pieces.append(ObjectPiece(field_runs, whole=True))
    return pieces


def encode_paragraph(p) -> Encoded:
    pieces = _pieces(p)
    weight: dict[bytes, int] = {}
    rprs: dict[bytes, object] = {}
    for piece in pieces:
        if isinstance(piece, TextPiece):
            weight[piece.key] = weight.get(piece.key, 0) + len(piece.text.strip())
            rprs.setdefault(piece.key, piece.rpr)
    base = max(weight, key=lambda key: weight[key], default=b"")  # ties: the first formatting seen
    numbers: dict[bytes, int] = {}
    encoded = Encoded(tagged="", text="", base_rpr=rprs.get(base), pieces=pieces)
    out: list[str] = []
    open_key: Optional[bytes] = None
    k = 0

    def close() -> None:
        nonlocal open_key
        if open_key is not None:
            out.append(f"⟦/{numbers[open_key]}⟧")
            open_key = None

    for piece in pieces:
        if isinstance(piece, ObjectPiece):
            close()
            k += 1
            piece.k = k
            encoded.objects[k] = piece
            out.append(f"⟦{k}⟧")
            continue
        if piece.key != open_key and piece.text.strip():  # spaces never open a tag of their own
            close()
            if piece.key != base:
                if piece.key not in numbers:
                    k += 1
                    numbers[piece.key] = k
                    encoded.groups[k] = rprs[piece.key]
                out.append(f"⟦{numbers[piece.key]}⟧")
                open_key = piece.key
        out.append(piece.text)
    close()
    encoded.tagged = "".join(out)
    encoded.text = "".join(piece.text for piece in pieces if isinstance(piece, TextPiece))
    return encoded


def parse_tags(text: str) -> list[tuple[str, int]]:
    """The tags of *text* in order: ``("open", k)``, ``("close", k)`` or ``("object", k)``."""
    tags: list[tuple[str, int]] = []
    opened: list[int] = []
    for match in TAG.finditer(text or ""):
        k = int(match.group(2))
        if match.group(1):
            tags.append(("close", k))
            if k in opened:
                opened.remove(k)
        else:
            tags.append(("open", k))
            opened.append(k)
    closed = {k for kind, k in tags if kind == "close"}
    return [("object", k) if kind == "open" and k not in closed else (kind, k) for kind, k in tags]


def strip_tags(text: str) -> str:
    return TAG.sub("", text or "")


def has_letters(text: str) -> bool:
    return bool(_LETTER.search(text or ""))


def _excluded(body) -> set:
    """The cover page's and the table of contents' paragraphs."""
    out: set = set()
    try:
        cover = find_cover(body)
    except FrontMatterError:
        cover = None
    for block in (cover.blocks if cover else []):
        out.update(block.iter(W_P))
    start = _toc_start(body)
    first = ancestor(start, W_P) if start is not None else None
    if first is not None:
        out.update(_field_paragraphs(first))
    return out


def template_paragraphs(doc, generated: frozenset) -> list[tuple[object, Encoded]]:
    """Each body paragraph of the template's own text, in body order, with its encoding."""
    body = doc.element.body
    excluded = _excluded(body)
    out = []
    for p in body.iter(W_P):
        if p in generated or p in excluded:
            continue
        encoded = encode_paragraph(p)
        if has_letters(encoded.text):
            out.append((p, encoded))
    return out


def harvest_hook(collected: list) -> Callable[[object, frozenset], None]:
    """A renderer ``body_hook`` that appends (block path, tagged text) for each template paragraph to *collected*."""

    def hook(doc, generated: frozenset) -> None:
        body = doc.element.body
        collected.extend((block_path(p, body), encoded.tagged) for p, encoded in template_paragraphs(doc, generated))

    return hook


# ── Applying a translation (Phase T6) ─────────────────────────────────

_KEPT = {qn("w:bookmarkStart"), qn("w:bookmarkEnd")}


def decode_into(p, encoded: Encoded, target: str) -> bool:
    """Rebuild *p*'s runs from *target*, the translation of ``encoded.tagged``: text under ``⟦k⟧…⟦/k⟧`` takes that
    group's formatting (the innermost pair when they nest), other text the plain formatting, and each standalone
    ``⟦k⟧`` puts its object back. False, and *p* unchanged, when a marker is unknown or an object is lost or doubled.
    """
    objects: list[int] = []
    for kind, k in parse_tags(target):
        if kind == "object":
            if k not in encoded.objects:
                return False
            objects.append(k)
        elif k not in encoded.groups:
            return False
    if sorted(objects) != sorted(encoded.objects):
        return False

    moved = {el for piece in encoded.objects.values() for el in piece.elements}
    marks = [el for el in p.iter(*_KEPT) if el not in moved and not any(a in moved for a in el.iterancestors())]
    for child in list(p):
        if child.tag != W_PPR:
            p.remove(child)
    ppr = p.find(W_PPR)
    for mark in reversed([m for m in marks if m.tag == qn("w:bookmarkStart")]):
        ppr.addnext(mark) if ppr is not None else p.insert(0, mark)

    stack: list[int] = []

    def text(chunk: str) -> None:
        if chunk:
            add_runs(p, chunk, encoded.groups[stack[-1]] if stack else encoded.base_rpr)

    last = 0
    for match in TAG.finditer(target):
        text(target[last:match.start()])
        k = int(match.group(2))
        if match.group(1):
            if k in stack:
                stack.reverse()
                stack.remove(k)  # the innermost open pair of that number
                stack.reverse()
        elif k in encoded.objects:
            piece = encoded.objects[k]
            if piece.whole:
                for el in piece.elements:
                    p.append(el)
            else:
                r = w_el("r")
                if piece.rpr is not None:
                    r.append(copy.deepcopy(piece.rpr))
                for el in piece.elements:
                    r.append(el)
                p.append(r)
        else:
            stack.append(k)
        last = match.end()
    text(target[last:])
    for mark in marks:
        if mark.tag == qn("w:bookmarkEnd"):
            p.append(mark)
    return True


def apply_hook(segments: list, warnings: list[str], applied: list[str]) -> Callable[[object, frozenset], None]:
    """A renderer ``body_hook`` that writes each template-text segment's translation into its paragraph.

    Every paragraph is found (by block path, then checked against its English) before any is changed, so rebuilding
    a paragraph that holds a text box does not move the box's own paragraphs. A paragraph that is not where its
    segment says, or whose translation's markers do not fit, keeps its English (a warning names the segment).
    *applied* gets the ids of the segments written.
    """

    def hook(doc, generated: frozenset) -> None:
        body = doc.element.body
        found = []
        for segment in segments:
            target = segment.target_text
            if target is None or not strip_tags(target).strip():
                warnings.append(f"{segment.segment_id}: no translation; the template text is shown in English")
                continue
            p = find_block(body, segment.locator.block_path)
            encoded = encode_paragraph(p) if p is not None and p.tag == W_P and p not in generated else None
            if encoded is None or encoded.tagged != segment.source_text:
                warnings.append(f"{segment.segment_id}: template text not found at {segment.locator.block_path}; "
                                "kept in English")
                continue
            found.append((segment, p, encoded))
        for segment, p, encoded in found:
            if segment.target_text == segment.source_text or decode_into(p, encoded, segment.target_text):
                applied.append(segment.segment_id)
            else:
                warnings.append(f"{segment.segment_id}: the translation's markers do not fit the paragraph's "
                                "formatting; kept in English")

    return hook
