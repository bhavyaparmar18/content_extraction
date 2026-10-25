"""The translator (Phase T5): the job's segments → one ``TranslationSet`` per scope.

- **Once per distinct text.** Segments with the same ``source_text`` (markers included) form a group, keyed by its
  first segment's id; the answer goes to every segment of the group. A text with nothing to translate (no letters
  once markers, tokens, references and do-not-translate terms are removed) is copied (``origin=copied``).
- **Two waves.** The template's own text, the table headers and the cross-reference phrases go first; their short
  translations (six words or fewer, no markers) become the bounded "already translated in this document" memory of
  the second wave, the section texts, so headings, labels and the body name things the same way. Like the
  glossary, the memory sends a call only the entries its texts use.
- **Blocks.** Groups are packed per scope with ``planning/budget.pack`` and translated concurrently. One attempt
  per block, plus one more call for what it did not translate (the segments the answer left out, or a failed
  call's segments as two halves): a segment still without an answer stays untranslated for CHECKING and REPAIRING. Markers an answer adds that its English does not have are
  dropped (they carry no text); anything else wrong is left to the checks.
- **Repair.** The same prompt with a ``REPAIR:`` section: the previous translation and the problems found.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger
from pydantic import BaseModel, Field

from app.schemas.v2 import (
    ClaimKind,
    Glossary,
    GlossaryEntry,
    LanguageCode,
    SectionDraft,
    Segment,
    SegmentKind,
    SegmentOrigin,
    SegmentSet,
    TranslationJob,
    TranslationSet,
)
from app.schemas.v2.translation import SCOPE_TEMPLATE, SCOPE_XREFS
from app.services.llm.prompts.v2.translator import (
    GLOSSARY_SECTION,
    MEMORY_SECTION,
    PROMPT_VERSION,
    REPAIR_HEADING,
    STYLE_SECTION,
    SYSTEM_PROMPT,
    USER_PROMPT,
)
from app.services.migration_v2.drafting.drafter import _call
from app.services.migration_v2.planning.budget import Block, Line, SectionLines, estimate_tokens, pack

from .glossary import terms_in
from .languages import get_language
from .template_text import TAG, has_letters

LINE_BREAK = "⏎"
DEFAULT_BLOCK_TOKENS = 1500
DEFAULT_MEMORY_TOKENS = 600
MEMORY_MAX_WORDS = 6
_FIRST_WAVE = (SegmentKind.TEMPLATE_TEXT, SegmentKind.TABLE_HEADER, SegmentKind.XREF)
_ROLES = {
    SegmentKind.TABLE_CELL: "table cell", SegmentKind.TABLE_HEADER: "table header",
    SegmentKind.XREF: "cross-reference phrase", SegmentKind.TEMPLATE_TEXT: "template text",
}
_CLAIM_ROLES = {ClaimKind.STEP: "numbered step", ClaimKind.BULLET: "bullet", ClaimKind.HEADING: "heading",
                ClaimKind.CAPTION: "caption", ClaimKind.TABLE_ROW: "table row"}


# ── LLM output schema ─────────────────────────────────────────────────


class TranslatedSegment(BaseModel):
    segment_id: str = Field(description="The segment ID as given, e.g. 'SEG-0042'")
    translation: str


class TranslatorOutput(BaseModel):
    translations: list[TranslatedSegment] = Field(default_factory=list)


# ── Groups ────────────────────────────────────────────────────────────


@dataclass
class Group:
    """One distinct English text and the segments that show it."""

    key: str                      # the first segment's id; the id the prompt uses
    source_text: str
    segment_ids: list[str]
    scope: str
    kind: SegmentKind
    role: str
    context: Optional[str] = None  # a cross-reference phrase: the English claim it is inserted into

    @property
    def wave(self) -> int:
        return 1 if self.kind in _FIRST_WAVE else 2


def _role(segment: Segment, claims: dict) -> str:
    if segment.kind != SegmentKind.CLAIM:
        return _ROLES[segment.kind]
    claim = claims.get(segment.locator.claim_id)
    return _CLAIM_ROLES.get(claim.kind, "paragraph") if claim is not None else "paragraph"


def group_segments(segments: Iterable[Segment], drafts: Iterable[SectionDraft] = ()) -> list[Group]:
    """The distinct texts in order of first appearance; each belongs to the scope it first appears in."""
    claims = {c.claim_id: c for d in drafts for c in d.iter_claims()}
    groups: dict[str, Group] = {}
    for segment in segments:
        group = groups.get(segment.source_text)
        if group is not None:
            group.segment_ids.append(segment.segment_id)
            continue
        claim = claims.get(segment.locator.claim_id) if segment.kind == SegmentKind.XREF else None
        groups[segment.source_text] = Group(segment.segment_id, segment.source_text, [segment.segment_id],
                                            segment.scope, segment.kind, _role(segment, claims),
                                            claim.text if claim is not None else None)
    return list(groups.values())


def memory_entries(pairs: Iterable[tuple[str, str]]) -> list[GlossaryEntry]:
    """Short translated texts as "already translated" entries: no markers, tokens or line breaks, six words at most."""
    out: dict[str, GlossaryEntry] = {}
    for source, target in pairs:
        source, target = " ".join(source.split()), " ".join((target or "").split())
        if (not target or TAG.search(source) or TAG.search(target) or "{{" in source or not has_letters(source)
                or len(source.split()) > MEMORY_MAX_WORDS or source == target):
            continue
        entry = GlossaryEntry(source_term=source, target_term=target)
        out.setdefault(entry.key, entry)
    return list(out.values())


def _show(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\n", LINE_BREAK)


def _own_markers(answer: str, source: str) -> str:
    """The answer without the markers its English does not have (they carry no text; models add them)."""
    own = {int(m.group(2)) for m in TAG.finditer(source)}
    return TAG.sub(lambda m: m.group(0) if int(m.group(2)) in own else "", answer)


def _restore(answer: str, source: str) -> str:
    """The answer with line breaks back, foreign markers dropped and the source's leading and trailing spaces."""
    text = _own_markers(answer, source)
    text = re.sub(r"[ \t]{2,}", " ", text) if text != answer else text
    text = text.replace(f" {LINE_BREAK} ", "\n").replace(LINE_BREAK, "\n").strip()
    lead = source[: len(source) - len(source.lstrip())]
    trail = source[len(source.rstrip()):]
    return f"{lead}{text}{trail}"


def _entry_line(entry: GlossaryEntry) -> str:
    if entry.do_not_translate:
        return f'- "{entry.source_term}": DO NOT TRANSLATE'
    note = f" ({entry.note})" if entry.note else ""
    return f'- "{entry.source_term}" → "{entry.target_term}"{note}'


# ── Prompts ───────────────────────────────────────────────────────────


class Translator:
    def __init__(self, language: LanguageCode | str, groups: Iterable[Group], glossary: Optional[Glossary] = None,
                 titles: Optional[dict[str, str]] = None, memory_tokens: int = DEFAULT_MEMORY_TOKENS):
        self.language = get_language(language)
        self.glossary = glossary
        self.titles = titles or {}
        self.memory_tokens = memory_tokens
        self.memory: list[GlossaryEntry] = []
        self.by_key = {g.key: g for g in groups}

    def remember(self, pairs: Iterable[tuple[str, str]]) -> None:
        self.memory = memory_entries(pairs)

    def _title(self, scope: str) -> str:
        if scope == SCOPE_TEMPLATE:
            return "Template text (headings, labels and fixed text of the document template)"
        if scope == SCOPE_XREFS:
            return "Cross-reference phrases"
        title = self.titles.get(scope)
        return f"Section: {title}" if title else f"Section {scope}"

    def line(self, group: Group) -> Line:
        context = f' (in: "{_show(group.context)}")' if group.context else ""
        return Line(f"[{group.key}] ({group.role}){context} {_show(group.source_text)}", [group.key])

    def blocks(self, groups: Iterable[Group], budget: int = DEFAULT_BLOCK_TOKENS) -> list[Block]:
        scopes: dict[str, list[Group]] = {}
        for group in groups:
            scopes.setdefault(group.scope, []).append(group)
        return pack([SectionLines(scope, f"### {self._title(scope)}", [self.line(g) for g in members])
                     for scope, members in scopes.items()], budget)

    def _texts(self, block: Block) -> str:
        return "\n".join(self.by_key[k].source_text for k in self.keys(block))

    @staticmethod
    def keys(block: Block) -> list[str]:
        return [u for part in block.parts for line in part.lines for u in line.unit_ids]

    def glossary_terms(self, block: Block) -> list[GlossaryEntry]:
        return terms_in(TAG.sub(" ", self._texts(block)), self.glossary.entries) if self.glossary else []

    def memory_terms(self, block: Block) -> list[GlossaryEntry]:
        texts = TAG.sub(" ", self._texts(block))
        own = {g.source_text.casefold() for g in (self.by_key[k] for k in self.keys(block))}
        picked, size = [], 0
        for entry in terms_in(texts, self.memory):
            if entry.source_term.casefold() in own:
                continue  # the text being translated is not its own example
            cost = estimate_tokens(_entry_line(entry))
            if size + cost > self.memory_tokens:
                break
            picked.append(entry)
            size += cost
        return picked

    def prompt(self, block: Block) -> str:
        resources = ""
        entries = self.glossary_terms(block)
        if entries:
            resources += GLOSSARY_SECTION.format(entries="\n".join(_entry_line(e) for e in entries))
        if self.glossary is not None and (self.glossary.style_notes or "").strip():
            resources += STYLE_SECTION.format(notes=self.glossary.style_notes.strip())
        memory = self.memory_terms(block)
        if memory:
            resources += MEMORY_SECTION.format(entries="\n".join(_entry_line(e) for e in memory))
        return USER_PROMPT.format(language=self.language.name, code=self.language.code.value, resources=resources,
                                  segments=block.render())

    def repair_prompt(self, block: Block, previous: dict[str, Optional[str]], problems: dict[str, list[str]]) -> str:
        lines = []
        for key in self.keys(block):
            before = previous.get(key)
            shown = f'"{_show(before)}"' if before else "(none)"
            lines.append(f"- [{key}] previous translation: {shown}; problems: {'; '.join(problems.get(key, []))}")
        return f"{self.prompt(block)}\n\n{REPAIR_HEADING}\n" + "\n".join(lines)

    def accept(self, block: Block, output: TranslatorOutput) -> dict[str, str]:
        """key → translation for the block's segments the answer translated (other IDs and empty answers dropped)."""
        wanted = set(self.keys(block))
        out: dict[str, str] = {}
        for item in output.translations:
            key = item.segment_id.strip().strip("[]")
            if key in wanted and key not in out and (item.translation or "").strip():
                out[key] = _restore(item.translation, self.by_key[key].source_text)
        return out


# ── LLM calls ─────────────────────────────────────────────────────────


@dataclass
class TranslateRun:
    targets: dict[str, str] = field(default_factory=dict)  # group key → translation
    usage: dict[str, int] = field(default_factory=dict)
    calls: int = 0
    failed_calls: int = 0
    left_out: int = 0              # segments an answer skipped (asked again once)
    blocks: int = 0
    memory_pairs: int = 0
    glossary_terms: set[str] = field(default_factory=set)

    @property
    def all_failed(self) -> bool:
        return self.calls > 0 and self.failed_calls == self.calls


async def _run_blocks(translator: Translator, run: TranslateRun, blocks: list[Block], prompt: Callable[[Block], str],
                      chain: Any, rate_limiter: Any, max_concurrent: int, task: str) -> None:
    """One call per block, and one more for what it did not translate: the segments an answer left out (models skip
    items of a long list), or, when the call failed, its segments as two halves (a model that runs away to its
    output limit on a long list usually manages half of it). A segment still without an answer stays
    untranslated."""
    gate = asyncio.Semaphore(max(1, max_concurrent))

    def block_of(keys: list[str]) -> Block:
        return translator.blocks([translator.by_key[k] for k in keys], 10 ** 9)[0]

    async def one(block: Block, retry: bool = True) -> None:
        async with gate:
            run.calls += 1
            run.glossary_terms.update(e.source_term for e in translator.glossary_terms(block))
            messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt(block))]
            try:
                output = await _call(chain, messages, TranslatorOutput, run.usage, rate_limiter, task)
            except Exception as exc:
                run.failed_calls += 1
                logger.warning(f"Translator call failed for {translator.keys(block)[:3]}…: {str(exc)[:200]}")
                output = None
        keys = translator.keys(block)
        if output is not None:
            answered = translator.accept(block, output)
            run.targets.update(answered)
            left = [k for k in keys if k not in answered]
            if retry and left:
                run.left_out += len(left)
                await one(block_of(left), retry=False)
        elif retry and len(keys) > 1:
            half = len(keys) // 2
            await asyncio.gather(one(block_of(keys[:half]), retry=False), one(block_of(keys[half:]), retry=False))

    await asyncio.gather(*(one(block) for block in blocks))


async def translate_all(translator: Translator, groups: list[Group], chain_factory: Any, rate_limiter: Any = None,
                        block_tokens: int = DEFAULT_BLOCK_TOKENS, max_concurrent: int = 3) -> TranslateRun:
    """Translate *groups* in two waves; the first wave's short texts are the second wave's memory."""
    run = TranslateRun()
    if not groups:
        return run
    chain = chain_factory.create_structured_planner(TranslatorOutput, include_raw=True)
    for wave in (1, 2):
        blocks = translator.blocks([g for g in groups if g.wave == wave], block_tokens)
        run.blocks += len(blocks)
        await _run_blocks(translator, run, blocks, translator.prompt, chain, rate_limiter, max_concurrent, "translator")
        if wave == 1:
            translator.remember((g.source_text, run.targets[g.key]) for g in groups
                                if g.wave == 1 and g.key in run.targets)
            run.memory_pairs = len(translator.memory)
    return run


async def repair_all(translator: Translator, groups: list[Group], previous: dict[str, Optional[str]],
                     problems: dict[str, list[str]], chain_factory: Any, rate_limiter: Any = None,
                     block_tokens: int = DEFAULT_BLOCK_TOKENS, max_concurrent: int = 3) -> TranslateRun:
    """One retranslation of *groups*, each with its previous translation and problems."""
    run = TranslateRun()
    if not groups:
        return run
    chain = chain_factory.create_structured_planner(TranslatorOutput, include_raw=True)
    blocks = translator.blocks(groups, block_tokens)
    run.blocks = len(blocks)
    run.memory_pairs = len(translator.memory)
    await _run_blocks(translator, run, blocks, lambda b: translator.repair_prompt(b, previous, problems), chain,
                      rate_limiter, max_concurrent, "translator_repair")
    return run


# ── Translation sets ──────────────────────────────────────────────────


def merged(segment_set: SegmentSet, sets: Iterable[TranslationSet]) -> SegmentSet:
    """The segments with their latest translations; unchanged when nothing is translated yet.

    Every segment must be in exactly one set, with its English text and locator: anything else is a bug.
    """
    by_id: dict[str, Segment] = {}
    for translation_set in sets:
        for segment in translation_set.segments:
            if segment.segment_id in by_id:
                raise RuntimeError(f"segment {segment.segment_id} is in two translation sets")
            by_id[segment.segment_id] = segment
    if not by_id:
        return segment_set
    out = []
    for segment in segment_set.segments:
        translated = by_id.pop(segment.segment_id, None)
        if translated is None:
            raise RuntimeError(f"segment {segment.segment_id} is in no translation set")
        if translated.source_text != segment.source_text or translated.locator != segment.locator:
            raise RuntimeError(f"segment {segment.segment_id} of a translation set does not match the segments")
        out.append(segment.model_copy(update={"target_text": translated.target_text, "origin": translated.origin}))
    if by_id:
        raise RuntimeError(f"translation sets hold unknown segments: {sorted(by_id)[:5]}")
    return segment_set.model_copy(update={"segments": out})


def build_sets(job: TranslationJob, segments: Iterable[Segment],
               targets: dict[str, tuple[Optional[str], Optional[SegmentOrigin]]], versions: dict[str, int],
               model: Optional[str] = None) -> list[TranslationSet]:
    """One ``TranslationSet`` per scope in *versions*, its segments taking their (text, origin) from *targets*
    (a segment not in *targets* keeps what it has)."""
    by_scope: dict[str, list[Segment]] = {scope: [] for scope in versions}
    for segment in segments:
        if segment.scope not in by_scope:
            continue
        if segment.segment_id in targets:
            text, origin = targets[segment.segment_id]
            segment = segment.model_copy(update={"target_text": text, "origin": origin})
        by_scope[segment.scope].append(segment)
    return [TranslationSet(job_id=job.job_id, language=job.language, scope=scope, version=versions[scope],
                           segments=members, prompt_version=PROMPT_VERSION, model=model)
            for scope, members in by_scope.items()]


def group_of(groups: Iterable[Group]) -> dict[str, Group]:
    """segment id → its group."""
    return {sid: g for g in groups for sid in g.segment_ids}

