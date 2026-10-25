"""Translation API (docs/translation/IMPLEMENTATION_PLAN.md): languages, glossaries, language templates and jobs.

Both resources are per language and optional on a translation job:
- a glossary (Phase T2): without one the LLM translates freely; with one its terms are mandatory;
- a language template (Phase T3): its first page, headers and footers replace the English ones; without one the
  English front matter is kept.

A translation job (Phase T4) is one language of a completed migration; ``POST /translations`` starts one per
language. Its segments carry their translations once translated, and ``/validation`` serves the QA checks (T5).
Once rendered (T6), ``/export/preview`` serves the translated document and ``/render-report`` its render.
"""

from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi import Path as PathParam
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.api.auth import require_user
from app.config.settings import Settings, get_settings
from app.core.exceptions import AppError, NotFoundError, ValidationError
from app.schemas.auth import ApiFieldError
from app.schemas.v2 import (
    ArtifactKind,
    QualityReport,
    RenderReport,
    SegmentSet,
    TranslationJob,
    TranslationSet,
    TranslationStatus,
)
from app.schemas.v2.translation import GlossaryEntry
from app.services.extraction.metadata_extractor import SOPMetadataExtractor
from app.services.migration_v2.artifacts import ArtifactCorrupted
from app.services.migration_v2.orchestrator import JobStateError
from app.services.translation import glossary_service, job_service, language_template_service
from app.services.translation.glossary import GlossaryInvalid, parse_glossary_file, to_csv, to_xlsx
from app.services.translation.languages import LANGUAGES, get_language
from app.services.translation.orchestrator import TranslationOrchestrator
from app.services.translation.render import TRANSLATED
from app.services.translation.stages import CHECKS
from app.services.translation.translator import merged
from app.stores.glossary_store import GlossaryStore
from app.stores.language_template_store import LanguageTemplateStore

router = APIRouter(prefix="/api/v1/translations", tags=["Translations"], dependencies=[Depends(require_user)])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class EntriesUpdate(BaseModel):
    entries: list[GlossaryEntry] = Field(default_factory=list)
    style_notes: Optional[str] = None
    name: Optional[str] = None


def _actor(user: dict) -> Optional[str]:
    return str(user.get("userId")) if user and user.get("userId") is not None else None


def _glossary_store(request: Request, settings: Settings) -> GlossaryStore:
    store = getattr(request.app.state, "glossary_store", None)
    if store is None:
        store = GlossaryStore(settings.db_path, settings)
    return store


def _language_template_store(request: Request, settings: Settings) -> LanguageTemplateStore:
    store = getattr(request.app.state, "language_template_store", None)
    if store is None:
        store = LanguageTemplateStore(settings.db_path, settings)
    return store


def _resolve(store, key: str, version: Optional[int] = None) -> dict[str, Any]:
    """A record by numeric record id, or by its glossary_id / template_id (latest version unless one is given)."""
    record = store.get_record_by_id(int(key)) if key.isdigit() else None
    if record is None:
        record = store.get_version(key, version) if version is not None else store.get_latest(key)
    if record is None:
        code = "GLOSSARY_NOT_FOUND" if isinstance(store, GlossaryStore) else "LANGUAGE_TEMPLATE_NOT_FOUND"
        raise NotFoundError(f"{store.LABEL} '{key}' not found", code=code)
    return record


def _invalid(problems: list[str]) -> AppError:
    return AppError(
        status_code=422,
        code="GLOSSARY_INVALID",
        message=f"Glossary is invalid ({len(problems)} problem(s))",
        field_errors=[ApiFieldError(field="entries", code="invalid", message=p) for p in problems],
    )


def _language(code: str) -> str:
    try:
        return get_language(code).word_lang
    except ValueError as exc:
        raise ValidationError(str(exc), code="UNSUPPORTED_LANGUAGE") from exc


def _load(record: dict[str, Any]):
    try:
        return glossary_service.load(record)
    except FileNotFoundError as exc:
        raise NotFoundError(str(exc), code="GLOSSARY_ENTRIES_NOT_FOUND") from exc


# ── Languages ─────────────────────────────────────────────────────────


@router.get("/languages")
async def list_languages():
    return [{"code": lang.word_lang, "name": lang.name, "script": lang.script, "east_asian": lang.east_asian}
            for lang in LANGUAGES.values()]


# ── Glossaries ────────────────────────────────────────────────────────


@router.post("/glossaries")
async def create_glossary(
    request: Request,
    language: str = Form(...),
    file: Optional[UploadFile] = File(None),
    name: Optional[str] = Form(None),
    glossary_id: Optional[str] = Form(None),
    style_notes: Optional[str] = Form(None),
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_user),
):
    """Upload a glossary (.csv or .xlsx) as the next version, or start an empty one (no file).

    The version is ``glossary_id`` (default: from the name or file name). It is checked before anything is
    saved: a file with any bad row is refused with every problem listed.
    """
    language = _language(language)
    upload = None
    entries: list[GlossaryEntry] = []
    notes = (style_notes or "").strip() or None
    stem = ""
    if file is not None and file.filename:
        extension = Path(file.filename).suffix.lower()
        if extension not in settings.glossary_allowed_extensions:
            raise ValidationError(
                f"Unsupported glossary file type '{extension}'. Allowed: {settings.glossary_allowed_extensions}",
                code="UNSUPPORTED_GLOSSARY_FILE_TYPE",
            )
        contents = await file.read()
        if not contents:
            raise ValidationError("Uploaded glossary file is empty.", code="EMPTY_GLOSSARY_FILE")
        if len(contents) > settings.max_upload_size_mb * 1024 * 1024:
            raise ValidationError(f"Glossary file exceeds the maximum size of {settings.max_upload_size_mb} MB.",
                                  code="GLOSSARY_FILE_TOO_LARGE")
        try:
            parsed = parse_glossary_file(contents, file.filename, language)
        except GlossaryInvalid as exc:
            raise _invalid(exc.problems) from exc
        entries, notes = parsed.entries, notes or parsed.style_notes
        upload = (contents, file.filename)
        stem = Path(file.filename).stem

    display = (name or "").strip() or stem
    record_id = SOPMetadataExtractor.sanitize_string((glossary_id or "").strip() or display)
    if not record_id:
        raise ValidationError("Give the glossary a name or upload a file.", code="GLOSSARY_NAME_REQUIRED")
    store = _glossary_store(request, settings)
    try:
        return glossary_service.create_version(
            store, settings, glossary_id=record_id, name=display or record_id, language=language, entries=entries,
            style_notes=notes, created_by=_actor(user), upload=upload)
    except GlossaryInvalid as exc:
        raise _invalid(exc.problems) from exc
    except glossary_service.GlossaryLanguageMismatch as exc:
        raise AppError(status_code=409, code="GLOSSARY_LANGUAGE_MISMATCH", message=str(exc)) from exc


@router.get("/glossaries")
async def list_glossaries(
    request: Request,
    language: Optional[str] = None,
    status: Optional[str] = None,
    glossary_id: Optional[str] = None,
    settings: Settings = Depends(get_settings),
):
    return _glossary_store(request, settings).get_records(
        record_id=glossary_id, language=_language(language) if language else None, status=status)


@router.get("/glossaries/{glossary}")
async def get_glossary(request: Request, glossary: str, version: Optional[int] = None,
                       settings: Settings = Depends(get_settings)):
    return _resolve(_glossary_store(request, settings), glossary, version)


@router.get("/glossaries/{glossary}/entries")
async def get_entries(request: Request, glossary: str, version: Optional[int] = None,
                      settings: Settings = Depends(get_settings)):
    return _load(_resolve(_glossary_store(request, settings), glossary, version)).to_clean_dict()


@router.put("/glossaries/{glossary}/entries")
async def put_entries(
    request: Request,
    glossary: str,
    body: EntriesUpdate,
    version: Optional[int] = None,
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_user),
):
    """Save edited terms: in place while the version is in review, as the next version once it is approved."""
    store = _glossary_store(request, settings)
    record = _resolve(store, glossary, version)
    try:
        return glossary_service.save_entries(store, settings, record, body.entries, body.style_notes, body.name,
                                             created_by=_actor(user))
    except GlossaryInvalid as exc:
        raise _invalid(exc.problems) from exc


@router.post("/glossaries/{glossary}/approve")
async def approve_glossary(request: Request, glossary: str, version: Optional[int] = None,
                           settings: Settings = Depends(get_settings)):
    store = _glossary_store(request, settings)
    record = _resolve(store, glossary, version)
    try:
        return glossary_service.approve(store, record)
    except FileNotFoundError as exc:
        raise NotFoundError(str(exc), code="GLOSSARY_ENTRIES_NOT_FOUND") from exc


@router.get("/glossaries/{glossary}/export")
async def export_glossary(
    request: Request,
    glossary: str,
    version: Optional[int] = None,
    format: Literal["csv", "xlsx"] = "xlsx",
    settings: Settings = Depends(get_settings),
):
    record = _resolve(_glossary_store(request, settings), glossary, version)
    content = _load(record)
    filename = f"{record['glossary_id']}_v{record['version']}.{format}"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if format == "csv":
        return Response(("﻿" + to_csv(content)).encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers=headers)  # the BOM makes Excel read UTF-8
    return Response(to_xlsx(content), media_type=_XLSX, headers=headers)


@router.delete("/glossaries/{glossary}")
async def delete_glossary(request: Request, glossary: str, version: Optional[int] = None,
                          settings: Settings = Depends(get_settings)):
    store = _glossary_store(request, settings)
    record = _resolve(store, glossary, version)
    store.delete_record(record["id"])
    return {"deleted": True, "glossary_id": record["glossary_id"], "version": record["version"]}


# ── Language templates ────────────────────────────────────────────────


def _with_report(record: dict[str, Any]) -> dict[str, Any]:
    try:
        report = language_template_service.load_report(record).to_clean_dict()
    except FileNotFoundError:
        report = None
    return {**record, "report": report}


@router.post("/language-templates")
async def create_language_template(
    request: Request,
    language: str = Form(...),
    file: UploadFile = File(...),
    name: Optional[str] = Form(None),
    template_id: Optional[str] = Form(None),
    settings: Settings = Depends(get_settings),
    user: dict = Depends(require_user),
):
    """Upload a language template (.docx) as the next version and extract its first page, headers and footers.

    A template whose front matter cannot be extracted is still saved, as ``failed`` with the reason.
    """
    language = _language(language)
    extension = Path(file.filename or "").suffix.lower()
    if extension not in settings.language_template_allowed_extensions:
        raise ValidationError(
            f"Unsupported language template file type '{extension}'. "
            f"Allowed: {settings.language_template_allowed_extensions}",
            code="UNSUPPORTED_LANGUAGE_TEMPLATE_FILE_TYPE",
        )
    contents = await file.read()
    if not contents:
        raise ValidationError("Uploaded language template file is empty.", code="EMPTY_LANGUAGE_TEMPLATE_FILE")
    if len(contents) > settings.max_upload_size_mb * 1024 * 1024:
        raise ValidationError(f"Language template exceeds the maximum size of {settings.max_upload_size_mb} MB.",
                              code="LANGUAGE_TEMPLATE_FILE_TOO_LARGE")
    display = (name or "").strip() or Path(file.filename).stem
    record_id = SOPMetadataExtractor.sanitize_string((template_id or "").strip() or display)
    if not record_id:
        raise ValidationError("Give the language template a name.", code="LANGUAGE_TEMPLATE_NAME_REQUIRED")
    try:
        record = language_template_service.create_version(
            _language_template_store(request, settings), settings, template_id=record_id, name=display or record_id,
            language=language, data=contents, filename=file.filename, created_by=_actor(user))
    except language_template_service.LanguageTemplateLanguageMismatch as exc:
        raise AppError(status_code=409, code="LANGUAGE_TEMPLATE_LANGUAGE_MISMATCH", message=str(exc)) from exc
    return _with_report(record)


@router.get("/language-templates")
async def list_language_templates(
    request: Request,
    language: Optional[str] = None,
    status: Optional[str] = None,
    template_id: Optional[str] = None,
    settings: Settings = Depends(get_settings),
):
    return _language_template_store(request, settings).get_records(
        record_id=template_id, language=_language(language) if language else None, status=status)


@router.get("/language-templates/{template}")
async def get_language_template(request: Request, template: str, version: Optional[int] = None,
                                settings: Settings = Depends(get_settings)):
    return _resolve(_language_template_store(request, settings), template, version)


@router.get("/language-templates/{template}/report")
async def get_language_template_report(request: Request, template: str, version: Optional[int] = None,
                                       settings: Settings = Depends(get_settings)):
    record = _resolve(_language_template_store(request, settings), template, version)
    try:
        return language_template_service.load_report(record).to_clean_dict()
    except FileNotFoundError as exc:
        raise NotFoundError(str(exc), code="LANGUAGE_TEMPLATE_REPORT_NOT_FOUND") from exc


@router.get("/language-templates/{template}/preview")
async def get_language_template_preview(request: Request, template: str, version: Optional[int] = None,
                                        settings: Settings = Depends(get_settings)):
    """The extracted first page, headers and footers, with two placeholder body pages (.docx)."""
    record = _resolve(_language_template_store(request, settings), template, version)
    path = record.get("preview_path")
    if not path or not Path(path).exists():
        raise NotFoundError(f"Language template '{template}' has no preview",
                            code="LANGUAGE_TEMPLATE_PREVIEW_NOT_FOUND")
    return FileResponse(path, media_type=_DOCX,
                        filename=f"{record['template_id']}_v{record['version']}_front_matter_preview.docx")


@router.post("/language-templates/{template}/ready")
async def mark_language_template_ready(request: Request, template: str, version: Optional[int] = None,
                                       settings: Settings = Depends(get_settings)):
    store = _language_template_store(request, settings)
    record = _resolve(store, template, version)
    try:
        return language_template_service.mark_ready(store, record)
    except language_template_service.LanguageTemplateNotReady as exc:
        raise AppError(
            status_code=409, code="LANGUAGE_TEMPLATE_NOT_READY",
            message=f"Language template cannot be marked ready ({len(exc.reasons)} problem(s))",
            field_errors=[ApiFieldError(field="report", code="problem", message=r) for r in exc.reasons],
        ) from exc


@router.delete("/language-templates/{template}")
async def delete_language_template(request: Request, template: str, version: Optional[int] = None,
                                   settings: Settings = Depends(get_settings)):
    store = _language_template_store(request, settings)
    record = _resolve(store, template, version)
    store.delete_record(record["id"])
    return {"deleted": True, "template_id": record["template_id"], "version": record["version"]}


# ── Translation jobs (Phase T4) ───────────────────────────────────────
# Declared after the static routes above, so /languages, /glossaries and /language-templates match first.


class LanguageChoice(BaseModel):
    language: str
    glossary_id: Optional[str] = None
    glossary_version: Optional[int] = None
    language_template_id: Optional[str] = None
    language_template_version: Optional[int] = None


class CreateTranslationsRequest(BaseModel):
    migration_job_id: str
    languages: list[LanguageChoice] = Field(default_factory=list)


_JOB_ID = r"^TRN-[A-Za-z0-9-]+$"


def _orchestrator(request: Request) -> TranslationOrchestrator:
    orchestrator = getattr(request.app.state, "translation_orchestrator", None)
    if orchestrator is None:
        raise AppError(503, "TRANSLATIONS_UNAVAILABLE", "The translation orchestrator is not running")
    return orchestrator


def _job(orch: TranslationOrchestrator, job_id: str) -> TranslationJob:
    job = orch.store.get_job(job_id)
    if job is None:
        raise NotFoundError(f"Translation job '{job_id}' not found", code="TRANSLATION_NOT_FOUND")
    return job


def _view(orch: TranslationOrchestrator, job: TranslationJob) -> dict[str, Any]:
    data = job.to_clean_dict()
    data["running"] = orch.is_running(job.job_id)
    return data


@router.post("")
async def create_translations(request: Request, body: CreateTranslationsRequest, user: dict = Depends(require_user)):
    """Start one translation job per language of a completed migration (glossary and language template optional)."""
    orch = _orchestrator(request)
    try:
        resolved = job_service.resolve_request(
            orch.migrations, orch.glossaries, orch.language_templates, body.migration_job_id,
            [job_service.LanguageRequest(**choice.model_dump()) for choice in body.languages])
    except job_service.TranslationRequestError as exc:
        raise AppError(exc.status, exc.code, exc.message) from exc
    jobs = [orch.create(body.migration_job_id, r.language, r.glossary, r.language_template, created_by=_actor(user))
            for r in resolved]
    return [_view(orch, job) for job in jobs]


@router.get("")
async def list_translations(
    request: Request,
    migration_job_id: Optional[str] = None,
    language: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    orch = _orchestrator(request)
    return orch.store.list_jobs(status=status, migration_job_id=migration_job_id,
                                language=_language(language) if language else None, limit=limit, offset=offset)


@router.get("/{job_id}")
async def get_translation(request: Request, job_id: str = PathParam(..., pattern=_JOB_ID)):
    orch = _orchestrator(request)
    return _view(orch, _job(orch, job_id))


@router.post("/{job_id}/cancel")
async def cancel_translation(request: Request, job_id: str = PathParam(..., pattern=_JOB_ID),
                             user: dict = Depends(require_user)):
    orch = _orchestrator(request)
    _job(orch, job_id)
    try:
        return _view(orch, orch.cancel(job_id, _actor(user)))
    except JobStateError as exc:
        raise AppError(409, exc.code, exc.message) from exc


@router.post("/{job_id}/retry")
async def retry_translation(request: Request, job_id: str = PathParam(..., pattern=_JOB_ID),
                            from_stage: Optional[TranslationStatus] = None, user: dict = Depends(require_user)):
    orch = _orchestrator(request)
    _job(orch, job_id)
    try:
        return _view(orch, orch.retry(job_id, from_stage, _actor(user)))
    except JobStateError as exc:
        raise AppError(409, exc.code, exc.message) from exc


@router.get("/{job_id}/audit")
async def get_translation_audit(request: Request, job_id: str = PathParam(..., pattern=_JOB_ID)):
    orch = _orchestrator(request)
    _job(orch, job_id)
    return orch.store.list_events(job_id)


@router.get("/{job_id}/segments")
async def get_segments(request: Request, job_id: str = PathParam(..., pattern=_JOB_ID),
                       section: Optional[str] = None):
    """The document's segments with their latest translations (once translated); ``section`` is a target section
    id, ``xrefs`` or ``template``."""
    orch = _orchestrator(request)
    job = _job(orch, job_id)
    try:
        segments = orch.artifacts.latest(job, ArtifactKind.SEGMENTS, SegmentSet)
        if segments is not None:
            sets = [orch.artifacts.latest(job, ArtifactKind.TRANSLATION, TranslationSet, s) for s in segments.scopes]
            segments = merged(segments, [s for s in sets if s is not None])
    except ArtifactCorrupted as exc:
        raise AppError(500, "ARTIFACT_CORRUPTED", str(exc)) from exc
    if segments is None:
        raise NotFoundError(f"Job '{job_id}' has no segments yet", code="ARTIFACT_NOT_FOUND")
    data = segments.to_clean_dict()
    if section:
        data["segments"] = [s.to_clean_dict() for s in segments.scope(section)]
    data["counts"] = segments.counts
    data["scopes"] = segments.scopes
    return data


@router.get("/{job_id}/validation")
async def get_validation(request: Request, job_id: str = PathParam(..., pattern=_JOB_ID)):
    """The latest QA checks of the translation (``quality_report[translation]``)."""
    orch = _orchestrator(request)
    job = _job(orch, job_id)
    try:
        report = orch.artifacts.latest(job, ArtifactKind.QUALITY_REPORT, QualityReport, CHECKS)
    except ArtifactCorrupted as exc:
        raise AppError(500, "ARTIFACT_CORRUPTED", str(exc)) from exc
    if report is None:
        raise NotFoundError(f"Job '{job_id}' has not been checked yet", code="NO_VALIDATION")
    return report.to_clean_dict()


@router.get("/{job_id}/render-report")
async def get_render_report(request: Request, job_id: str = PathParam(..., pattern=_JOB_ID)):
    """The latest render of the translated document (``render_report[translated]``): its warnings (segments shown
    in English among them) and the post-render check's problems."""
    orch = _orchestrator(request)
    job = _job(orch, job_id)
    try:
        report = orch.artifacts.latest(job, ArtifactKind.RENDER_REPORT, RenderReport, TRANSLATED)
    except ArtifactCorrupted as exc:
        raise AppError(500, "ARTIFACT_CORRUPTED", str(exc)) from exc
    if report is None:
        raise NotFoundError(f"Job '{job_id}' has not been rendered yet", code="NO_RENDER")
    return report.to_clean_dict()


@router.get("/{job_id}/export/preview")
async def preview_translation(request: Request, job_id: str = PathParam(..., pattern=_JOB_ID)):
    """The latest translated document (``docx[translated]``) for viewing in the app; the approved export is T7's."""
    orch = _orchestrator(request)
    job = _job(orch, job_id)
    if orch.is_running(job_id):
        raise AppError(409, "JOB_RUNNING", f"Job {job_id} is running; preview once it has finished")
    ref = job.latest_artifact(ArtifactKind.DOCX, TRANSLATED)
    if ref is None:
        raise NotFoundError(f"Job '{job_id}' has not been rendered yet", code="NO_RENDER")
    try:
        data = orch.artifacts.read_bytes(ref)
    except ArtifactCorrupted as exc:
        raise AppError(500, "ARTIFACT_CORRUPTED", str(exc)) from exc
    name = f"{job_id}_{job.language.value}_v{ref.version}_preview.docx"
    return Response(data, media_type=_DOCX, headers={"Content-Disposition": f'inline; filename="{name}"'})
