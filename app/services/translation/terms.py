"""The document's own terms: the English terms a job's segments use again and again.

They are translated once, before anything else (the translator's term wave), and every later call is given the
translations it uses, so a term reads the same in every section and table (``owning system`` is not three different
things in German). The checks then hold each segment to them (``TERM-<n>``). A glossary, when the job has one,
governs its own terms: a document term the glossary covers is left to the glossary.

A term is either
- a phrase of two to four words, none of them a function word ("of", "the", "must"), that appears in at least
  ``min_texts`` distinct texts; a phrase inside a longer one that covers most of its texts gives way to the longer
  one ("Subject Matter" to "Subject Matter Expert"), or
- the whole text of a short table cell, header or template label (two to four words) that appears in another text
  too ("Owning system", "Change Requester").

Phrases are found case-insensitively and with English plurals; each is shown as it is written most often. Names,
IDs and abbreviations alone (nothing to translate) are no terms.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Iterable, Optional

from app.schemas.v2 import Glossary, GlossaryEntry, Segment, SegmentKind
from app.schemas.v2.refs import REF_TOKEN_PATTERN

from .glossary import source_pattern, terms_in
from .template_text import TAG, has_letters

DEFAULT_MAX_TERMS = 80
DEFAULT_MIN_TEXTS = 3
MAX_WORDS = 4
COVERED = 0.75  # a phrase gives way to a longer one found in this share of its texts

_LABELS = (SegmentKind.TABLE_CELL, SegmentKind.TABLE_HEADER, SegmentKind.TEMPLATE_TEXT)
_BREAK = re.compile(r"[.,;:!?()\[\]{}\"“”„|/–—]|\s-\s")
_TOKEN = re.compile(r"[^\W_](?:[\w&'’-]*[^\W_])?")
_STOP = frozenset("""
a an the and or nor but of to in on at by for from with without within into onto over under as per via than then
that this these those it its they them their there here which who whom whose what when where why how if whether
is are was were be been being am has have had do does did must shall should may might can could will would not no
all any each every some such both either neither only also other another more most less least very so e.g i.e etc
according based using used one two three new same further following include includes including require requires
required
""".split())


def _plain(text: str) -> str:
    return REF_TOKEN_PATTERN.sub(" ", TAG.sub(" ", text or ""))


def _translatable(term: str) -> bool:
    """Something to translate: a word with a lower-case letter (not only names, IDs and abbreviations)."""
    return has_letters(term) and any(any(c.islower() for c in w) for w in _TOKEN.findall(term))


def _singular(word: str) -> str:
    """An English plural's singular ("systems", "entries"); abbreviations ("RPAS") and "process" stay."""
    if len(word) <= 3 or not any(c.islower() for c in word) or not word.endswith("s"):
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    return word if word.endswith(("ss", "us", "is")) else word[:-1]


def _phrases(text: str) -> set[tuple[str, ...]]:
    """The candidate phrases of one text, as lower-case word tuples (the last word singular)."""
    out: set[tuple[str, ...]] = set()
    for chunk in _BREAK.split(_plain(text)):
        words = _TOKEN.findall(chunk)
        for n in range(2, MAX_WORDS + 1):
            for i in range(len(words) - n + 1):
                gram = tuple(w.casefold() for w in words[i:i + n - 1]) + (_singular(words[i + n - 1]).casefold(),)
                if any(w in _STOP or not has_letters(w) for w in gram):
                    continue
                out.add(gram)
    return out


def _label(segment: Segment) -> Optional[str]:
    """A short label's text ("Owning system"), or None."""
    if segment.kind not in _LABELS:
        return None
    text = " ".join(_plain(segment.source_text).split())
    words = _TOKEN.findall(text)
    if not 2 <= len(words) <= MAX_WORDS or _BREAK.search(text):
        return None
    if words[0].casefold() in _STOP or words[-1].casefold() in _STOP:
        return None
    return text


def _contains(longer: tuple[str, ...], shorter: tuple[str, ...]) -> bool:
    n = len(shorter)
    return len(longer) > n and any(longer[i:i + n] == shorter for i in range(len(longer) - n + 1))


def find_terms(segments: Iterable[Segment], glossary: Optional[Glossary] = None,
               max_terms: int = DEFAULT_MAX_TERMS, min_texts: int = DEFAULT_MIN_TEXTS) -> list[str]:
    """The document's terms (see the module notes), the most used first, at most *max_terms*."""
    segments = list(segments)
    texts = list(dict.fromkeys(s.source_text for s in segments))
    found: dict[tuple[str, ...], set[int]] = defaultdict(set)
    for i, text in enumerate(texts):
        for gram in _phrases(text):
            found[gram].add(i)
    phrases = {g: ids for g, ids in found.items() if len(ids) >= min_texts}
    phrases = {g: ids for g, ids in phrases.items()
               if not any(_contains(h, g) and len(ids & other) >= COVERED * len(ids) for h, other in phrases.items())}

    candidates: dict[str, int] = {}  # casefolded term → number of texts
    for gram, ids in phrases.items():
        candidates[" ".join(gram)] = len(ids)
    plain = [_plain(t) for t in texts]
    for segment in segments:
        label = _label(segment)
        if label is None:
            continue
        words = _TOKEN.findall(label)
        key = " ".join([w.casefold() for w in words[:-1]] + [_singular(words[-1]).casefold()])
        if key in candidates:
            continue
        pattern = source_pattern(GlossaryEntry(source_term=key, target_term=key))
        uses = sum(1 for t in plain if pattern.search(t))
        if uses >= 2:
            candidates[key] = uses

    spelled = _spellings(candidates, plain)
    covered = glossary.entries if glossary is not None else []
    terms = [t for t in candidates if _translatable(spelled[t]) and not terms_in(spelled[t], covered)]
    terms.sort(key=lambda t: (-candidates[t], -len(t.split()), t))
    return [spelled[t] for t in terms[:max_terms]]


def _spellings(candidates: dict[str, int], texts: list[str]) -> dict[str, str]:
    """Each term as it is written most often (``CSV&C Function``, ``owning system``)."""
    out: dict[str, str] = {}
    for term in candidates:
        pattern = source_pattern(GlossaryEntry(source_term=term, target_term=term))
        seen = Counter(" ".join(m.group(0).split()) for t in texts for m in pattern.finditer(t))
        singular = [s for s in seen if s.casefold() == term]
        out[term] = max(singular or seen or [term], key=lambda s: (seen.get(s, 0), s))
    return out
