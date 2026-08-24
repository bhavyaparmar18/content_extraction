"""Document detail endpoints — retrieve parsed content by document_id."""

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from fastapi import APIRouter, Depends
from loguru import logger

from app.config.settings import Settings, get_settings
from app.core.exceptions import AppError, DocumentNotFoundError, ParsingError
from app.services.parser import ParserFactory
from app.services.extraction import TableExtractor, CrossPageTableStitcher, IconExtractor, CaptionExtractor
from app.services.hierarchy.ast_builder import ASTBuilder
from app.services.chunking.hierarchical import HierarchicalChunker
from app.services.chunking.semantic import SemanticChunker
from app.services.chunking.validator import ChunkValidator
from app.schemas.document import DocumentOutput

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.get("/{document_id}")
async def get_document(
    document_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return the full parsed RawDocument as JSON for inspection."""

    with logger.contextualize(document_id=document_id), _pipeline_errors(document_id):
        logger.info("Fetching raw parsed document '{d}'.", d=document_id)
        upload_path = _find_upload(document_id, settings)

        factory = ParserFactory(settings=settings)
        parser = factory.get_parser(str(upload_path))
        raw_document = parser.parse(str(upload_path))

        return raw_document.model_dump()


@router.get("/{document_id}/elements")
async def get_document_elements(
    document_id: str,
    page: int | None = None,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return a flat list of all extracted elements, optionally filtered
    by page number.
    """

    with logger.contextualize(document_id=document_id), _pipeline_errors(document_id):
        logger.info("Fetching elements for '{d}' (page={p}).", d=document_id, p=page)
        upload_path = _find_upload(document_id, settings)

        factory = ParserFactory(settings=settings)
        parser = factory.get_parser(str(upload_path))
        raw_document = parser.parse(str(upload_path))

        elements = []
        for pg in raw_document.pages:
            if page is not None and pg.page_number != page:
                continue
            for el in pg.elements:
                elements.append(el.model_dump())

        return {
            "document_id": document_id,
            "total_elements": len(elements),
            "page_filter": page,
            "elements": elements,
        }


@router.get("/{document_id}/tree")
async def get_document_tree(
    document_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return the nested hierarchical structure of the document."""

    with logger.contextualize(document_id=document_id), _pipeline_errors(document_id):
        logger.info("Building tree for '{d}'.", d=document_id)
        upload_path = _find_upload(document_id, settings)

        factory = ParserFactory(settings=settings)
        parser = factory.get_parser(str(upload_path))
        raw_document = parser.parse(str(upload_path))

        extractors = [
            TableExtractor(settings=settings),
            CrossPageTableStitcher(settings=settings),
            IconExtractor(settings=settings),
            CaptionExtractor(settings=settings),
        ]
        for extractor in extractors:
            raw_document = extractor.extract(raw_document)

        ast_builder = ASTBuilder(settings=settings)
        document_node = ast_builder.build(raw_document)

        return document_node.model_dump()


@router.get("/{document_id}/chunks")
async def get_document_chunks(
    document_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Return the document split into refined chunks."""

    with logger.contextualize(document_id=document_id), _pipeline_errors(document_id):
        logger.info("Chunking '{d}'.", d=document_id)
        upload_path = _find_upload(document_id, settings)

        factory = ParserFactory(settings=settings)
        parser = factory.get_parser(str(upload_path))
        raw_document = parser.parse(str(upload_path))

        extractors = [
            TableExtractor(settings=settings),
            CrossPageTableStitcher(settings=settings),
            IconExtractor(settings=settings),
            CaptionExtractor(settings=settings),
        ]
        for extractor in extractors:
            raw_document = extractor.extract(raw_document)

        ast_builder = ASTBuilder(settings=settings)
        document_node = ast_builder.build(raw_document)

        hierarchical_chunker = HierarchicalChunker(settings=settings)
        chunks = hierarchical_chunker.chunk(document_node)

        semantic_chunker = SemanticChunker(settings=settings)
        refined_chunks = semantic_chunker.chunk(chunks)

        validator = ChunkValidator(settings=settings)
        is_valid, warnings = validator.validate(refined_chunks)

        doc_output = DocumentOutput(
            document_id=document_id,
            title=document_node.doc_metadata.title or upload_path.stem,
            chunks=refined_chunks,
            validation_passed=is_valid,
            validation_warnings=warnings,
        )

        return doc_output.model_dump()


@router.get("/v2/{document_id}/json")
async def get_document_json_v2(
    document_id: str,
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    """Export the fully processed document AST as JSON (v2).

    This retrieves the completed extraction from the background job queue's
    saved disk output.
    """
    with logger.contextualize(document_id=document_id):
        output_path = settings.output_dir / f"{document_id}_v2.json"

        if not output_path.exists():
            raise DocumentNotFoundError(
                f"v2 JSON for document '{document_id}' not found. Did the job complete?"
            )

        try:
            return json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            logger.exception("Failed to read v2 JSON for '{d}'.", d=document_id)
            raise ParsingError(
                f"Stored v2 JSON for '{document_id}' could not be read.", detail=str(e)
            )


# ── Helpers ──────────────────────────────────────────────────────────────

@contextmanager
def _pipeline_errors(document_id: str) -> Iterator[None]:
    """Map on-demand parse/extraction failures to consistent HTTP errors + logs.

    ``AppError`` subclasses (e.g. 404) pass through unchanged; ``ValueError``
    (unsupported format, bad structure) becomes a 422 ParsingError; anything
    else is logged with a traceback and re-raised for the global 500 handler.
    """
    try:
        yield
    except AppError:
        raise
    except ValueError as e:
        logger.warning("Cannot process '{d}': {e}", d=document_id, e=e)
        raise ParsingError(f"Could not process document '{document_id}'.", detail=str(e))
    except Exception:  # noqa: BLE001
        logger.exception("Unexpected failure processing '{d}'.", d=document_id)
        raise


def _find_upload(document_id: str, settings: Settings) -> Path:
    """Locate the uploaded file for *document_id* or raise 404."""
    for ext in settings.allowed_extensions:
        candidate = settings.upload_dir / f"{document_id}{ext}"
        if candidate.exists():
            return candidate

    raise DocumentNotFoundError(
        f"No uploaded file found for document_id '{document_id}'."
    )
