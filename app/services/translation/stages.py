"""Stage functions run by the translation orchestrator, one per working status (as ``migration_v2/stages.py``).

A stage receives a ``TranslationStageContext`` and may return a status to go to instead of the default next one.
A stage must be safe to re-run: after a crash or a retry it runs again and writes the next artifact versions.

PREPARING (Phase T4) snapshots the completed migration's English final document into the job and cuts it into
segments. TRANSLATING, CHECKING, REPAIRING (T5) and RENDERING (T6) come later; until then a job waits at TRANSLATING.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from app.schemas.v2 import ArtifactKind, SegmentSet, TranslationJob, TranslationStatus
from app.services.migration_v2.artifacts import ArtifactWriter
from app.services.migration_v2.export import EXPORTABLE, ExportBlocked, render_final

from . import glossary_service
from .languages import get_language
from .segments import build_segments
from .template_text import harvest_hook

SYSTEM_ACTOR = "system"
ENGLISH = "english"  # scope of the English final document's snapshot artifacts


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

    def write(self, kind: ArtifactKind, payload, scope: Optional[str] = None):
        return self.artifacts.write(self.job.job_id, kind, payload, scope=scope, created_by=SYSTEM_ACTOR)

    def write_file(self, kind: ArtifactKind, data: bytes, suffix: str, scope: Optional[str] = None):
        return self.artifacts.write_file(self.job.job_id, kind, data, suffix, scope=scope, created_by=SYSTEM_ACTOR)

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
        self.store.add_event(self.job.job_id, event, SYSTEM_ACTOR, detail)


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


def default_stages() -> dict[TranslationStatus, Stage]:
    return {TranslationStatus.PREPARING: preparing}
