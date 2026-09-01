"""FastAPI router for document migration endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, status
from fastapi.responses import FileResponse, JSONResponse
from loguru import logger

from app.config.settings import Settings, get_settings
from app.schemas.migration import DocxMigrationOutput
from app.services.llm.chain_factory import ChainFactory
from app.services.migration.docx_migrator import DocxMigrator
from app.services.migration.schemas import MigrationResult


router = APIRouter(prefix="/documents", tags=["Migration"])


@router.post("/migrate", response_model=MigrationResult)
async def migrate_document(
    request: Request,
    document_id: str = Form(...),
    template_file: Optional[UploadFile] = File(None),
    settings: Settings = Depends(get_settings),
):
    """Migrate an extracted document JSON into a .docx template.

    - **document_id**: ID of previously extracted document.
    - **template_file**: Optional custom .docx template file. If omitted, uses default template.
    """
    logger.info(f"Migration request received for document_id='{document_id}'")

    # Locate extracted JSON
    json_path = settings.output_dir / f"{document_id}.json"
    if not json_path.exists():
        # Try matching files starting with or containing document_id
        candidates = list(settings.output_dir.glob(f"*{document_id}*.json"))
        if candidates:
            json_path = candidates[0]
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Extracted JSON not found for document_id '{document_id}' in {settings.output_dir}",
            )

    # Load extracted JSON into DocxMigrationOutput
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        extracted = DocxMigrationOutput.model_validate(raw_data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to parse extracted JSON '{json_path.name}': {exc}",
        )

    # Handle template file
    if template_file and template_file.filename:
        template_save_path = settings.migration_template_dir / f"upload_{template_file.filename}"
        with open(template_save_path, "wb") as f:
            content = await template_file.read()
            f.write(content)
        target_template_path = template_save_path
    else:
        # Look for default template in templates dir
        templates = list(settings.migration_template_dir.glob("*.docx"))
        if templates:
            target_template_path = templates[0]
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No template_file provided and no default .docx found in data/templates/",
            )

    output_docx_path = settings.migration_output_dir / f"migrated_{document_id}.docx"
    plan_save_path = settings.migration_output_dir / f"plan_{document_id}.json"
    qa_save_path = settings.migration_output_dir / f"qa_{document_id}.json"

    # Get or create ChainFactory from app state
    chain_factory = getattr(request.app.state, "chain_factory", None)
    if chain_factory is None:
        chain_factory = ChainFactory(settings)

    migrator = DocxMigrator(settings, chain_factory)

    try:
        result = await migrator.migrate(
            extracted=extracted,
            template_path=target_template_path,
            output_path=output_docx_path,
        )

        # Save plan and QA report for persistent retrieval
        with open(plan_save_path, "w", encoding="utf-8") as f:
            json.dump(result.plan.model_dump(), f, indent=2)

        with open(qa_save_path, "w", encoding="utf-8") as f:
            json.dump(result.qa_report.model_dump(), f, indent=2)

        return result

    except Exception as exc:
        logger.exception(f"Migration failed for '{document_id}': {exc}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Migration execution failed: {exc}",
        )


@router.get("/{document_id}/migration-plan")
async def get_migration_plan(
    document_id: str,
    settings: Settings = Depends(get_settings),
):
    """Retrieve the LLM-generated MigrationPlan for a document."""
    plan_path = settings.migration_output_dir / f"plan_{document_id}.json"
    if not plan_path.exists():
        candidates = list(settings.migration_output_dir.glob(f"plan_*{document_id}*.json"))
        if candidates:
            plan_path = candidates[0]
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Migration plan not found for document_id '{document_id}'",
            )

    with open(plan_path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/{document_id}/migration-status")
async def get_migration_status(
    document_id: str,
    settings: Settings = Depends(get_settings),
):
    """Retrieve migration status and QA report for a document."""
    qa_path = settings.migration_output_dir / f"qa_{document_id}.json"
    if not qa_path.exists():
        candidates = list(settings.migration_output_dir.glob(f"qa_*{document_id}*.json"))
        if candidates:
            qa_path = candidates[0]
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"QA report not found for document_id '{document_id}'",
            )

    with open(qa_path, "r", encoding="utf-8") as f:
        return json.load(f)


@router.get("/{document_id}/download-docx")
async def download_migrated_docx(
    document_id: str,
    settings: Settings = Depends(get_settings),
):
    """Download the final migrated .docx file."""
    docx_path = settings.migration_output_dir / f"migrated_{document_id}.docx"
    if not docx_path.exists():
        candidates = list(settings.migration_output_dir.glob(f"migrated_*{document_id}*.docx"))
        if candidates:
            docx_path = candidates[0]
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Migrated .docx not found for document_id '{document_id}'",
            )

    return FileResponse(
        path=docx_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=docx_path.name,
    )
