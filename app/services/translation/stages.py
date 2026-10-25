"""Stage functions run by the translation orchestrator, one per working status (as ``migration_v2/stages.py``).

A stage receives a ``TranslationStageContext`` and may return a status to go to instead of the default next one.
A stage must be safe to re-run: after a crash or a retry it runs again and writes the next artifact versions.

PREPARING (Phase T4) snapshots the completed migration's English final document into the job and cuts it into
segments. TRANSLATING translates the document's recurring terms (``glossary[terms]``) and then the segments (one
``translation[<scope>]`` per scope), CHECKING runs the QA checks
(``quality_report[translation]``) and sends the failing segments to REPAIRING once (Phase T5). RENDERING renders the
translated final document (``docx[translated]``, ``render_report[translated]``) for review (Phase T6); its
``render`` event records the translation versions it rendered, so review (T7) knows when a render is out of date.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from app.schemas.v2 import (
    ArtifactKind,
    AssembledDocument,
    Glossary,
    GlossaryEntry,
    NumberMap,
    QualityReport,
    SectionDraft,
    SegmentOrigin,
    SegmentSet,
    SlotPlan,
    SourceDocument,
    TemplateModel,
    TranslationJob,
    TranslationSet,
    TranslationStatus,
)
from app.services.migration_v2.artifacts import ArtifactWriter
from app.services.migration_v2.export import EXPORTABLE, ExportBlocked, render_final
from app.services.migration_v2.render import RenderBlocked, RenderError
from app.services.migration_v2.render.pages import word_page_counter

from . import glossary_service
from .checks import check_segment, check_translations, copy_only, needs_repair, repair_candidates, worst
from .front_matter import FrontMatterError
from .languages import get_language
from .render import TRANSLATED, render_translation
from .segments import build_segments
from .template_text import harvest_hook
from .terms import find_terms
from .translator import (
    TERMS,
    Translator,
    build_sets,
    group_of,
    group_segments,
    merged,
    repair_all,
    term_entries,
    translate_all,
)

SYSTEM_ACTOR = "system"
ENGLISH = "english"  # scope of the English final document's snapshot artifacts
CHECKS = "translation"  # scope of the QA checks' quality_report


@dataclass
class TranslationStageContext:
    job: TranslationJob
    store: Any                      # TranslationStore
    artifacts: ArtifactWriter       # over settings.translation_dir
    migrations: Any                 # MigrationStore
    migration_artifacts: ArtifactWriter
    glossaries: Any = None          # GlossaryStore
    language_templates: Any = None  # LanguageTemplateStore
    settings: Any = None
    rate_limiter: Any = None
    chain_factory: Any = None
    actor: str = SYSTEM_ACTOR       # who writes the artifacts and events: a reviewer in review (T7)

    def write(self, kind: ArtifactKind, payload, scope: Optional[str] = None):
        return self.artifacts.write(self.job.job_id, kind, payload, scope=scope, created_by=self.actor)

    def write_file(self, kind: ArtifactKind, data: bytes, suffix: str, scope: Optional[str] = None):
        return self.artifacts.write_file(self.job.job_id, kind, data, suffix, scope=scope, created_by=self.actor)

    def refresh(self) -> TranslationJob:
        """Re-read the job, so ``latest`` sees the artifacts written since."""
        self.job = self.store.get_job(self.job.job_id)
        return self.job

    def next_version(self, kind: ArtifactKind, scope: Optional[str] = None) -> int:
        return self.store.next_artifact_version(self.job.job_id, kind, scope)

    def latest(self, kind: ArtifactKind, model, scope: Optional[str] = None):
        return self.artifacts.latest(self.job, kind, model, scope)

    def require(self, kind: ArtifactKind, model, scope: Optional[str] = None):
        value = self.latest(kind, model, scope)
        if value is None:
            raise RuntimeError(f"job {self.job.job_id} has no {kind.value} artifact")
        return value

    def event(self, event: str, detail: Optional[dict] = None) -> None:
        self.store.add_event(self.job.job_id, event, self.actor, detail)


Stage = Callable[[TranslationStageContext], Awaitable[Optional[TranslationStatus]]]


# ── PREPARING: the English final document, the job's resources, the segments ──


def _glossary(ctx: TranslationStageContext, language_name: str, notes: list[str]) -> None:
    job = ctx.job
    if not job.glossary_id:
        notes.append(f"No glossary for {language_name}: the text is translated freely.")
        ctx.event("no_glossary", {"language": job.language.value})
        return
    record = ctx.glossaries.get_version(job.glossary_id, job.glossary_version) if ctx.glossaries else None
    if record is None:
        raise RuntimeError(f"glossary {job.glossary_id} v{job.glossary_version} not found")
    if record["status"] != "approved" or record["language"] != job.language.value:
        raise RuntimeError(f"glossary {job.glossary_id} v{job.glossary_version} is {record['status']} "
                           f"({record['language']}); a job needs an approved {job.language.value} glossary")
    glossary = glossary_service.load(record)
    ctx.write(ArtifactKind.GLOSSARY, glossary)
    ctx.event("glossary", {"glossary_id": job.glossary_id, "version": job.glossary_version,
                           "entries": len(glossary.entries), "style_notes": bool(glossary.style_notes)})


def _front_matter(ctx: TranslationStageContext, language_name: str, notes: list[str]) -> None:
    job = ctx.job
    if not job.language_template_id:
        notes.append(f"English first page, header and footer kept: no language template for {language_name} "
                     f"({job.language.value}).")
        ctx.event("no_language_template", {"language": job.language.value})
        return
    record = (ctx.language_templates.get_version(job.language_template_id, job.language_template_version)
              if ctx.language_templates else None)
    if record is None:
        raise RuntimeError(f"language template {job.language_template_id} v{job.language_template_version} not found")
    if record["status"] != "ready" or record["language"] != job.language.value:
        raise RuntimeError(f"language template {job.language_template_id} v{job.language_template_version} is "
                           f"{record['status']} ({record['language']}); a job needs a ready {job.language.value} "
                           "language template")
    path = Path(record.get("front_matter_path") or "")
    if not record.get("front_matter_path") or not path.exists():
        raise RuntimeError(f"language template {job.language_template_id} v{job.language_template_version} has no "
                           "front matter file")
    ref = ctx.write_file(ArtifactKind.FRONT_MATTER, path.read_bytes(), ".docx")
    ctx.event("front_matter", {"template_id": job.language_template_id, "version": job.language_template_version,
                               "sha256": ref.sha256})


async def preparing(ctx: TranslationStageContext) -> None:
    """Snapshot the migration's English final document and cut it into the ``segments`` artifact.

    The final document is rendered as the migration's export renders it (accepted gaps left out, final mode), with
    a body hook that collects the template's own text. Its inputs are copied into the job (source, template, slot
    plan, drafts, assembly and number map), with the English ``docx`` and its render report (scope ``english``),
    the glossary and the language template's front matter when the job names them.
    """
    job = ctx.job
    migration = ctx.migrations.get_job(job.migration_job_id)
    if migration is None:
        raise RuntimeError(f"migration {job.migration_job_id} not found")
    if migration.status not in EXPORTABLE:
        raise RuntimeError(f"migration {job.migration_job_id} is {migration.status.value}; a translation starts from "
                           "a completed migration")

    collected: list[tuple[str, str]] = []
    try:
        final = render_final(migration, ctx.migrations, ctx.migration_artifacts, body_hook=harvest_hook(collected))
    except ExportBlocked as exc:
        details = f": {'; '.join(exc.details[:5])}" if exc.details else ""
        raise RuntimeError(f"the English final document cannot be rendered ({exc.code}) {exc.message}{details}") from exc

    ctx.write(ArtifactKind.SOURCE_MODEL, final.source)
    ctx.write(ArtifactKind.TEMPLATE_MODEL, final.template)
    if final.slot_plan is not None:
        ctx.write(ArtifactKind.SLOT_PLAN, final.slot_plan)
    for draft in final.drafts:
        ctx.write(ArtifactKind.SECTION_DRAFT, draft, scope=draft.target_section_id)
    ctx.write(ArtifactKind.ASSEMBLED_DRAFT, final.assembly.document)
    ctx.write(ArtifactKind.NUMBER_MAP, final.assembly.number_map)
    docx = ctx.write_file(ArtifactKind.DOCX, final.data, ".docx", scope=ENGLISH) if final.data else None
    ctx.write(ArtifactKind.RENDER_REPORT, final.report, scope=ENGLISH)
    if final.report.problems:  # the segments stand; the translated render is checked in RENDERING
        ctx.event("english_render_problems", {"problems": final.report.problems[:10]})

    notes: list[str] = []
    language_name = get_language(job.language).name
    _glossary(ctx, language_name, notes)
    _front_matter(ctx, language_name, notes)

    segments = build_segments(final.template, final.drafts, final.source, final.assembly.document, collected,
                              final.accepted)
    segment_set = SegmentSet(
        job_id=job.job_id, migration_job_id=job.migration_job_id, language=job.language,
        version=ctx.next_version(ArtifactKind.SEGMENTS), accepted_gaps=list(final.accepted),
        draft_versions=final.versions, english_docx_sha256=docx.sha256 if docx else None, notes=notes,
        segments=segments,
    )
    ctx.write(ArtifactKind.SEGMENTS, segment_set)
    ctx.event("segments", {
        "segments": len(segments), "kinds": segment_set.counts, "scopes": len(segment_set.scopes),
        "distinct_texts": len({s.source_text for s in segments}), "accepted_gaps": list(final.accepted),
        "draft_versions": final.versions,
    })


# ── TRANSLATING, CHECKING, REPAIRING (Phase T5) ───────────────────────


def _setting(ctx: TranslationStageContext, name: str, default):
    return getattr(ctx.settings, name, default) if ctx.settings is not None else default


def job_glossary(ctx: TranslationStageContext) -> Optional[Glossary]:
    """The job's snapshot of its glossary (None for a job without one: free translation)."""
    return ctx.require(ArtifactKind.GLOSSARY, Glossary) if ctx.job.glossary_id else None


def job_terms(ctx: TranslationStageContext) -> list[GlossaryEntry]:
    """The job's document terms as TRANSLATING agreed them (none for a job translated before they existed)."""
    terms = ctx.latest(ArtifactKind.GLOSSARY, Glossary, TERMS)
    return terms.entries if terms is not None else []


def _drafts(ctx: TranslationStageContext, segment_set: SegmentSet) -> list[SectionDraft]:
    drafts = [ctx.latest(ArtifactKind.SECTION_DRAFT, SectionDraft, s) for s in segment_set.draft_versions]
    return [d for d in drafts if d is not None]


def _translator(ctx: TranslationStageContext, groups, glossary: Optional[Glossary],
                terms: list[GlossaryEntry] = ()) -> Translator:
    template = ctx.latest(ArtifactKind.TEMPLATE_MODEL, TemplateModel)
    titles = {s.section_id: s.heading for s in template.sections} if template else {}
    return Translator(ctx.job.language, groups, glossary, titles, _setting(ctx, "translator_memory_tokens", 600),
                      terms, _setting(ctx, "translator_terms_tokens", 800))


def _model(ctx: TranslationStageContext) -> Optional[str]:
    factory = ctx.chain_factory
    return factory.planner_label() if factory is not None and hasattr(factory, "planner_label") else None


def _need_llm(ctx: TranslationStageContext) -> None:
    if ctx.chain_factory is None:
        raise RuntimeError("no LLM is configured; a translation needs one")


def current_segments(ctx: TranslationStageContext, segment_set: SegmentSet) -> SegmentSet:
    """The segments with their latest translations."""
    sets = [ctx.latest(ArtifactKind.TRANSLATION, TranslationSet, scope) for scope in segment_set.scopes]
    return merged(segment_set, [s for s in sets if s is not None])


def translation_versions(job: TranslationJob) -> dict[str, int]:
    """scope → the latest ``translation[<scope>]`` version."""
    out: dict[str, int] = {}
    for ref in job.artifacts:
        if ref.kind == ArtifactKind.TRANSLATION and ref.scope:
            out[ref.scope] = max(out.get(ref.scope, 0), ref.version)
    return out


async def translating(ctx: TranslationStageContext) -> None:
    """Translate the document's terms, then every distinct text once (copy those with nothing to translate); write
    the agreed terms (``glossary[terms]``) and every scope's set."""
    _need_llm(ctx)
    segment_set = ctx.require(ArtifactKind.SEGMENTS, SegmentSet)
    glossary = job_glossary(ctx)
    groups = group_segments(segment_set.segments, _drafts(ctx, segment_set))
    copied = [g for g in groups if copy_only(g.source_text, glossary)]
    todo = [g for g in groups if g not in copied]
    terms = find_terms(segment_set.segments, glossary, _setting(ctx, "translation_terms_max", 80),
                       _setting(ctx, "translation_term_min_texts", 3)) if todo else []
    translator = _translator(ctx, groups, glossary)
    run = await translate_all(translator, todo, ctx.chain_factory, ctx.rate_limiter,
                              _setting(ctx, "translator_block_tokens", 1500), _setting(ctx, "llm_max_concurrent", 3),
                              terms)
    if todo and run.all_failed:
        raise RuntimeError(f"every translation call failed ({run.failed_calls}); see the llm_call events")
    ctx.write(ArtifactKind.GLOSSARY, Glossary(
        glossary_id=f"{ctx.job.job_id}-terms", version=ctx.next_version(ArtifactKind.GLOSSARY, TERMS),
        language=ctx.job.language, name="Document terms", entries=term_entries(run.terms)), scope=TERMS)

    targets: dict[str, tuple[Optional[str], Optional[SegmentOrigin]]] = {}
    for group in copied:
        targets.update({sid: (group.source_text, SegmentOrigin.COPIED) for sid in group.segment_ids})
    for group in todo:
        text = run.targets.get(group.key)
        targets.update({sid: (text, SegmentOrigin.LLM if text is not None else None) for sid in group.segment_ids})
    versions = {scope: ctx.next_version(ArtifactKind.TRANSLATION, scope) for scope in segment_set.scopes}
    for translation_set in build_sets(ctx.job, segment_set.segments, targets, versions, _model(ctx)):
        ctx.write(ArtifactKind.TRANSLATION, translation_set, scope=translation_set.scope)
    ctx.event("translator", {
        "segments": len(segment_set.segments), "groups": len(groups), "copied": len(copied),
        "translated": len(run.targets), "missing": len(todo) - len(run.targets), "blocks": run.blocks,
        "calls": run.calls, "failed_calls": run.failed_calls, "left_out": run.left_out, "memory_pairs": run.memory_pairs,
        "glossary_terms_used": len(run.glossary_terms), "terms": len(terms), "terms_translated": len(run.terms),
        "usage": run.usage,
    })


async def checking(ctx: TranslationStageContext) -> Optional[TranslationStatus]:
    """The QA checks on every segment; segments with a repairable issue go to REPAIRING once."""
    segment_set = ctx.require(ArtifactKind.SEGMENTS, SegmentSet)
    current = current_segments(ctx, segment_set)
    previous = ctx.latest(ArtifactKind.QUALITY_REPORT, QualityReport, CHECKS)
    report = check_translations(ctx.job.job_id, ctx.next_version(ArtifactKind.QUALITY_REPORT, CHECKS),
                                current.segments, ctx.job.language, job_glossary(ctx), ctx.settings, previous,
                                job_terms(ctx))
    ctx.write(ArtifactKind.QUALITY_REPORT, report, scope=CHECKS)
    repair = repair_candidates(current.segments, report)
    open_issues = [i for i in report.issues if not i.resolved]
    severities: dict[str, int] = {}
    for issue in open_issues:
        severities[issue.severity.value] = severities.get(issue.severity.value, 0) + 1
    ctx.event("checks", {
        "round": report.version, "issues": len(report.issues), "open": len(open_issues), "by_severity": severities,
        "gate_issues": len(report.open_gate_issues), "coverage": report.unit_coverage,
        "repair": len(repair), "repair_ids": repair[:50],
    })
    return TranslationStatus.REPAIRING if repair else None


async def repairing(ctx: TranslationStageContext) -> None:
    """Retranslate the segments the last check sent to repair, once, with their problems as feedback.

    Each segment it touches becomes ``origin=repair`` (so it is never repaired again); its text is the new answer
    unless that one checks worse than the previous translation, which is then kept.
    """
    _need_llm(ctx)
    segment_set = ctx.require(ArtifactKind.SEGMENTS, SegmentSet)
    report = ctx.require(ArtifactKind.QUALITY_REPORT, QualityReport, CHECKS)
    current = current_segments(ctx, segment_set)
    wanted = set(repair_candidates(current.segments, report))
    if not wanted:
        return
    glossary = job_glossary(ctx)
    terms = job_terms(ctx)
    segments = {s.segment_id: s for s in current.segments}
    groups = group_segments(current.segments, _drafts(ctx, segment_set))
    by_segment = group_of(groups)
    repair_groups = [g for g in groups if wanted & set(g.segment_ids)]
    problems: dict[str, list[str]] = {}
    for issue in report.issues:
        for sid in issue.segment_ids:
            if sid in wanted and needs_repair(issue):
                found = problems.setdefault(by_segment[sid].key, [])
                message = issue.message.split(": ", 1)[-1]  # without the "SEG-…: " prefix
                if message not in found:
                    found.append(message)
    first = {g.key: next(s for s in g.segment_ids if s in wanted) for g in repair_groups}
    previous = {key: segments[sid].target_text for key, sid in first.items()}

    translator = _translator(ctx, groups, glossary, terms)
    translator.remember((g.source_text, segments[g.key].target_text) for g in groups
                        if g.wave == 1 and segments[g.key].origin not in (None, SegmentOrigin.COPIED)
                        and segments[g.key].target_text is not None)
    run = await repair_all(translator, repair_groups, previous, problems, ctx.chain_factory, ctx.rate_limiter,
                           _setting(ctx, "translator_block_tokens", 1500), _setting(ctx, "llm_max_concurrent", 3))

    targets: dict[str, tuple[Optional[str], Optional[SegmentOrigin]]] = {}
    improved = kept = 0
    for group in repair_groups:
        text, answer = previous[group.key], run.targets.get(group.key)
        if answer is not None:
            sample = segments[first[group.key]]
            before = check_segment(sample, ctx.job.language, glossary, ctx.settings, terms)
            after = check_segment(sample.model_copy(update={"target_text": answer, "origin": SegmentOrigin.REPAIR}),
                                  ctx.job.language, glossary, ctx.settings, terms)
            if worst(after) <= worst(before):
                text, improved = answer, improved + 1
            else:
                kept += 1
        targets.update({sid: (text, SegmentOrigin.REPAIR) for sid in group.segment_ids if sid in wanted})
    scopes = list(dict.fromkeys(segments[sid].scope for sid in targets))
    versions = {scope: ctx.next_version(ArtifactKind.TRANSLATION, scope) for scope in scopes}
    for translation_set in build_sets(ctx.job, current.segments, targets, versions, _model(ctx)):
        ctx.write(ArtifactKind.TRANSLATION, translation_set, scope=translation_set.scope)
    ctx.event("repair", {
        "segments": len(targets), "groups": len(repair_groups), "answered": len(run.targets), "improved": improved,
        "kept_previous": kept, "calls": run.calls, "failed_calls": run.failed_calls, "scopes": scopes,
        "usage": run.usage,
    })


# ── RENDERING (Phase T6) ──────────────────────────────────────────────


def _page_counter(ctx: TranslationStageContext):
    """Word measures the table of contents' page numbers when installed and allowed (``render_toc_pages``)."""
    return word_page_counter() if _setting(ctx, "render_toc_pages", "off") == "word" else None


async def rendering(ctx: TranslationStageContext) -> None:
    """Render the translated final document from the job's snapshot and the latest translations.

    The document is saved even when its post-render check has problems, so the reviewer sees them; the job goes to
    review either way (approval waits for a clean render, T7).
    """
    job = ctx.job
    segment_set = ctx.require(ArtifactKind.SEGMENTS, SegmentSet)
    current = current_segments(ctx, segment_set)
    template = ctx.require(ArtifactKind.TEMPLATE_MODEL, TemplateModel)
    source = ctx.require(ArtifactKind.SOURCE_MODEL, SourceDocument)
    package = None
    if job.language_template_id:
        ref = job.latest_artifact(ArtifactKind.FRONT_MATTER)
        if ref is None:
            raise RuntimeError(f"job {job.job_id} has no front_matter artifact")
        ctx.artifacts.read_bytes(ref)  # the snapshot is what PREPARING saved (its hash)
        package = ref.path

    job_dir = ctx.artifacts.job_dir(job.job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=job_dir) as tmp:
        work = Path(tmp) / "translated.docx"
        try:
            result = render_translation(
                job.job_id, job.language, current.segments, template, _drafts(ctx, segment_set), source, work,
                version=ctx.next_version(ArtifactKind.RENDER_REPORT, TRANSLATED),
                slot_plan=ctx.latest(ArtifactKind.SLOT_PLAN, SlotPlan), accepted_gaps=segment_set.accepted_gaps,
                assembled=ctx.latest(ArtifactKind.ASSEMBLED_DRAFT, AssembledDocument),
                number_map=ctx.latest(ArtifactKind.NUMBER_MAP, NumberMap), front_matter=package,
                settings=ctx.settings, page_counter=_page_counter(ctx),
            )
        except (RenderError, RenderBlocked, FrontMatterError) as exc:
            raise RuntimeError(f"the translated document cannot be rendered: {exc}") from exc
        docx = ctx.write_file(ArtifactKind.DOCX, work.read_bytes(), ".docx", scope=TRANSLATED)
    report = result.report
    ctx.write(ArtifactKind.RENDER_REPORT, report, scope=TRANSLATED)
    swap = result.swap
    ctx.event("render", {
        "docx_version": docx.version, "sha256": docx.sha256, "translation_versions": translation_versions(job),
        "applied": result.applied, "kept_english": len(result.kept),
        "kept_ids": result.kept[:50], "toc_entries": report.toc_entries, "toc_page_numbers": report.toc_page_numbers,
        "front_matter": ({"blocks_inserted": swap.blocks_inserted, "parts_added": len(swap.parts_added),
                          "styles_replaced": len(swap.styles_replaced)} if swap else None),
        "east_asia_font": result.east_asia_font, "warnings": len(report.warnings), "problems": report.problems[:10],
    })
    if report.problems:
        ctx.event("render_problems", {"problems": report.problems[:20]})


def default_stages() -> dict[TranslationStatus, Stage]:
    return {
        TranslationStatus.PREPARING: preparing,
        TranslationStatus.TRANSLATING: translating,
        TranslationStatus.CHECKING: checking,
        TranslationStatus.REPAIRING: repairing,
        TranslationStatus.RENDERING: rendering,
    }
