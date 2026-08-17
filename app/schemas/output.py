"""Output schemas for the v2 extraction pipeline.

These models define the top-level JSON envelope returned by the AST-based
extraction system.  The ``DocumentExtractionOutput`` replaces the v1
``DocumentOutput`` (chunk-based) as the primary export format.

The v1 ``DocumentOutput`` is retained in ``document.py`` for backward
compatibility and the ``/v2/documents/{id}/chunks`` endpoint.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.ast_nodes import DocumentNode
from app.schemas.document import DocumentMetadata, Chunk


# ── Extraction Statistics ──────────────────────────────────────────────

class ExtractionStats(BaseModel):
    """Aggregate statistics computed from the AST after extraction."""
    total_sections: int = 0
    total_paragraphs: int = 0
    total_headings: int = 0
    total_lists: int = 0
    total_list_items: int = 0
    total_tables: int = 0
    total_images: int = 0
    total_icons: int = 0
    total_captions: int = 0
    total_highlights: int = 0
    total_images_with_ocr: int = 0
    avg_confidence: float = 0.0
    processing_time_ms: int = 0

    @classmethod
    def from_ast(cls, ast: DocumentNode) -> "ExtractionStats":
        stats = cls()

        def traverse(node):
            node_type = getattr(node, "node_type", None)

            if node_type == "section":
                stats.total_sections += 1
                if getattr(node, "heading", None):
                    traverse(node.heading)
            elif node_type == "paragraph":
                stats.total_paragraphs += 1
                stats.total_highlights += len(getattr(node, "highlights", []))
            elif node_type == "heading":
                stats.total_headings += 1
            elif node_type == "list":
                stats.total_lists += 1
                for item in getattr(node, "items", []):
                    stats.total_list_items += 1
                    traverse(item)
            elif node_type == "table":
                stats.total_tables += 1
                for row in getattr(node, "rows", []):
                    traverse(row)
            elif node_type == "table_row":
                for cell in getattr(node, "cells", []):
                    traverse(cell)
            elif node_type == "table_cell":
                for c in getattr(node, "content", []):
                    traverse(c)
            elif node_type == "image":
                stats.total_images += 1
            elif node_type == "icon":
                stats.total_icons += 1
            elif node_type == "caption":
                stats.total_captions += 1
            elif node_type == "highlight":
                stats.total_highlights += 1

            if hasattr(node, "children"):
                for child in getattr(node, "children"):
                    traverse(child)

        traverse(ast)
        return stats


# ── Asset Manifest ─────────────────────────────────────────────────────

class AssetReference(BaseModel):
    """Metadata for a single extracted asset (image or icon)."""
    asset_id: str
    filename: str
    width: int = 0
    height: int = 0
    hash: str = ""
    size_bytes: int = 0
    semantic_meaning: Optional[str] = None
    icon_type: Optional[str] = None
    classification_method: Optional[str] = None
    confidence: float = 1.0


class AssetManifest(BaseModel):
    """Inventory of all extracted image and icon assets."""
    base_path: str = ""
    images: list[AssetReference] = Field(default_factory=list)
    icons: list[AssetReference] = Field(default_factory=list)


# ── Header / Footer ───────────────────────────────────────────────────

class HeaderFooterEntry(BaseModel):
    """A header or footer extracted from a specific page."""
    page: int = 0
    text: str = ""


# ── Top-Level Output ──────────────────────────────────────────────────

class DocumentExtractionOutput(BaseModel):
    """Top-level v2 extraction result.

    This is the JSON envelope returned by ``/v2/documents/{id}/json``
    and ``/v2/jobs/{job_id}/result``.  It wraps the full AST together
    with document metadata, asset manifests, and extraction statistics.
    """
    version: str = "2.0"
    document_id: str
    extraction_timestamp: str
    extraction_engine_version: str = "0.2.0"
    metadata: DocumentMetadata = Field(default_factory=DocumentMetadata)
    assets: AssetManifest = Field(default_factory=AssetManifest)
    headers: list[HeaderFooterEntry] = Field(default_factory=list)
    footers: list[HeaderFooterEntry] = Field(default_factory=list)
    ast: DocumentNode = Field(default_factory=DocumentNode)
    chunks: list[Chunk] = Field(default_factory=list)
    extraction_stats: ExtractionStats = Field(default_factory=ExtractionStats)
