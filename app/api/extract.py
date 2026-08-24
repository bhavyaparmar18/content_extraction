"""Extract endpoint — triggers the extraction pipeline for an uploaded document."""

from pathlib import Path

from fastapi import APIRouter, Depends
from loguru import logger
from pydantic import BaseModel

from app.config.settings import Settings, get_settings
from app.core.exceptions import DocumentNotFoundError, ParsingError
from app.services.parser import ParserFactory
from app.services.extraction import TableExtractor, CrossPageTableStitcher, IconExtractor, CaptionExtractor
from app.services.hierarchy.ast_builder import ASTBuilder

router = APIRouter(prefix="/documents", tags=["Documents"])


class ExtractRequest(BaseModel):
    """Payload for the extraction trigger."""
    document_id: str


class ExtractResponse(BaseModel):
    """Structured response after extraction completes."""
    document_id: str
    status: str
    title: str
    file_type: str
    page_count: int
    total_elements: int
    element_summary: dict[str, int]
    message: str


@router.post("/extract", response_model=ExtractResponse)
async def extract_document(
    request: ExtractRequest,
    settings: Settings = Depends(get_settings),
):
    """Run the parser on a previously uploaded document and return
    a summary of extracted elements.
    """

    document_id = request.document_id
    with logger.contextualize(document_id=document_id):
        logger.info("Synchronous extract requested for '{d}'.", d=document_id)

        # ── Locate the uploaded file ────────────────────────────────────
        upload_path: Path | None = None
        for ext in settings.allowed_extensions:
            candidate = settings.upload_dir / f"{document_id}{ext}"
            if candidate.exists():
                upload_path = candidate
                break

        if upload_path is None:
            raise DocumentNotFoundError(
                f"No uploaded file found for document_id '{document_id}'."
            )

        # ── Parse + extract + build AST ─────────────────────────────────
        try:
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

        except ValueError as e:
            logger.warning("Extraction rejected for '{d}': {e}", d=document_id, e=e)
            raise ParsingError(
                f"Could not parse document '{document_id}'.", detail=str(e)
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("Extraction failed unexpectedly for '{d}'.", d=document_id)
            raise ParsingError(
                f"Extraction failed for document '{document_id}'.", detail=str(e)
            )

    # ── Build summary ───────────────────────────────────────────────
    element_counts: dict[str, int] = {}
    total_elements = 0
    total_sections = 0
    
    # Helper to count sections and elements recursively
    def _traverse(node):
        nonlocal total_elements, total_sections
        
        if node.node_type == "section":
            total_sections += 1
            if hasattr(node, "heading") and node.heading:
                key = "heading"
                element_counts[key] = element_counts.get(key, 0) + 1
                total_elements += 1
                
        # Count node if it is not just a container (like document/section)
        if node.node_type not in ["document", "section", "heading"]:
            element_counts[node.node_type] = element_counts.get(node.node_type, 0) + 1
            total_elements += 1
            
        if hasattr(node, "children"):
            for child in getattr(node, "children", []):
                _traverse(child)
                
    _traverse(document_node)

    return ExtractResponse(
        document_id=request.document_id,
        status="completed",
        title=document_node.doc_metadata.title or upload_path.stem,
        file_type=document_node.doc_metadata.file_type,
        page_count=document_node.doc_metadata.page_count or len(raw_document.pages),
        total_elements=total_elements,
        element_summary=element_counts,
        message=f"Extraction completed successfully. Built {total_sections} structural sections.",
    )
