"""Review of a translation job (Phase T7): a reviewer's edits, find and replace, issue resolutions, the approval and
the approved export.

- **Edits** change a segment's translation (``origin: human``): by default every segment with the same English
  text that no human has edited yet (``apply_to="same_text"``), or only that one (``"this"``). An edit the
  renderer could not show (empty, ``{{ref:}}`` tokens, ``⟦k⟧`` markers or ``|`` cell separators changed) is refused.
- **Find and replace** changes a word or phrase in the translations: one occurrence, a chosen set or all of them,
  never inside a marker or token. Whole-word matching reports the longer words it leaves out (German inflections
  and compounds: "Eigentümersystems"); without whole words they are replaced too ("Eigentümer-Systems"). Replacing every occurrence of a document term's agreed translation agrees the new
  one (``glossary[terms]``), so the ``TERM-<n>`` checks follow the reviewer.
- Every change writes the next ``translation[<scope>]`` of the scopes it touches and runs the QA checks again at
  once (deterministic, no LLM): the changed segments' issues are reopened, every other resolution carries over.
  The render is then out of date until ``POST /{id}/render`` (``TranslationOrchestrator.rerender``).
- **Approval** needs a current render without post-render problems, and no open gate or critical issue.
- **The export** serves the very ``docx[translated]`` that was approved.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Union

from app.schemas.v2 import (
    ArtifactKind,
    ArtifactRef,
    Glossary,
    QualityReport,
    RenderReport,
    Segment,
    SegmentOrigin,
    SegmentSet,
    Severity,
    TranslationJob,
    TranslationSet,
    TranslationStatus,
)
from app.schemas.v2.refs import REF_TOKEN_PATTERN
from app.services.migration_v2.quality.gates import gate_counts

from .checks import check_segment, check_translations
from .languages import get_language
from .render import TRANSLATED
from .stages import CHECKS, TranslationStageContext, current_segments, job_glossary, job_terms, translation_versions
from .template_text import TAG
from .translator import TERMS, build_sets

STRUCTURAL = ("EMPTY", "REF_TOKENS", "TAGS", "CELLS")  # an edit with one of these could not be rendered
_PROTECTED = re.compile(f"{TAG.pattern}|{REF_TOKEN_PATTERN.pattern}")
_CONTEXT = 60
TEXT_MAX = 500  # characters of a text kept in an event

ApplyTo = Literal["same_text", "this"]


class ReviewError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Optional[list[str]] = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details or []


def require_review(job: TranslationJob, running: bool) -> None:
    """A reviewer acts only on a job that waits for review and is not running."""
    if running:
        raise ReviewError(409, "JOB_RUNNING", f"Job {job.job_id} is running; review once it has finished")
    if job.status != TranslationStatus.REVIEW_PENDING:
        raise ReviewError(409, "NOT_IN_REVIEW", f"Job {job.job_id} is {job.status.value}; only a job in review "
                                                "(REVIEW_PENDING) can be changed")


# ── Saving a reviewer's translations ──────────────────────────────────


def _code(issue_id: str, segment_id: str) -> str:
    return issue_id.removeprefix(f"TQ-{segment_id}-")


def structural_problems(ctx: TranslationStageContext, segment: Segment, text: str) -> list[str]:
    """Why *text* could not be rendered as *segment*'s translation (empty when it can)."""
    edited = segment.model_copy(update={"target_text": text, "origin": SegmentOrigin.HUMAN})
    return [i.message for i in check_segment(edited, ctx.job.language, job_glossary(ctx), ctx.settings, job_terms(ctx))
            if _code(i.issue_id, segment.segment_id) in STRUCTURAL]


def summary(report: QualityReport) -> dict[str, Any]:
    open_issues = [i for i in report.issues if not i.resolved]
    severities: dict[str, int] = {}
    for issue in open_issues:
        severities[issue.severity.value] = severities.get(issue.severity.value, 0) + 1
    return {"version": report.version, "issues": len(report.issues), "open": len(open_issues),
            "by_severity": severities, "gate_issues": len(report.open_gate_issues), "gates_passed": report.gates_passed}


def recheck(ctx: TranslationStageContext, segment_set: SegmentSet, reopened: set[str]) -> QualityReport:
    """The QA checks of every segment as the next ``quality_report[translation]``; the issues of the *reopened*
    segments lose their resolutions (they were about the old text), the others keep them."""
    ctx.refresh()
    previous = ctx.latest(ArtifactKind.QUALITY_REPORT, QualityReport, CHECKS)
    if previous is not None and reopened:
        previous = previous.model_copy(update={
            "issues": [i for i in previous.issues if not set(i.segment_ids) & reopened]})
    current = current_segments(ctx, segment_set)
    report = check_translations(ctx.job.job_id, ctx.next_version(ArtifactKind.QUALITY_REPORT, CHECKS),
                                current.segments, ctx.job.language, job_glossary(ctx), ctx.settings, previous,
                                job_terms(ctx))
    ctx.write(ArtifactKind.QUALITY_REPORT, report, scope=CHECKS)
    return report


@dataclass
class Saved:
    segments: list[Segment]
    report: QualityReport
    versions: dict[str, int]


def save_human(ctx: TranslationStageContext, segment_set: SegmentSet, current: SegmentSet,
               texts: dict[str, str]) -> Saved:
    """Write *texts* (segment id → translation) as ``origin: human`` into the next sets of the scopes they touch,
    then check again."""
    by_id = {s.segment_id: s for s in current.segments}
    scopes = list(dict.fromkeys(by_id[sid].scope for sid in texts))
    versions = {scope: ctx.next_version(ArtifactKind.TRANSLATION, scope) for scope in scopes}
    targets = {sid: (text, SegmentOrigin.HUMAN) for sid, text in texts.items()}
    for translation_set in build_sets(ctx.job, current.segments, targets, versions):
        previous = ctx.latest(ArtifactKind.TRANSLATION, TranslationSet, translation_set.scope)
        if previous is not None:  # the set's prompt and model stay those of its machine translation
            translation_set = translation_set.model_copy(update={"prompt_version": previous.prompt_version,
                                                                 "model": previous.model})
        ctx.write(ArtifactKind.TRANSLATION, translation_set, scope=translation_set.scope)
    report = recheck(ctx, segment_set, set(texts))
    changed = [s for s in current_segments(ctx, segment_set).segments if s.segment_id in texts]
    return Saved(changed, report, versions)


def _result(ctx: TranslationStageContext, saved: Saved) -> dict[str, Any]:
    ids = {s.segment_id for s in saved.segments}
    return {
        "segments": [s.to_clean_dict() for s in saved.segments],
        "issues": [i.to_clean_dict() for i in saved.report.issues if not i.resolved and set(i.segment_ids) & ids],
        "validation": summary(saved.report),
        "translation_versions": translation_versions(ctx.job),
        "render_current": render_state(ctx).current,
    }


def _clip(text: Optional[str]) -> Optional[str]:
    return text[:TEXT_MAX] if text is not None else None


# ── Edit one segment ──────────────────────────────────────────────────


def edit_segment(ctx: TranslationStageContext, segment_id: str, target_text: str,
                 apply_to: ApplyTo = "same_text") -> dict[str, Any]:
    """Save a reviewer's translation of a segment, and of every segment with the same English text that no human
    has edited yet unless *apply_to* is ``"this"``."""
    segment_set = ctx.require(ArtifactKind.SEGMENTS, SegmentSet)
    current = current_segments(ctx, segment_set)
    segment = next((s for s in current.segments if s.segment_id == segment_id), None)
    if segment is None:
        raise ReviewError(404, "SEGMENT_NOT_FOUND", f"Job {ctx.job.job_id} has no segment {segment_id}")
    text = target_text.strip()
    problems = structural_problems(ctx, segment, text)
    if problems:
        raise ReviewError(422, "SEGMENT_INVALID", f"The translation of {segment_id} cannot be shown in the document "
                                                  f"({len(problems)} problem(s))", problems)
    ids = [segment_id]
    if apply_to == "same_text":
        ids += [s.segment_id for s in current.segments if s.segment_id != segment_id
                and s.source_text == segment.source_text and s.origin != SegmentOrigin.HUMAN]
    saved = save_human(ctx, segment_set, current, {sid: text for sid in ids})
    ctx.event("segment_edited", {
        "segment_id": segment_id, "apply_to": apply_to, "applied_to": ids, "versions": saved.versions,
        "before": _clip(segment.target_text), "after": _clip(text), "quality_report_version": saved.report.version,
    })
    return _result(ctx, saved)


# ── Find and replace ──────────────────────────────────────────────────


@dataclass
class Match:
    segment: Segment
    occurrence: int  # 0-based, within the segment's translation
    start: int
    end: int

    def view(self) -> dict[str, Any]:
        text = self.segment.target_text or ""
        return {
            "segment_id": self.segment.segment_id, "occurrence": self.occurrence, "kind": self.segment.kind.value,
            "scope": self.segment.scope, "origin": self.segment.origin.value if self.segment.origin else None,
            "english": self.segment.source_text[:TEXT_MAX], "context_before": text[max(0, self.start - _CONTEXT):self.start],
            "match": text[self.start:self.end], "context_after": text[self.end:self.end + _CONTEXT],
        }


def _check_phrase(name: str, value: str, required: bool = True) -> str:
    value = unicodedata.normalize("NFC", value)
    if required and not value.strip():
        raise ReviewError(422, "REPLACE_INVALID", f"'{name}' is empty")
    if _PROTECTED.search(value):
        raise ReviewError(422, "REPLACE_INVALID", f"'{name}' contains a ⟦k⟧ marker or a {{{{ref:}}}} token; those "
                                                  "are kept as they are")
    return value


def _pattern(find: str, language, case_sensitive: bool, whole_word: bool) -> re.Pattern:
    body = r"\s+".join(re.escape(w) for w in find.split())  # any whitespace between the words
    if whole_word and not get_language(language).east_asian:  # Chinese and Japanese: substrings
        body = rf"(?<![^\W_]){body}(?![^\W_])"
    return re.compile(body, 0 if case_sensitive else re.IGNORECASE)


def _matches(segments: list[Segment], pattern: re.Pattern, section: Optional[str]) -> list[Match]:
    """Every occurrence of *pattern* in the translations, never inside or across a marker or token."""
    out: list[Match] = []
    for segment in segments:
        text = segment.target_text
        if not text or (section and segment.scope != section):
            continue
        n, pos = 0, 0
        pieces = [(m.start(), m.end()) for m in _PROTECTED.finditer(text)] + [(len(text), len(text))]
        for start, end in pieces:
            for found in pattern.finditer(text, pos, start):
                if found.end() > found.start():
                    out.append(Match(segment, n, found.start(), found.end()))
                    n += 1
            pos = end
    return out


def longer_words(segments: list[Segment], find: str, language, case_sensitive: bool,
                 section: Optional[str]) -> dict[str, int]:
    """The longer words *find* occurs in that whole-word matching leaves out, with their counts: inflected and
    compound forms ("Eigentümersystems", "Eigentümersystemdaten"), so the reviewer can include them."""
    if get_language(language).east_asian:
        return {}
    strict = {(m.segment.segment_id, m.start) for m in _matches(segments, _pattern(find, language, case_sensitive, True),
                                                                section)}
    out: dict[str, int] = {}
    for match in _matches(segments, _pattern(find, language, case_sensitive, False), section):
        if (match.segment.segment_id, match.start) in strict:
            continue
        text = match.segment.target_text or ""
        start, end = match.start, match.end
        while start > 0 and (text[start - 1].isalnum()):
            start -= 1
        while end < len(text) and text[end].isalnum():
            end += 1
        out[text[start:end]] = out.get(text[start:end], 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _key(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def _term_hits(ctx: TranslationStageContext, find: str) -> tuple[list[str], list[str]]:
    """The glossary entries and the document terms whose agreed translation is *find* (their English terms)."""
    key = _key(find)
    glossary = job_glossary(ctx)
    entries = [e.source_term for e in (glossary.entries if glossary else []) if _key(e.target_term) == key]
    terms = [e.source_term for e in job_terms(ctx) if _key(e.target_term) == key]
    return entries, terms


def find_matches(ctx: TranslationStageContext, find: str, case_sensitive: bool = False, whole_word: bool = True,
                 section: Optional[str] = None) -> dict[str, Any]:
    """The occurrences of a word or phrase in the translations, for the reviewer to choose from; nothing is saved."""
    find = _check_phrase("find", find)
    segment_set = ctx.require(ArtifactKind.SEGMENTS, SegmentSet)
    current = current_segments(ctx, segment_set)
    matches = _matches(current.segments, _pattern(find, ctx.job.language, case_sensitive, whole_word), section)
    entries, terms = _term_hits(ctx, find)
    warnings = [f"\"{find}\" is the glossary's translation of \"{t}\": replacing it opens glossary issues"
                for t in entries]
    warnings += [f"\"{find}\" is the agreed translation of the document term \"{t}\": replacing every occurrence "
                 "agrees the new text for the whole document" for t in terms]
    longer = longer_words(current.segments, find, ctx.job.language, case_sensitive, section) if whole_word else {}
    if longer:
        forms = ", ".join(f"{w} ({n})" for w, n in list(longer.items())[:5])
        warnings.append(f"\"{find}\" also occurs inside {sum(longer.values())} longer word(s), e.g. {forms}; search "
                        "without whole words to include them")
    return {
        "find": find, "total": len(matches), "segments": len({m.segment.segment_id for m in matches}),
        "longer_words": longer,
        "matches": [m.view() for m in matches], "translation_versions": translation_versions(ctx.job),
        "glossary_terms": entries, "document_terms": terms, "warnings": warnings,
    }


@dataclass
class Occurrence:
    segment_id: str
    occurrence: int


def replace(ctx: TranslationStageContext, find: str, replacement: str,
            targets: Union[Literal["all"], list[Occurrence]], expected_versions: dict[str, int],
            case_sensitive: bool = False, whole_word: bool = True, section: Optional[str] = None) -> dict[str, Any]:
    """Replace the chosen occurrences (or ``"all"``) of a word or phrase with *replacement*, as a find-and-replace
    preview showed them; refused when the translations changed since (``expected_versions``)."""
    find = _check_phrase("find", find)
    replacement = _check_phrase("replace", replacement, required=False)
    if expected_versions != translation_versions(ctx.job):
        raise ReviewError(409, "PREVIEW_OUT_OF_DATE", "The translations changed since the preview; preview again")
    segment_set = ctx.require(ArtifactKind.SEGMENTS, SegmentSet)
    current = current_segments(ctx, segment_set)
    matches = _matches(current.segments, _pattern(find, ctx.job.language, case_sensitive, whole_word), section)
    if targets != "all":
        wanted = {(t.segment_id, t.occurrence) for t in targets}
        known = {(m.segment.segment_id, m.occurrence) for m in matches}
        unknown = sorted(wanted - known)
        if unknown:
            raise ReviewError(422, "REPLACE_INVALID", f"{len(unknown)} chosen occurrence(s) are not matches",
                              [f"{sid} occurrence {n}" for sid, n in unknown])
        matches = [m for m in matches if (m.segment.segment_id, m.occurrence) in wanted]
    if not matches:
        raise ReviewError(422, "NO_MATCHES", f"\"{find}\" does not occur in the translations")

    by_segment: dict[str, list[Match]] = {}
    for match in matches:
        by_segment.setdefault(match.segment.segment_id, []).append(match)
    texts: dict[str, str] = {}
    skipped: list[dict[str, Any]] = []
    for sid, found in by_segment.items():
        text = found[0].segment.target_text or ""
        for match in reversed(found):
            text = text[:match.start] + replacement + text[match.end:]
        problems = structural_problems(ctx, found[0].segment, text)
        if problems:
            skipped.append({"segment_id": sid, "problems": problems})
        else:
            texts[sid] = text
    if not texts:
        raise ReviewError(422, "SEGMENT_INVALID", "No occurrence could be replaced",
                          [p for s in skipped for p in s["problems"]])

    term_updated: list[str] = []
    if targets == "all" and section is None and replacement.strip():
        term_updated = _agree_term(ctx, find, replacement)
    saved = save_human(ctx, segment_set, current, texts)
    replaced = sum(len(by_segment[sid]) for sid in texts)
    ctx.event("segments_replaced", {
        "find": _clip(find), "replace": _clip(replacement), "targets": "all" if targets == "all" else "chosen",
        "section": section, "count": replaced, "segment_ids": list(texts), "skipped": [s["segment_id"] for s in skipped],
        "versions": saved.versions, "term_updated": term_updated, "quality_report_version": saved.report.version,
    })
    left = longer_words(current_segments(ctx, segment_set).segments, find, ctx.job.language, case_sensitive, section)         if whole_word else {}
    return {**_result(ctx, saved), "replaced": replaced, "skipped": skipped, "term_updated": term_updated,
            "longer_words": left}


def _agree_term(ctx: TranslationStageContext, find: str, replacement: str) -> list[str]:
    """Agree *replacement* for the document terms translated as *find*: the next ``glossary[terms]``."""
    terms = ctx.latest(ArtifactKind.GLOSSARY, Glossary, TERMS)
    if terms is None:
        return []
    key = _key(find)
    hits = [e.source_term for e in terms.entries if _key(e.target_term) == key]
    if not hits:
        return []
    entries = [e.model_copy(update={"target_term": replacement.strip()}) if _key(e.target_term) == key else e
               for e in terms.entries]
    ctx.write(ArtifactKind.GLOSSARY, terms.model_copy(update={
        "entries": entries, "version": ctx.next_version(ArtifactKind.GLOSSARY, TERMS)}), scope=TERMS)
    return hits


# ── Issues ────────────────────────────────────────────────────────────


def resolve_issue(ctx: TranslationStageContext, issue_id: str, note: str) -> dict[str, Any]:
    """Resolve one open issue with the reviewer's note, as the next ``quality_report[translation]``."""
    report = ctx.require(ArtifactKind.QUALITY_REPORT, QualityReport, CHECKS)
    issue = next((i for i in report.issues if i.issue_id == issue_id), None)
    if issue is None:
        raise ReviewError(404, "ISSUE_NOT_FOUND", f"Issue '{issue_id}' is not in the quality report")
    if issue.resolved:
        raise ReviewError(409, "ISSUE_RESOLVED", f"Issue {issue_id} is already resolved")
    note = note.strip()
    signed = f"{ctx.actor}: {note}" if ctx.actor else note
    issues = [i.model_copy(update={"resolved": True, "resolution_note": signed}) if i.issue_id == issue_id else i
              for i in report.issues]
    saved = report.model_copy(update={"issues": issues, "gate_counts": gate_counts(issues),
                                      "version": ctx.next_version(ArtifactKind.QUALITY_REPORT, CHECKS)})
    ctx.write(ArtifactKind.QUALITY_REPORT, saved, scope=CHECKS)
    ctx.event("issue_resolved", {"issue_id": issue_id, "gate": issue.gate.value if issue.gate else None,
                                 "severity": issue.severity.value, "note": note[:TEXT_MAX],
                                 "quality_report_version": saved.version})
    ctx.refresh()
    return {**saved.to_clean_dict(), "gates_passed": saved.gates_passed,
            "blockers": [b.view() for b in approval_blockers(ctx)]}


# ── The render and the approval ───────────────────────────────────────


@dataclass
class RenderState:
    docx: Optional[ArtifactRef] = None
    report: Optional[RenderReport] = None
    current: bool = False
    event: dict[str, Any] = field(default_factory=dict)  # the render event's detail


def _last_event(ctx: TranslationStageContext, name: str) -> Optional[dict[str, Any]]:
    return next((e["detail"] or {} for e in reversed(ctx.store.list_events(ctx.job.job_id)) if e["event"] == name),
                None)


def render_state(ctx: TranslationStageContext) -> RenderState:
    """The latest translated render and whether it shows the latest translations.

    A render records the translation versions it rendered; one rendered before that (Phase T6) is current when no
    translation was written after its document."""
    job = ctx.job
    docx = job.latest_artifact(ArtifactKind.DOCX, TRANSLATED)
    if docx is None:
        return RenderState()
    report = ctx.latest(ArtifactKind.RENDER_REPORT, RenderReport, TRANSLATED)
    event = _last_event(ctx, "render") or {}
    if event.get("docx_version") == docx.version and "translation_versions" in event:
        current = event["translation_versions"] == translation_versions(job)
    else:
        at = next(n for n, a in enumerate(job.artifacts) if a == docx)
        current = not any(a.kind == ArtifactKind.TRANSLATION for a in job.artifacts[at + 1:])
    return RenderState(docx, report, current, event)


@dataclass
class Blocker:
    code: str
    message: str
    issue_id: Optional[str] = None

    def view(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, **({"issue_id": self.issue_id} if self.issue_id else {})}


def approval_blockers(ctx: TranslationStageContext, state: Optional[RenderState] = None) -> list[Blocker]:
    """What keeps the job from being approved: no current render, render problems, open gate or critical issues."""
    state = state or render_state(ctx)
    out: list[Blocker] = []
    if state.docx is None:
        out.append(Blocker("NO_RENDER", "The translated document has not been rendered"))
    elif not state.current:
        out.append(Blocker("RENDER_OUT_OF_DATE", "The translations changed since the last render; render again"))
    out += [Blocker("RENDER_PROBLEMS", p) for p in (state.report.problems if state.report else [])]
    report = ctx.latest(ArtifactKind.QUALITY_REPORT, QualityReport, CHECKS)
    if report is None:
        out.append(Blocker("NO_VALIDATION", "The translation has not been checked"))
        return out
    for issue in report.issues:
        if issue.resolved:
            continue
        if issue.gate is not None:
            out.append(Blocker("OPEN_GATE", issue.message, issue.issue_id))
        elif issue.severity == Severity.CRITICAL:
            out.append(Blocker("OPEN_CRITICAL", issue.message, issue.issue_id))
    return out


def review_view(ctx: TranslationStageContext) -> dict[str, Any]:
    """The review state a workspace polls: whether the render is current and what blocks the approval."""
    state = render_state(ctx)
    blockers = approval_blockers(ctx, state)
    return {"render_current": state.current, "docx_version": state.docx.version if state.docx else None,
            "blockers": [b.view() for b in blockers], "can_approve": not blockers}


def approve(ctx: TranslationStageContext, note: Optional[str] = None) -> TranslationJob:
    """Approve the job's latest render; refused while anything blocks it."""
    state = render_state(ctx)
    blockers = approval_blockers(ctx, state)
    if blockers:
        raise ReviewError(409, "APPROVAL_BLOCKED", f"Job {ctx.job.job_id} cannot be approved yet "
                                                   f"({len(blockers)} blocker(s))", [b.message for b in blockers])
    report = ctx.require(ArtifactKind.QUALITY_REPORT, QualityReport, CHECKS)
    detail = {
        "docx_version": state.docx.version, "sha256": state.docx.sha256,
        "translation_versions": translation_versions(ctx.job), "quality_report_version": report.version,
        "open_issues": summary(report)["by_severity"], "kept_english": state.event.get("kept_ids", []),
        "note": (note or "").strip()[:TEXT_MAX] or None,
    }
    if not ctx.store.approve(ctx.job.job_id, ctx.actor, detail):
        raise ReviewError(409, "NOT_IN_REVIEW", f"Job {ctx.job.job_id} is no longer in review")
    return ctx.refresh()


def approved_export(ctx: TranslationStageContext) -> tuple[bytes, str]:
    """The approved translated document (the ``docx[translated]`` the approval names) and its file name."""
    job = ctx.job
    if job.status != TranslationStatus.APPROVED:
        raise ReviewError(409, "NOT_APPROVED", f"Job {job.job_id} is {job.status.value}; the translated document is "
                                               "exported once it is approved")
    approved = _last_event(ctx, "approved") or {}
    ref = next((a for a in job.artifacts if a.kind == ArtifactKind.DOCX and a.scope == TRANSLATED
                and a.version == approved.get("docx_version")), None)
    if ref is None:
        raise ReviewError(404, "NO_RENDER", f"Job {job.job_id} has no approved document")
    data = ctx.artifacts.read_bytes(ref)
    ctx.event("export", {"docx_version": ref.version, "sha256": ref.sha256})
    return data, f"{job.job_id}_{job.language.value}_v{ref.version}.docx"
