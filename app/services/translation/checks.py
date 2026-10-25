"""Deterministic QA checks of a translation (Phase T5), as ``ValidationIssue``s in a ``QualityReport``.

Per segment (issue id ``TQ-<segment>-<code>``, so a reviewer's resolution carries over to the next round):

- CRITICAL: ``EMPTY`` (no translation), ``REF_TOKENS`` (a ``{{ref:...}}`` token lost, added or changed), ``TAGS``
  (the ``⟦k⟧`` markers differ from the source's, or pairs are unbalanced or cross; their order may change),
  ``CELLS`` (an English text with ``|`` cell separators, e.g. an edited table row, has a different number of them);
- CRITICAL with the ``NUMERICAL_CHANGE`` gate: ``NUMBERS`` (a number of the source is missing) and ``REFERENCES``
  (a document ID, e-mail address or URL of the source is missing);
- HIGH, only with a glossary: ``GLOSSARY-<n>`` (a term the source uses is not translated with its target term) and
  ``DNT-<n>`` (a do-not-translate term was altered); ``n`` is the entry's place in the glossary;
- MEDIUM, with the job's document terms (``glossary[terms]``, see ``terms.py``): ``TERM-<n>`` (the source uses a
  document term the translation does not render as agreed, loosely matched by ``glossary.term_present``; a term
  the translation keeps in English, such as a document title, passes); ``n`` is the term's place in the list;
- MEDIUM: ``UNTRANSLATED`` (identical to the English: wording of two words or more; LOW for one word or only
  capitalized words, such as a person's name and unit; abbreviations do not count), ``SCRIPT`` (Chinese, Japanese, Greek: mostly Latin letters once the English's own names, acronyms and
  do-not-translate terms are left out), ``LINE_BREAKS``;
- LOW: ``LENGTH`` (character ratio outside the language's bounds), ``NUMBERS_ADDED`` (a number the source does not
  show, e.g. "two" written as "2").

Numbers are compared language-neutrally: every run of digits counts (not one inside a name such as E2E, which a
translation may write out), a separator followed by exactly three digits
is a thousands separator (``1,000`` = ``1.000`` = ``1 000``) and any other separator splits the number (``1.5`` and
``1,5`` both give 1 and 5), so dates and decimals written the target language's way still match. ``extract_values``
is used only for its language-neutral kind, references; its other normalized forms carry English words.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from typing import Any, Iterable, Optional

from app.schemas.v2 import (
    FactKind,
    Gate,
    Glossary,
    GlossaryEntry,
    IssueCategory,
    LanguageCode,
    QualityReport,
    Segment,
    SegmentOrigin,
    Severity,
    ValidationIssue,
)
from app.schemas.v2.refs import REF_TOKEN_PATTERN, make_ref_token
from app.services.migration_v2.drafting.refs import tokens_of
from app.services.migration_v2.quality.facts import extract_values
from app.services.migration_v2.quality.gates import carry_resolutions, gate_counts

from .glossary import match_terms, target_present, term_present, terms_in
from .languages import get_language
from .template_text import TAG, has_letters, parse_tags, strip_tags

_RANK = {Severity.INFO: 0, Severity.LOW: 1, Severity.MEDIUM: 2, Severity.HIGH: 3, Severity.CRITICAL: 4}
_NUMBER = re.compile(r"(?<![^\W\d_])\d+(?:[.,'’ ]\d{3}(?!\d))*")  # not a digit inside a name (E2E, S4HANA)
_THOUSANDS = re.compile(r"[.,'’ ]")
_WORD = re.compile(r"[^\W\d_]+")
_LATIN = re.compile(f"[A-Za-z{chr(0xC0)}-{chr(0x24F)}]")  # Basic Latin to Latin Extended-B
_NON_LATIN_SCRIPTS = ("han", "japanese", "greek")
# CJK punctuation, kana, CJK ideographs (with extension A and compatibility forms), half- and full-width forms
_CJK = "".join(f"{chr(a)}-{chr(b)}" for a, b in ((0x3000, 0x30FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF),
                                                  (0xF900, 0xFAFF), (0xFF00, 0xFFEF)))
_CJK_BEFORE = re.compile(rf"([{_CJK}])([A-Za-z0-9])")
_CJK_AFTER = re.compile(rf"([A-Za-z0-9])([{_CJK}])")
_NAME = re.compile(r"\w*(?:[A-Z]\w*[A-Z]|\d)\w*|\w+[A-Z]\w*")  # GBS, unITed, BPML, E2E: names kept as written
DEFAULT_LENGTH_MIN_CHARS = 20


# ── Text properties ───────────────────────────────────────────────────


def _spaced(text: str) -> str:
    """NFKC, with a space where Chinese or Japanese meets Latin letters or digits ("RD01で"), so the
    word-boundary patterns of ``extract_values`` find IDs inside East Asian text."""
    text = unicodedata.normalize("NFKC", text or "")
    text = _CJK_BEFORE.sub(r"\1 \2", text)
    return _CJK_AFTER.sub(r"\1 \2", text)


def references(text: str) -> set[str]:
    """Document IDs, e-mail addresses and URLs in *text*, normalized."""
    return {v.normalized for v in extract_values(_spaced(strip_tags(text))) if v.kind == FactKind.REFERENCE}


def _bare(text: str, references: bool = True) -> str:
    """*text* without markers, reference tokens and (unless *references* is False) protected references,
    NFKC-normalized."""
    text = _spaced(TAG.sub(" ", text or ""))
    text = REF_TOKEN_PATTERN.sub(" ", text)
    if references:
        for value in extract_values(text):
            if value.kind == FactKind.REFERENCE:
                text = text.replace(value.raw, " ")
    return text


def neutral_numbers(text: str) -> Counter:
    """The numbers of *text*, language-neutral (see the module notes). The digits of IDs count too: an ID is not
    always recognised on both sides (the English may lack a space a translation adds)."""
    out: Counter = Counter()
    for match in _NUMBER.finditer(_bare(text, references=False)):
        digits = _THOUSANDS.sub("", match.group(0))
        out[digits.lstrip("0") or "0"] += 1
    return out


def words(text: str) -> list[str]:
    return _WORD.findall(_bare(text))


def copy_only(text: str, glossary: Optional[Glossary] = None) -> bool:
    """Nothing to translate: no letters once markers, tokens, references and do-not-translate terms are removed."""
    rest = _bare(text)
    if glossary is not None:
        keep = [e for e in glossary.entries if e.do_not_translate]
        for match in reversed(match_terms(rest, keep)):
            rest = rest[:match.start] + " " + rest[match.end:]
    return not has_letters(rest)


def tag_problems(source: str, target: str) -> list[str]:
    """How the markers of *target* differ from *source*'s: missing, extra, unbalanced or crossing pairs."""
    want, tags = Counter(parse_tags(source)), parse_tags(target)
    got = Counter(tags)
    show = {"open": "⟦{}⟧", "close": "⟦/{}⟧", "object": "⟦{}⟧"}
    problems = []
    missing = [show[kind].format(k) for (kind, k), n in sorted((want - got).items()) for _ in range(n)]
    extra = [show[kind].format(k) for (kind, k), n in sorted((got - want).items()) for _ in range(n)]
    if missing:
        problems.append(f"lost the marker(s) {' '.join(missing)}")
    if extra:
        problems.append(f"added or changed the marker(s) {' '.join(extra)}")
    stack: list[int] = []
    for kind, k in tags:
        if kind == "open":
            stack.append(k)
        elif kind == "close":
            if not stack or stack[-1] != k:
                problems.append(f"the pair ⟦{k}⟧…⟦/{k}⟧ is out of order or crosses another pair")
                break
            stack.pop()
    return problems


def _latin_share(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    return sum(bool(_LATIN.match(c)) for c in letters) / len(letters) if letters else 0.0


# ── Per-segment checks ────────────────────────────────────────────────


def _setting(settings: Any, name: str, default):
    return getattr(settings, name, default) if settings is not None else default


def check_segment(segment: Segment, language: LanguageCode | str, glossary: Optional[Glossary] = None,
                  settings: Any = None, terms: Optional[list[GlossaryEntry]] = None) -> list[ValidationIssue]:
    """The issues of one translated segment (none for a copied one); *terms* are the job's document terms."""
    if segment.origin == SegmentOrigin.COPIED:
        return []
    lang = get_language(language)
    source, target = segment.source_text, segment.target_text
    loc = segment.locator
    issues: list[ValidationIssue] = []

    def add(code: str, severity: Severity, category: IssueCategory, message: str, gate: Optional[Gate] = None):
        issues.append(ValidationIssue(
            issue_id=f"TQ-{segment.segment_id}-{code}", severity=severity, category=category, gate=gate,
            target_section_id=loc.section_id, slot_id=loc.slot_id, claim_ids=[loc.claim_id] if loc.claim_id else [],
            unit_ids=[loc.unit_id] if loc.unit_id else [], segment_ids=[segment.segment_id],
            message=f"{segment.segment_id}: {message}",
        ))

    if target is None or not strip_tags(target).strip():
        add("EMPTY", Severity.CRITICAL, IssueCategory.STRUCTURE, "no translation")
        return issues

    if Counter(tokens_of(source)) != Counter(tokens_of(target)):
        lost = [make_ref_token(t) for t in (Counter(tokens_of(source)) - Counter(tokens_of(target))).elements()]
        added = [make_ref_token(t) for t in (Counter(tokens_of(target)) - Counter(tokens_of(source))).elements()]
        detail = "; ".join(p for p in (f"lost {' '.join(lost)}" if lost else "",
                                       f"added {' '.join(added)}" if added else "") if p)
        add("REF_TOKENS", Severity.CRITICAL, IssueCategory.CROSS_REFERENCE, f"reference tokens changed: {detail}")
    tags = tag_problems(source, target)
    if tags:
        add("TAGS", Severity.CRITICAL, IssueCategory.FORMATTING, "; ".join(tags))
    if "|" in source and source.count("|") != target.count("|"):
        add("CELLS", Severity.CRITICAL, IssueCategory.STRUCTURE,
            f"{source.count('|')} table cell separator(s) '|' in the English, {target.count('|')} in the translation")

    lost_refs = sorted(references(source) - references(target))
    if lost_refs:
        add("REFERENCES", Severity.CRITICAL, IssueCategory.PRESERVATION,
            f"missing ID, e-mail or URL {', '.join(lost_refs)}", Gate.NUMERICAL_CHANGE)
    want, got = neutral_numbers(source), neutral_numbers(target)
    if want - got:
        add("NUMBERS", Severity.CRITICAL, IssueCategory.PRESERVATION,
            f"missing number(s) {', '.join(sorted((want - got).elements()))}", Gate.NUMERICAL_CHANGE)
    if got - want:
        add("NUMBERS_ADDED", Severity.LOW, IssueCategory.PRESERVATION,
            f"number(s) the English does not show: {', '.join(sorted((got - want).elements()))}")

    if glossary is not None:
        position = {e.key: n for n, e in enumerate(glossary.entries, start=1)}
        for entry in terms_in(strip_tags(source), glossary.entries):
            if target_present(strip_tags(target), entry, lang.code):
                continue
            if entry.do_not_translate:
                add(f"DNT-{position[entry.key]}", Severity.HIGH, IssueCategory.TERMINOLOGY,
                    f"do-not-translate term \"{entry.source_term}\" was altered")
            else:
                add(f"GLOSSARY-{position[entry.key]}", Severity.HIGH, IssueCategory.TERMINOLOGY,
                    f"glossary: \"{entry.source_term}\" must be translated as \"{entry.target_term}\"")

    if terms:
        position = {e.key: n for n, e in enumerate(terms, start=1)}
        translated = strip_tags(target)
        for entry in terms_in(strip_tags(source), terms):
            if term_present(translated, entry.target_term, lang.code) or term_present(
                    translated, entry.source_term, lang.code):
                continue
            add(f"TERM-{position[entry.key]}", Severity.MEDIUM, IssueCategory.TERMINOLOGY,
                f"document term \"{entry.source_term}\" is translated as \"{entry.target_term}\" in this document")

    plain = [w for w in words(source) if any(c.islower() for c in w)]  # abbreviations stay as they are
    if target.strip() == source.strip() and plain and not copy_only(source, glossary):
        # MEDIUM (repaired) for wording; LOW for one word or only capitalized words (names, a person and a unit)
        wording = len(plain) >= 2 and any(w.islower() for w in plain)
        severity = Severity.MEDIUM if wording else Severity.LOW
        add("UNTRANSLATED", severity, IssueCategory.LANGUAGE, "the text is still in English")
    elif lang.script in _NON_LATIN_SCRIPTS and len(plain) >= 3:
        rest = _bare(target)
        keep = [e.target_term for e in (glossary.entries if glossary else [])
                if e.do_not_translate or _latin_share(e.target_term) > 0.5]
        keep += [w for w in _NAME.findall(_bare(source)) if _LATIN.search(w)]  # the English's own names
        for term in sorted(set(keep), key=len, reverse=True):
            rest = re.sub(rf"(?<![^\W\d_]){re.escape(term)}(?![^\W\d_])", " ", rest, flags=re.IGNORECASE)
        if _latin_share(rest) > 0.5:
            add("SCRIPT", Severity.MEDIUM, IssueCategory.LANGUAGE, f"mostly Latin letters, not {lang.name}")

    if source.count("\n") != target.count("\n"):
        add("LINE_BREAKS", Severity.MEDIUM, IssueCategory.FORMATTING,
            f"{source.count(chr(10))} line break(s) in the English, {target.count(chr(10))} in the translation")

    plain_source, plain_target = strip_tags(source).strip(), strip_tags(target).strip()
    bounds = _setting(settings, "translation_length_bounds", {}).get(lang.code.value)
    if bounds and len(plain_source) >= _setting(settings, "translation_length_min_chars", DEFAULT_LENGTH_MIN_CHARS):
        ratio = len(plain_target) / len(plain_source)
        low, high = bounds
        if not low <= ratio <= high:
            add("LENGTH", Severity.LOW, IssueCategory.LANGUAGE,
                f"the translation is {ratio:.2f}× the English length (expected {low}–{high})")
    return issues


# ── The report ────────────────────────────────────────────────────────


def rank(severity: Severity) -> int:
    return _RANK[severity]


def worst(issues: Iterable[ValidationIssue]) -> int:
    """The rank of the most severe open issue (-1 when there is none)."""
    return max((rank(i.severity) for i in issues if not i.resolved), default=-1)


def needs_repair(issue: ValidationIssue) -> bool:
    return not issue.resolved and rank(issue.severity) >= rank(Severity.MEDIUM)


def repair_candidates(segments: Iterable[Segment], report: QualityReport) -> list[str]:
    """Segments with an open MEDIUM-or-worse issue that have not had their one retranslation (LLM or untranslated)."""
    flagged = {s for issue in report.issues if needs_repair(issue) for s in issue.segment_ids}
    return [s.segment_id for s in segments
            if s.segment_id in flagged and s.origin in (None, SegmentOrigin.LLM)]


def check_translations(job_id: str, version: int, segments: list[Segment], language: LanguageCode | str,
                       glossary: Optional[Glossary] = None, settings: Any = None,
                       previous: Optional[QualityReport] = None,
                       terms: Optional[list[GlossaryEntry]] = None) -> QualityReport:
    """Every segment's checks in one report; resolutions of the previous round's issues carry over."""
    issues = carry_resolutions([i for s in segments for i in check_segment(s, language, glossary, settings, terms)],
                               previous)
    total = len(segments) or 1
    done = [s for s in segments if s.target_text is not None]
    copied = sum(s.origin == SegmentOrigin.COPIED for s in segments)
    return QualityReport(
        job_id=job_id, version=version, issues=issues, unit_coverage=round(len(done) / total, 4),
        gate_counts=gate_counts(issues),
        soft_scores={"translated": round((len(done) - copied) / total, 4), "copied": round(copied / total, 4),
                     "repaired": round(sum(s.origin == SegmentOrigin.REPAIR for s in segments) / total, 4)},
    )
