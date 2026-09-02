"""Upload endpoint — receives PDF / DOCX files and stores them."""

import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Depends, Request
from loguru import logger

from app.config.settings import Settings, get_settings
from app.core import sop_store
from app.core.exceptions import BadRequestError
from app.schemas.jobs import BatchJob, RejectedFile
from app.services.extraction.metadata_extractor import SOPMetadataExtractor

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post("/upload/batch", response_model=BatchJob)
async def upload_documents_batch(
    request: Request,
    files: list[UploadFile] = File(...),
    settings: Settings = Depends(get_settings),
):
    """Accept multiple PDF or DOCX file uploads, validate, and enqueue a batch job.

    Each file is validated independently: invalid files are logged with a reason
    and reported back in ``rejected_files`` instead of silently dropped. The batch
    only fails (400) if *no* file survives validation.
    """
    document_ids: list[str] = []
    rejected: list[RejectedFile] = []
    logger.info("Batch upload received: {n} file(s).", n=len(files))

    for file in files:
        filename = file.filename or "<unnamed>"
        with logger.contextualize(filename=filename):
            # 1. Filename present
            if not file.filename:
                logger.warning("Rejected a file: missing filename.")
                rejected.append(RejectedFile(filename=filename, reason="Missing filename"))
                continue

            # 2. Supported extension
            extension = Path(file.filename).suffix.lower()
            if extension not in settings.allowed_extensions:
                logger.warning(
                    "Rejected '{f}': unsupported extension '{e}' (allowed: {a}).",
                    f=filename, e=extension, a=settings.allowed_extensions,
                )
                rejected.append(RejectedFile(
                    filename=filename,
                    reason=f"Unsupported file type '{extension}'. Allowed: {settings.allowed_extensions}",
                ))
                continue

            # 3. Readable content
            try:
                contents = await file.read()
            except Exception as e:  # noqa: BLE001
                logger.exception("Rejected '{f}': could not read contents.", f=filename)
                rejected.append(RejectedFile(filename=filename, reason=f"Could not read file: {e}"))
                continue

            # 4. Size checks
            size_bytes = len(contents)
            max_bytes = settings.max_upload_size_mb * 1024 * 1024
            if size_bytes == 0:
                logger.warning("Rejected '{f}': empty file.", f=filename)
                rejected.append(RejectedFile(filename=filename, reason="File is empty"))
                continue
            if size_bytes > max_bytes:
                logger.warning(
                    "Rejected '{f}': {mb:.2f} MB exceeds {limit} MB limit.",
                    f=filename, mb=size_bytes / 1024 / 1024, limit=settings.max_upload_size_mb,
                )
                rejected.append(RejectedFile(
                    filename=filename,
                    reason=f"File exceeds {settings.max_upload_size_mb} MB limit",
                ))
                continue

            # 5. Metadata extraction + persist
            temp_path = settings.temp_dir / f"temp_{uuid.uuid4()}{extension}"
            try:
                temp_path.write_bytes(contents)
                doc_title, doc_name, doc_num, doc_ver, _ = SOPMetadataExtractor.extract_from_file(
                    str(temp_path), fallback_filename=file.filename
                )
                # document_id generation only knows a single "name" slot; fall back to
                # the title so documents identified only by title keep a stable id.
                document_id = SOPMetadataExtractor.generate_document_id(
                    doc_name or doc_title, doc_num, doc_ver, fallback_filename=file.filename
                )
                # Preview the version this upload will become once processed. The
                # authoritative value is (re)computed from sop_records history at
                # parse time; this is purely informational for the log line.
                try:
                    next_version = sop_store.next_version(document_id)
                except Exception:  # noqa: BLE001 - store may not be ready; not fatal
                    next_version = 1

                dest = settings.upload_dir / f"{document_id}{extension}"
                dest.write_bytes(contents)
                document_ids.append(document_id)

                logger.info(
                    "Accepted '{f}' → document_id '{d}' ({kb:.1f} KB){dup}.",
                    f=filename, d=document_id, kb=size_bytes / 1024,
                    dup=f", re-upload (version #{next_version})" if next_version > 1 else "",
                )
            except Exception as e:  # noqa: BLE001
                logger.exception("Rejected '{f}': processing failed.", f=filename)
                rejected.append(RejectedFile(filename=filename, reason=f"Processing failed: {e}"))
                continue
            finally:
                temp_path.unlink(missing_ok=True)

    if not document_ids:
        # Per-file reasons were already logged above; the central AppError handler
        # logs the aggregated failure, so we just raise here without re-logging.
        reasons = "; ".join(f"{r.filename}: {r.reason}" for r in rejected) or "no files provided"
        raise BadRequestError(
            "No valid files were uploaded in the batch.",
            detail=reasons,
        )

    job_manager = request.app.state.job_manager
    job = job_manager.create_batch_job(document_ids)
    job.rejected_files = rejected
    logger.info(
        "Batch job '{jid}' created: {a} accepted, {r} rejected.",
        jid=job.job_id, a=len(document_ids), r=len(rejected),
    )
    return job
