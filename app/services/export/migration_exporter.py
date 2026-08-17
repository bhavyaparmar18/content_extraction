"""Migration Exporter for Clean .docx-Ready Output.

This module converts the extracted AST (DocumentNode) and AssetManifest into a
concise, section-wise reading-order JSON structure (DocxMigrationOutput) designed
specifically for reconstructing Microsoft Word (.docx) documents.
"""

from __future__ import annotations

import logging
import re
from typing import Optional, Any

from app.schemas.ast_nodes import (
    DocumentNode,
    SectionNode,
    HeadingNode,
    ParagraphNode,
    ListNode,
    ListItemNode,
    TableNode,
    TableRowNode,
    TableCellNode,
    ImageNode,
    IconNode,
    CaptionNode,
)
from app.schemas.migration import (
    DocxMigrationOutput,
    MigrationMetadata,
    MigrationSection,
    MigrationElement,
    MigrationTableCell,
    MigrationIconRef,
)

logger = logging.getLogger(__name__)


def _is_major_section_heading(title: str) -> Optional[str]:
    match = re.match(r"^(\d+)\s+([A-Z0-9\s&/\-_,]+)$", title.strip())
    if match:
        return match.group(1)
    return None


def _extract_section_number(title: str) -> Optional[str]:
    match = re.match(r"^(\d+(?:\.\d+)*)", title.strip())
    if match:
        return match.group(1).rstrip(".")
    return None


class MigrationExporter:
    """Exports AST and assets to a Clean .docx Document Migration format."""

    @classmethod
    def export(
        cls,
        document_id: str,
        ast: DocumentNode,
        assets_manifest: Optional[Any] = None,
    ) -> DocxMigrationOutput:
        """Convert a DocumentNode AST into a clean DocxMigrationOutput envelope."""
        metadata = cls._extract_metadata(document_id, ast)
        sections = cls._traverse_ast(ast)

        return DocxMigrationOutput(
            version="3.1",
            document_id=document_id,
            metadata=metadata,
            sections=sections,
        )

    @classmethod
    def _is_running_header_or_footer(cls, node: Any) -> bool:
        """Fallback check to suppress running header and footer nodes."""
        node_type = getattr(node, "node_type", None)
        if node_type in ("document", "section", "table"):
            return False
        text = (getattr(node, "text", "") or "").strip()
        if not text:
            return False

        import re
        patterns = [
            r"^Number:\s*BI-VQD-",
            r"^BI-VQD-\d+",
            r"^Boehringer\s+Ingelheim\s*Page\s+\d+",
            r"^Title:\s*Good\s+Writing\s+Practice",
            r"^Document\s+Name:\s*BI-VQD-",
            r"^Version:\s*\d+",
            r"^Effective\s+Date:\s*",
            r"^Life\s+forward$",
            r"Property\s+of\s+Boehringer\s+Ingelheim",
            r"Retrieved\s+by\s+",
            r"Verify\s+the\s+current\s+version",
            r"Working\s+Copy",
        ]
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False

    @classmethod
    def _extract_metadata(cls, document_id: str, ast: DocumentNode) -> MigrationMetadata:
        doc_meta = getattr(ast, "doc_metadata", None)
        if not doc_meta:
            return MigrationMetadata(document_id=document_id)

        title = getattr(doc_meta, "title", None) or getattr(doc_meta, "document_name", None)
        return MigrationMetadata(
            document_id=document_id,
            document_number=getattr(doc_meta, "document_number", None),
            document_name=getattr(doc_meta, "document_name", None),
            document_version=getattr(doc_meta, "document_version", None),
            title=title,
            language=getattr(doc_meta, "language", "en"),
            page_count=getattr(doc_meta, "page_count", 0),
            duplicate_upload_count=getattr(doc_meta, "duplicate_upload_count", 0),
        )

    @classmethod
    def _get_page(cls, node: Any) -> int:
        source_loc = getattr(node, "source_location", None)
        if source_loc and getattr(source_loc, "page", None) is not None:
            return source_loc.page
        return 0

    @classmethod
    def _traverse_ast(cls, ast: DocumentNode) -> list[MigrationSection]:
        sections: list[MigrationSection] = []
        current_section: Optional[MigrationSection] = None
        buffered_icons: list[MigrationIconRef] = []

        def ensure_section(title: str, page: int, section_number: Optional[str] = None) -> MigrationSection:
            nonlocal current_section
            if section_number is None:
                section_number = _extract_section_number(title)
            sec = MigrationSection(
                section_number=section_number,
                title=title,
                page_start=page,
                page_end=page,
                elements=[],
            )
            sections.append(sec)
            current_section = sec
            return sec

        def add_element(elem: MigrationElement):
            nonlocal current_section, buffered_icons
            if current_section is None:
                ensure_section("0 PREAMBLE", elem.page, section_number="0")

            if buffered_icons:
                elem.icons.extend(buffered_icons)
                buffered_icons.clear()

            current_section.elements.append(elem)
            current_section.page_end = max(current_section.page_end, elem.page)

        def attach_icon(icon_ref: MigrationIconRef, page: int = 0):
            nonlocal buffered_icons
            # Icons in PDF reading order precede the text they belong to,
            # so always buffer them for attachment to the *next* element.
            buffered_icons.append(icon_ref)

        def traverse(node: Any, is_top_section: bool = False):
            if node is None:
                return

            if cls._is_running_header_or_footer(node):
                return

            node_type = getattr(node, "node_type", None)
            page = cls._get_page(node)

            if node_type == "document":
                for child in getattr(node, "children", []):
                    traverse(child, is_top_section=True)

            elif node_type == "section":
                heading = getattr(node, "heading", None)
                heading_level = getattr(heading, "level", 1) if heading else 1
                heading_text = (getattr(heading, "text", "") or "").strip() if heading else ""
                major_sec = _is_major_section_heading(heading_text) if heading_text else None

                if major_sec or (current_section is None):
                    title = heading_text or f"Section {len(sections)+1}"
                    ensure_section(title, page, section_number=major_sec)
                elif heading:
                    add_element(
                        MigrationElement(
                            element_type="heading",
                            page=page,
                            level=heading_level,
                            text=heading_text,
                        )
                    )

                for child in getattr(node, "children", []):
                    traverse(child, is_top_section=False)

            elif node_type == "heading":
                text = (getattr(node, "text", "") or "").strip()
                if text:
                    level = getattr(node, "level", 1)
                    major_sec = _is_major_section_heading(text)
                    if current_section is None or major_sec:
                        ensure_section(text, page, section_number=major_sec)
                    add_element(
                        MigrationElement(
                            element_type="heading",
                            page=page,
                            level=level,
                            text=text,
                        )
                    )

            elif node_type == "paragraph":
                text = (getattr(node, "text", "") or "").strip()
                if text:
                    add_element(
                        MigrationElement(
                            element_type="paragraph",
                            page=page,
                            text=text,
                        )
                    )

            elif node_type == "list":
                items: list[str] = []
                for item in getattr(node, "items", []):
                    item_text = (getattr(item, "text", "") or "").strip()
                    if item_text:
                        items.append(item_text)
                if items:
                    add_element(
                        MigrationElement(
                            element_type="list",
                            page=page,
                            items=items,
                        )
                    )

            elif node_type == "table":
                table_elem = cls._convert_table(node, page)
                if table_elem:
                    add_element(table_elem)

            elif node_type == "image":
                path = getattr(node, "asset_path", "")
                if path:
                    caption = getattr(node, "caption", None) or getattr(node, "alt_text", None)
                    add_element(
                        MigrationElement(
                            element_type="image",
                            page=page,
                            title=caption,
                            image_path=path,
                        )
                    )

            elif node_type == "icon":
                path = getattr(node, "asset_path", "")
                if path:
                    icon_id = getattr(node, "node_id", "") or "icon"
                    attach_icon(
                        MigrationIconRef(
                            icon_id=str(icon_id),
                            path=path,
                            semantic_meaning=getattr(node, "semantic_meaning", None),
                        ),
                        page=page,
                    )

            elif hasattr(node, "children"):
                for child in getattr(node, "children", []):
                    traverse(child, is_top_section=False)

        traverse(ast, is_top_section=True)

        # If any buffered icons remain at the end, attach to last element of last section
        if buffered_icons and current_section and current_section.elements:
            current_section.elements[-1].icons.extend(buffered_icons)
            buffered_icons.clear()

        return sections

    @classmethod
    def _convert_table(cls, table: TableNode, page: int) -> Optional[MigrationElement]:
        rows = getattr(table, "rows", [])
        if not rows:
            return None

        num_rows = len(rows)
        # Determine num_cols from grid_cols or max cells across rows
        num_cols = getattr(table, "grid_cols", 0)
        if not num_cols:
            max_c = 0
            for r in rows:
                c_count = 0
                for cell in getattr(r, "cells", []):
                    c_count += getattr(cell, "col_span", 1)
                max_c = max(max_c, c_count)
            num_cols = max_c

        cells: list[MigrationTableCell] = []

        for row_idx, row in enumerate(rows):
            is_header = getattr(row, "is_header", False)
            for cell in getattr(row, "cells", []):
                # Only include genuine origin cells for .docx table construction
                if not getattr(cell, "is_merge_origin", True):
                    continue

                # Extract text, icon_path, image_path from cell content
                cell_text_parts: list[str] = []
                icon_path: Optional[str] = None
                image_path: Optional[str] = None

                for item in getattr(cell, "content", []):
                    item_type = getattr(item, "node_type", None)
                    if item_type in ("paragraph", "heading"):
                        t = (getattr(item, "text", "") or "").strip()
                        if t:
                            cell_text_parts.append(t)
                    elif item_type == "icon":
                        ip = getattr(item, "asset_path", None)
                        if ip and not icon_path:
                            icon_path = ip
                    elif item_type == "image":
                        ip = getattr(item, "asset_path", None)
                        if ip and not image_path:
                            image_path = ip
                    elif item_type == "list":
                        for litem in getattr(item, "items", []):
                            lt = (getattr(litem, "text", "") or "").strip()
                            if lt:
                                cell_text_parts.append(f"- {lt}")

                text = " ".join(cell_text_parts).strip()

                cells.append(
                    MigrationTableCell(
                        row_index=getattr(cell, "row_index", row_idx),
                        col_index=getattr(cell, "col_index", 0),
                        row_span=getattr(cell, "row_span", 1),
                        col_span=getattr(cell, "col_span", 1),
                        text=text,
                        icon_path=icon_path,
                        image_path=image_path,
                        is_header=is_header,
                    )
                )

        return MigrationElement(
            element_type="table",
            page=page,
            title=getattr(table, "caption", None),
            num_rows=num_rows,
            num_cols=num_cols,
            cells=cells,
        )
