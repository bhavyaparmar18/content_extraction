"""Glossary files and term matching.

A glossary arrives as CSV or XLSX with one term per row. The header row names the columns:

    source_term | target_term | note | case_sensitive | do_not_translate

Common alternatives are accepted (``source``/``English``, ``target``/``translation``
or the language's name or code, ``notes``/``comment``, ``dnt``…). An XLSX file
may carry a "Style notes" sheet; its text goes to the translation prompt verbatim.
A file with any bad row is refused as a whole, with every problem listed by row.

Matching is deliberately simple and explainable:

- **In the English source** (which terms a passage uses): whole words, case-insensitive
  unless the entry is case-sensitive, any whitespace between words, and the plural
  of the last word (``deviation`` matches ``deviations``, ``facility`` ``facilities``).
  Longer terms win where terms overlap (``batch record`` over ``batch``).
- **In a translation** (was the target term used): Chinese and Japanese compare by
  substring. Latin-script languages and Greek compare whole words, ignoring case and
  accents, and allow a changed ending on the last word, since nouns inflect
  (``Abweichung``/``Abweichungen``, ``απόκλιση``/``αποκλίσεις``). Do-not-translate
  terms must appear exactly as written.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Iterable, Optional

from pydantic import ValidationError as PydanticValidationError

from app.schemas.v2.translation import Glossary, GlossaryEntry, LanguageCode
from app.services.translation.languages import get_language

COLUMNS = ("source_term", "target_term", "note", "case_sensitive", "do_not_translate")

_ALIASES = {
    "source_term": {"source_term", "source", "term", "english", "en", "english_term", "source_text", "en_term"},
    "target_term": {"target_term", "target", "translation", "translated_term", "target_text"},
    "note": {"note", "notes", "comment", "comments", "context", "definition", "remark", "remarks"},
    "case_sensitive": {"case_sensitive", "match_case", "case"},
    "do_not_translate": {"do_not_translate", "dnt", "keep", "untranslatable", "no_translation", "keep_as_is"},
}
_GLOSSARY_SHEETS = {"glossary", "terms", "termbase", "terminology"}
_STYLE_SHEETS = {"style_notes", "style", "style_guide", "notes_for_translators", "translator_notes"}

_TRUE = {"yes", "y", "true", "1", "x", "✓", "ja", "oui", "si", "sí", "sim"}
_FALSE = {"", "no", "n", "false", "0", "-", "nein", "non"}


class GlossaryInvalid(ValueError):
    """The file (or edit) cannot become a glossary; ``problems`` lists every reason."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(f"glossary is invalid ({len(problems)} problem(s)): " + "; ".join(problems[:5]))


@dataclass
class ParsedGlossary:
    entries: list[GlossaryEntry] = field(default_factory=list)
    style_notes: Optional[str] = None


# ── Reading files ─────────────────────────────────────────────────────


def _norm_header(value: str) -> str:
    return re.sub(r"[\s\-]+", "_", str(value or "").strip().casefold()).strip("_")


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _decode(data: bytes) -> str:
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16")  # Excel's "Unicode text" export
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252")


def _csv_rows(data: bytes) -> list[list[str]]:
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [[_cell(c) for c in row] for row in csv.reader(io.StringIO(text), dialect)]


def _xlsx_rows(data: bytes) -> tuple[list[list[str]], Optional[str]]:
    from openpyxl import load_workbook

    try:
        book = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        raise GlossaryInvalid([f"not a readable .xlsx file: {exc}"]) from exc
    try:
        sheets = {_norm_header(ws.title): ws for ws in book.worksheets}
        style = next((ws for name, ws in sheets.items() if name in _STYLE_SHEETS), None)
        terms = next((ws for name, ws in sheets.items() if name in _GLOSSARY_SHEETS), None)
        if terms is None:
            terms = next((ws for ws in book.worksheets if ws is not style), None)
        if terms is None:
            raise GlossaryInvalid(["the workbook has no sheet of terms"])
        rows = [[_cell(c) for c in row] for row in terms.iter_rows(values_only=True)]
        notes = None
        if style is not None:
            lines = [" ".join(_cell(c) for c in row if _cell(c)) for row in style.iter_rows(values_only=True)]
            notes = "\n".join(line for line in lines if line) or None
        return rows, notes
    finally:
        book.close()


def _header_map(header: list[str], language: LanguageCode) -> tuple[dict[str, int], list[str]]:
    lang = get_language(language)
    aliases = {k: set(v) for k, v in _ALIASES.items()}
    aliases["target_term"] |= {_norm_header(lang.name), _norm_header(lang.word_lang),
                               _norm_header(lang.word_lang.split("-")[0])}
    found: dict[str, int] = {}
    problems: list[str] = []
    for index, name in enumerate(_norm_header(h) for h in header):
        column = next((c for c, names in aliases.items() if name in names), None)
        if column is None:
            continue
        if column in found:
            problems.append(f"header: more than one {column} column")
        found[column] = index
    if "source_term" not in found:
        problems.append("header: no source_term column (also accepted: source, term, English)")
    if "target_term" not in found:
        problems.append(f"header: no target_term column (also accepted: target, translation, {lang.name})")
    return found, problems


def _flag(value: str, column: str, row: int, problems: list[str]) -> bool:
    v = value.strip().casefold()
    if v in _TRUE:
        return True
    if v not in _FALSE:
        problems.append(f"row {row}: {column} must be yes or no, not {value!r}")
    return False


def rows_to_entries(rows: list[list[str]], language: LanguageCode) -> list[GlossaryEntry]:
    """Turn a header row plus term rows into entries; ``GlossaryInvalid`` lists every bad row."""
    numbered = [(n, row) for n, row in enumerate(rows, start=1) if any(c.strip() for c in row)]
    if not numbered:
        raise GlossaryInvalid(["the file is empty"])
    (_, header), body = numbered[0], numbered[1:]
    columns, problems = _header_map(header, language)
    if problems:
        raise GlossaryInvalid(problems)

    def get(row: list[str], column: str) -> str:
        index = columns.get(column)
        return row[index] if index is not None and index < len(row) else ""

    entries: list[GlossaryEntry] = []
    seen: dict[str, int] = {}
    for number, row in body:
        values = {
            "source_term": get(row, "source_term"),
            "target_term": get(row, "target_term"),
            "note": get(row, "note") or None,
            "case_sensitive": _flag(get(row, "case_sensitive"), "case_sensitive", number, problems),
            "do_not_translate": _flag(get(row, "do_not_translate"), "do_not_translate", number, problems),
        }
        try:
            entry = GlossaryEntry(**values)
        except PydanticValidationError as exc:
            problems.extend(f"row {number}: {e['msg'].removeprefix('Value error, ')}" for e in exc.errors())
            continue
        if entry.key in seen:
            problems.append(f"row {number}: {entry.source_term!r} is already listed in row {seen[entry.key]}")
            continue
        seen[entry.key] = number
        entries.append(entry)
    if problems:
        raise GlossaryInvalid(problems)
    return entries


def parse_glossary_file(data: bytes, filename: str, language: LanguageCode) -> ParsedGlossary:
    """Read an uploaded ``.csv`` or ``.xlsx`` glossary for ``language``."""
    suffix = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if suffix == "xlsx":
        rows, notes = _xlsx_rows(data)
    elif suffix == "csv":
        rows, notes = _csv_rows(data), None
    else:
        raise GlossaryInvalid([f"unsupported glossary file type '.{suffix}' (use .csv or .xlsx)"])
    return ParsedGlossary(entries=rows_to_entries(rows, language), style_notes=notes)


# ── Writing files ─────────────────────────────────────────────────────


def _row(entry: GlossaryEntry) -> list[str]:
    return [entry.source_term, entry.target_term, entry.note or "",
            "yes" if entry.case_sensitive else "no", "yes" if entry.do_not_translate else "no"]


def to_csv(glossary: Glossary) -> str:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(COLUMNS)
    writer.writerows(_row(e) for e in glossary.entries)
    return out.getvalue()


def to_xlsx(glossary: Glossary) -> bytes:
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    sheet.title = "Glossary"
    sheet.append(list(COLUMNS))
    for entry in glossary.entries:
        sheet.append(_row(entry))
    if glossary.style_notes:
        notes = book.create_sheet("Style notes")
        for line in glossary.style_notes.splitlines():
            notes.append([line])
    out = io.BytesIO()
    book.save(out)
    return out.getvalue()


# ── Matching ──────────────────────────────────────────────────────────


@dataclass(frozen=True)
class TermMatch:
    entry: GlossaryEntry
    start: int
    end: int


def _plural(word: str) -> str:
    """A regex for ``word`` and its English plural."""
    escaped = re.escape(word)
    if not word[-1:].isalpha():
        return escaped
    if len(word) > 1 and word[-1] in "yY" and word[-2].lower() not in "aeiou":
        return f"(?:{escaped}|{re.escape(word[:-1])}(?:ies|IES))"
    return f"{escaped}(?:e?s|E?S)?"


def source_pattern(entry: GlossaryEntry) -> re.Pattern:
    words = entry.source_term.split()
    body = r"\s+".join([re.escape(w) for w in words[:-1]] + [_plural(words[-1])])
    return re.compile(rf"(?<!\w){body}(?!\w)", 0 if entry.case_sensitive else re.IGNORECASE)


def match_terms(text: str, entries: Iterable[GlossaryEntry]) -> list[TermMatch]:
    """Glossary terms in English ``text``, without overlaps (the longer term wins), in text order."""
    found = [TermMatch(entry, m.start(), m.end())
             for entry in entries for m in source_pattern(entry).finditer(text)]
    found.sort(key=lambda m: (m.start, -(m.end - m.start)))  # at one position the longest term comes first
    kept: list[TermMatch] = []
    for match in found:
        if not kept or match.start >= kept[-1].end:
            kept.append(match)
    return kept


def terms_in(text: str, entries: Iterable[GlossaryEntry]) -> list[GlossaryEntry]:
    """The distinct entries ``text`` uses, in order of first use (what a translation prompt needs)."""
    seen: dict[str, GlossaryEntry] = {}
    for match in match_terms(text, entries):
        seen.setdefault(match.entry.key, match.entry)
    return list(seen.values())


def _fold(text: str, *, case: bool = True, accents: bool = True) -> str:
    """NFKC, then optionally drop case and accents. Folding keeps the string's length per character
    only loosely; callers compare folded text with folded text."""
    text = unicodedata.normalize("NFKC", text)
    if case:
        text = text.casefold()
    if accents:
        text = "".join(c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c))
        text = unicodedata.normalize("NFC", text)
    return text


def _target_regex(term: str) -> str:
    """Whole words; the last word may change its ending (inflection): its last letter (two for words of
    seven letters or more) may differ, and a few letters may follow."""
    words = term.split()
    last = words[-1]
    if len(last) <= 4 or not last[-1:].isalpha():
        tail = re.escape(last) + (r"\w{0,2}" if last[-1:].isalpha() else "")
    else:
        tail = re.escape(last[:-2] if len(last) >= 7 else last[:-1]) + r"\w{0,4}"
    return r"\s+".join([re.escape(w) for w in words[:-1]] + [tail])


def target_present(translation: str, entry: GlossaryEntry, language: LanguageCode) -> bool:
    """Whether ``translation`` uses the entry's target term (see the module notes for the rules)."""
    if entry.do_not_translate:
        flags = 0 if entry.case_sensitive else re.IGNORECASE
        body = r"\s+".join(re.escape(w) for w in entry.target_term.split())
        return re.search(rf"(?<!\w){body}(?!\w)", unicodedata.normalize("NFKC", translation), flags) is not None
    if get_language(language).east_asian:
        squash = lambda s: re.sub(r"\s+", "", _fold(s, case=not entry.case_sensitive, accents=False))  # noqa: E731
        return squash(entry.target_term) in squash(translation)
    case = not entry.case_sensitive
    pattern = _target_regex(_fold(entry.target_term, case=case))
    return re.search(rf"(?<!\w){pattern}(?!\w)", _fold(translation, case=case)) is not None
