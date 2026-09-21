"""Template management API endpoints — upload, extract, inspect, and delete templates."""

import json
from pathlib import Path
from typing import Optional, Any

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Request
from fastapi.responses import FileResponse
from loguru import logger

from app.config.settings import Settings, get_settings
from app.core.exceptions import NotFoundError, ValidationError
from app.schemas.template import (
    TemplateExtractResponse,
    TemplateListItem,
    TemplateUploadResponse,
)
from app.services.extraction.metadata_extractor import SOPMetadataExtractor
from app.services.extraction.template_extractor import TemplateExtractionService
from app.stores.template_store import TemplateStore

router = APIRouter(prefix="/templates", tags=["Templates"])


def _get_template_store(request: Request, settings: Settings) -> TemplateStore:
    """Retrieve TemplateStore from app state or instantiate fallback."""
    store = getattr(request.app.state, "template_store", None)
    if store is None:
        db_path = settings.project_root / "data" / "template_records.db"
        store = TemplateStore(db_path, settings)
    return store


def _resolve_template_record(store: TemplateStore, template_id: str) -> dict[str, Any]:
    """Find record by numeric id or template_uid."""
    record = None
    if template_id.isdigit():
        record = store.get_record_by_id(int(template_id))
    if record is None:
        record = store.get_record_by_uid(template_id)
    if record is None:
        raise NotFoundError(
            f"Template '{template_id}' not found",
            code="TEMPLATE_NOT_FOUND",
        )
    return record


_ASSET_PATH_KEYS = ("image_path", "icon_path", "path")


def _rewrite_template_asset_paths(node: Any, template_id: str) -> Any:
    """Rewrite absolute on-disk asset paths to servable URLs."""
    if isinstance(node, dict):
        for key in _ASSET_PATH_KEYS:
            value = node.get(key)
            if isinstance(value, str) and value:
                node[key] = f"/templates/{template_id}/assets/{Path(value).name}"
        for value in node.values():
            _rewrite_template_asset_paths(value, template_id)
    elif isinstance(node, list):
        for item in node:
            _rewrite_template_asset_paths(item, template_id)
    return node


@router.post("/upload", response_model=TemplateUploadResponse)
async def upload_template(
    request: Request,
    file: UploadFile = File(...),
    template_name: Optional[str] = Form(None),
    settings: Settings = Depends(get_settings),
):
    """Upload a template .docx file, validate, and register in the database."""
    if not file.filename:
        raise ValidationError("Filename is required.", code="FILENAME_REQUIRED")

    extension = Path(file.filename).suffix.lower()
    if extension not in settings.template_allowed_extensions:
        raise ValidationError(
            f"Unsupported template file type '{extension}'. Allowed: {settings.template_allowed_extensions}",
            code="UNSUPPORTED_TEMPLATE_FILE_TYPE",
        )

    contents = await file.read()
    size_bytes = len(contents)
    if size_bytes == 0:
        raise ValidationError("Uploaded template file is empty.", code="EMPTY_TEMPLATE_FILE")

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise ValidationError(
            f"Template file size ({size_bytes / (1024*1024):.1f} MB) exceeds maximum allowed ({settings.max_upload_size_mb} MB).",
            code="TEMPLATE_FILE_TOO_LARGE",
        )

    template_store = _get_template_store(request, settings)

    raw_stem = Path(file.filename).stem
    template_uid = SOPMetadataExtractor.sanitize_string(raw_stem)
    display_name = template_name.strip() if template_name and template_name.strip() else raw_stem

    next_version = template_store.get_next_version(template_uid)
    save_filename = f"{template_uid}_v{next_version}{extension}"
    save_path = settings.template_upload_dir / save_filename

    save_path.parent.mkdir(parents=True, exist_ok=True)
    save_path.write_bytes(contents)

    record = template_store.upsert_record(
        template_uid=template_uid,
        template_name=display_name,
        file_type="docx",
        file_size_bytes=size_bytes,
        source_filename=file.filename,
        upload_path=str(save_path),
        status="uploaded",
    )

    already_uploaded = next_version > 1

    return TemplateUploadResponse(
        template_id=template_uid,
        template_name=display_name,
        template_version=next_version,
        file_type="docx",
        size_bytes=size_bytes,
        already_uploaded=already_uploaded,
        message="Template uploaded successfully. Ready for extraction.",
    )


@router.post("/{template_id}/extract", response_model=TemplateExtractResponse)
async def extract_template(
    template_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """Run full extraction pipeline on an uploaded template."""
    template_store = _get_template_store(request, settings)
    record = _resolve_template_record(template_store, template_id)

    record_id = record["id"]
    template_uid = record["template_uid"]
    version = record["template_version"]

    if record.get("status") == "extracting":
        raise HTTPException(status_code=409, detail=f"Template '{template_id}' is already extracting.")

    upload_path_str = record.get("upload_path")
    if not upload_path_str or not Path(upload_path_str).exists():
        raise NotFoundError(f"Uploaded template file missing at {upload_path_str}", code="TEMPLATE_FILE_NOT_FOUND")

    template_store.update_status(record_id, "extracting")

    try:
        service = TemplateExtractionService(settings=settings)
        extraction_output = await service.extract(
            template_id=template_uid,
            upload_path=Path(upload_path_str),
            template_name=record.get("template_name"),
        )

        output_json_path = settings.template_output_dir / f"{template_uid}_v{version}.json"
        output_json_path.parent.mkdir(parents=True, exist_ok=True)

        clean_dict = extraction_output.to_clean_dict()
        with open(output_json_path, "w", encoding="utf-8") as f:
            json.dump(clean_dict, f, indent=2)

        global_rules_json = json.dumps(extraction_output.global_rules.to_clean_dict())

        total_sections = len(extraction_output.sections)
        total_elements = sum(len(sec.elements) for sec in extraction_output.sections)

        template_store.update_extraction_results(
            record_id=record_id,
            output_path=str(output_json_path),
            total_sections=total_sections,
            total_elements=total_elements,
            total_instructions=extraction_output.total_instructions,
            total_icons=extraction_output.total_icons,
            global_rules_json=global_rules_json,
            status="ready",
        )

        return TemplateExtractResponse(
            template_id=template_uid,
            status="ready",
            total_sections=total_sections,
            total_elements=total_elements,
            total_instructions=extraction_output.total_instructions,
            total_icons=extraction_output.total_icons,
            global_rules_count=len(extraction_output.global_rules.instructions),
            message="Template extracted successfully.",
        )

    except Exception as e:
        logger.error(f"Template extraction failed for {template_id}: {e}", exc_info=True)
        template_store.update_status(record_id, "failed")
        raise HTTPException(status_code=500, detail=f"Template extraction failed: {str(e)}")


@router.get("", response_model=list[TemplateListItem])
@router.get("/", response_model=list[TemplateListItem])
async def list_templates(
    status: Optional[str] = None,
    request: Request = None,
    settings: Settings = Depends(get_settings),
):
    """List templates, optionally filtered by status. Always returns newest first."""
    template_store = _get_template_store(request, settings)
    records = template_store.get_records(status=status)

    return [
        TemplateListItem(
            id=r["id"],
            template_uid=r["template_uid"],
            template_name=r["template_name"],
            template_version=r["template_version"],
            total_sections=r["total_sections"],
            total_instructions=r["total_instructions"],
            total_icons=r["total_icons"],
            status=r["status"],
            created_at=r["created_at"],
        )
        for r in records
    ]


@router.get("/{template_id}")
async def get_template(
    template_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """Retrieve template record metadata."""
    template_store = _get_template_store(request, settings)
    return _resolve_template_record(template_store, template_id)


@router.get("/{template_id}/content")
async def get_template_content(
    template_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """Retrieve full extracted template content JSON with servable asset URLs."""
    template_store = _get_template_store(request, settings)
    record = _resolve_template_record(template_store, template_id)

    output_path = record.get("output_path")
    if not output_path or not Path(output_path).exists():
        raise NotFoundError(
            f"Extracted content for template '{template_id}' not found. Run extraction first.",
            code="TEMPLATE_CONTENT_NOT_FOUND",
        )

    with open(output_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Rewrite asset paths to servable endpoints
    rewritten = _rewrite_template_asset_paths(data, record["template_uid"])
    return rewritten


@router.get("/{template_id}/global-rules")
async def get_template_global_rules(
    template_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """Retrieve only the global rules (blue-font instructions before first section)."""
    template_store = _get_template_store(request, settings)
    record = _resolve_template_record(template_store, template_id)

    rules_str = record.get("global_rules_json")
    if rules_str:
        try:
            return json.loads(rules_str)
        except Exception:
            pass

    # Fallback to output JSON
    output_path = record.get("output_path")
    if output_path and Path(output_path).exists():
        with open(output_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("global_rules", {"instructions": []})

    return {"instructions": []}


@router.get("/{template_id}/assets/{filename}")
async def get_template_asset(
    template_id: str,
    filename: str,
    settings: Settings = Depends(get_settings),
):
    """Serve extracted template images or icons."""
    safe_name = Path(filename).name

    img_path = settings.get_template_image_dir(template_id) / safe_name
    if img_path.exists() and img_path.is_file():
        return FileResponse(path=str(img_path), media_type="image/png")

    icon_path = settings.get_template_icon_dir(template_id) / safe_name
    if icon_path.exists() and icon_path.is_file():
        return FileResponse(path=str(icon_path), media_type="image/png")

    raise NotFoundError(
        f"Asset '{safe_name}' not found for template '{template_id}'",
        code="ASSET_NOT_FOUND",
    )


@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    """Delete a template record and clean up associated files."""
    template_store = _get_template_store(request, settings)
    record = _resolve_template_record(template_store, template_id)

    record_id = record["id"]
    deleted = template_store.delete_record(record_id)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete template record.")

    return {
        "deleted": True,
        "template_id": template_id,
        "message": f"Template '{template_id}' successfully deleted.",
    }
