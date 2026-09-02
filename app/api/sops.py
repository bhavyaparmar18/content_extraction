"""Endpoints for the persistent SOP records store (review status tracking)."""

import shutil
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Response, status
from loguru import logger

from app.config.settings import Settings, get_settings
from app.core import sop_store
from app.core.exceptions import SopRecordNotFoundError
from app.schemas.sop import SopRecord, SopStatus, SopStatusUpdate, SopListResponse

router = APIRouter(prefix="/sops", tags=["SOP Records"])


@router.get("", response_model=SopListResponse, response_model_by_alias=True)
async def list_sop_records(
    status: Optional[SopStatus] = None,
    document_uid: Optional[str] = Query(None, alias="document_Uid"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> SopListResponse:
    """List SOP extraction-run records, newest first."""
    rows = sop_store.list_records(
        status=status.value if status else None,
        document_uid=document_uid,
        limit=limit,
        offset=offset,
    )
    records = [SopRecord.model_validate(row) for row in rows]
    logger.info("Listed {n} SOP record(s).", n=len(records))
    return SopListResponse(count=len(records), records=records)


@router.get("/{record_id}", response_model=SopRecord, response_model_by_alias=True)
async def get_sop_record(record_id: int) -> SopRecord:
    """Fetch a single SOP record by its surrogate id."""
    row = sop_store.get_record(record_id)
    if row is None:
        raise SopRecordNotFoundError(f"No SOP record with id '{record_id}'.")
    return SopRecord.model_validate(row)


@router.patch("/{record_id}/status", response_model=SopRecord, response_model_by_alias=True)
async def update_sop_record_status(record_id: int, payload: SopStatusUpdate) -> SopRecord:
    """Update a SOP record's review status (in_review / approved / rejected)."""
    row = sop_store.update_status(record_id, payload.status.value)
    if row is None:
        raise SopRecordNotFoundError(f"No SOP record with id '{record_id}'.")
    logger.info("SOP record '{id}' status -> '{s}'.", id=record_id, s=payload.status.value)
    return SopRecord.model_validate(row)


def _cleanup_document_files(record: dict[str, Any], settings: Settings) -> None:
    """Best-effort removal of all files/dirs for a document with no remaining SOP records.

    The upload file and output JSON are named deterministically from
    ``document_uid`` only (no version in the filename), so this must only be
    called once the caller has confirmed no sibling row still references the
    same document. Failures here are logged, never raised: the DB row is
    already gone (the source of truth for the UI), so a stray file left on
    disk is a minor cleanup miss, not a user-facing failure.
    """
    document_uid = record["document_uid"]
    file_type = (record.get("file_type") or "").lower()

    if file_type:
        upload_path = settings.upload_dir / f"{document_uid}.{file_type}"
        try:
            upload_path.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("Cleanup: failed to remove upload file '{p}': {e}", p=upload_path, e=e)

    output_path = settings.output_dir / f"{document_uid}_v2.json"
    try:
        output_path.unlink(missing_ok=True)
    except OSError as e:
        logger.warning("Cleanup: failed to remove output JSON '{p}': {e}", p=output_path, e=e)

    for asset_dir in (settings.extracted_images_dir / document_uid, settings.extracted_icons_dir / document_uid):
        try:
            shutil.rmtree(asset_dir)
        except FileNotFoundError:
            pass
        except OSError as e:
            logger.warning("Cleanup: failed to remove directory '{p}': {e}", p=asset_dir, e=e)


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sop_record(record_id: int, settings: Settings = Depends(get_settings)) -> Response:
    """Delete a SOP record.

    If no other row still references the same document (across all
    gpdat_versions), this also best-effort deletes the uploaded file, output
    JSON, and extracted image/icon directories for that document.
    """
    deleted = sop_store.delete_record(record_id)
    if deleted is None:
        raise SopRecordNotFoundError(f"No SOP record with id '{record_id}'.")

    document_uid = deleted["document_uid"]
    remaining = sop_store.count_records_for_document(document_uid)
    if remaining == 0:
        _cleanup_document_files(deleted, settings)
        logger.info(
            "Deleted SOP record '{id}' ({doc}) and cleaned up its files.",
            id=record_id, doc=document_uid,
        )
    else:
        logger.info(
            "Deleted SOP record '{id}' ({doc}); {n} other version(s) remain, files kept.",
            id=record_id, doc=document_uid, n=remaining,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
