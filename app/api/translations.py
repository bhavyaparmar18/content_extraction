"""Translation API (docs/translation/IMPLEMENTATION_PLAN.md): languages and per-language glossaries (Phase T2).

Glossaries are optional on a translation job. Without one the LLM translates
freely; with one its terms are mandatory.
"""

from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.api.auth import require_user
from app.config.settings import Settings, get_settings
from app.core.exceptions import AppError, NotFoundError, ValidationError
from app.schemas.auth import ApiFieldError
from app.schemas.v2.translation import GlossaryEntry
from app.services.extraction.metadata_extractor import SOPMetadataExtractor
from app.services.translation import glossary_service
from app.services.translation.glossary import GlossaryInvalid, parse_glossary_file, to_csv, to_xlsx
from app.services.translation.languages import LANGUAGES, get_language
from app.stores.glossary_store import GlossaryStore

router = APIRouter(prefix="/api/v1/translations", tags=["Translations"], dependencies=[Depends(require_user)])

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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


def _resolve(store: GlossaryStore, glossary: str, version: Optional[int] = None) -> dict[str, Any]:
    """A glossary by numeric record id, or by glossary_id (latest version unless one is given)."""
    record = store.get_record_by_id(int(glossary)) if glossary.isdigit() else None
    if record is None:
        record = store.get_version(glossary, version) if version is not None else store.get_latest(glossary)
    if record is None:
        raise NotFoundError(f"Glossary '{glossary}' not found", code="GLOSSARY_NOT_FOUND")
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
