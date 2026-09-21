"""Template Extraction Service — Orchestrates full pipeline for template documents.

Reuses SOP extractors (Table, CrossPageTableStitcher, Icon, Caption), ASTBuilder,
HierarchicalChunker, and SemanticChunker, while producing TemplateExtractionOutput
with separated global rules and section-wise blue instructions.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional, Any

from loguru import logger

from app.config.settings import Settings
from app.schemas.ast_nodes import (
    DocumentNode,
    SectionNode,
    HeadingNode,
    ParagraphNode,
    ListNode,
    TableNode,
    ImageNode,
    IconNode,
)
from app.schemas.document import BoundingBox
from app.schemas.migration import MigrationTableCell
from app.schemas.template import (
    TemplateElement,
    TemplateExtractionOutput,
    TemplateGlobalRules,
    TemplateIconRef,
    TemplateInstruction,
    TemplateMetadata,
    TemplateSection,
)
from app.services.chunking.hierarchical import HierarchicalChunker
from app.services.chunking.semantic import SemanticChunker
from app.services.export.migration_exporter import (
    _extract_section_number,
    _is_major_section_heading,
)
from app.services.extraction.captions import CaptionExtractor
from app.services.extraction.cross_page_stitcher import CrossPageTableStitcher
from app.services.extraction.icons import IconExtractor
from app.services.extraction.tables import (
    TableExtractor,
    clean_table_cell_text,
    collapse_sparse_grid,
)
from app.services.hierarchy.ast_builder import ASTBuilder
from app.services.parser.template_parser import TemplateDocxParser


class TemplateExtractionService:
    """Orchestrates parsing, extraction, AST building, chunking, and output export for templates."""

    def __init__(self, settings: Settings, custom_logger=None):
        self.settings = settings
        self.logger = custom_logger or logger
        self.parser = TemplateDocxParser(settings=settings, logger=self.logger)

    async def extract(
        self, template_id: str, upload_path: Path, template_name: Optional[str] = None
    ) -> TemplateExtractionOutput:
        """Run full extraction pipeline on a template .docx file."""
        self.logger.info(f"TemplateExtractionService: starting extraction for {template_id} at {upload_path}")

        # 1. Parse .docx with blue instruction detection
        raw_document = self.parser.parse(str(upload_path), template_id=template_id)

        # 2. Reused Extractors
        table_extractor = TableExtractor(settings=self.settings, logger=self.logger)
        raw_document = table_extractor.extract(raw_document)

        stitcher = CrossPageTableStitcher(settings=self.settings, logger=self.logger)
        raw_document = stitcher.extract(raw_document)

        icon_extractor = IconExtractor(settings=self.settings, logger=self.logger)
        raw_document = icon_extractor.extract(raw_document, document_id=template_id, is_template=True)

        caption_extractor = CaptionExtractor(settings=self.settings, logger=self.logger)
        raw_document = caption_extractor.extract(raw_document)

        # 3. Build typed AST
        ast_builder = ASTBuilder(settings=self.settings, logger=self.logger)
        document_node = ast_builder.build(raw_document)

        # 4. Chunking (matching SOP chunking strategy)
        try:
            hierarchical_chunker = HierarchicalChunker(settings=self.settings, logger=self.logger)
            chunks = hierarchical_chunker.chunk(document_node)

            semantic_chunker = SemanticChunker(settings=self.settings, logger=self.logger)
            _ = semantic_chunker.chunk(chunks)
        except Exception as e:
            self.logger.warning(f"TemplateExtractionService: chunking warning (non-fatal): {e}")

        # 5. Build template-specific structured output
        output = self._build_output(
            template_id=template_id,
            upload_path=upload_path,
            ast=document_node,
            template_name=template_name,
        )

        self.logger.info(
            f"TemplateExtractionService: completed for {template_id}. "
            f"Sections: {len(output.sections)}, Instructions: {output.total_instructions}, "
            f"Icons: {output.total_icons}"
        )
        return output

    def _build_output(
        self,
        template_id: str,
        upload_path: Path,
        ast: DocumentNode,
        template_name: Optional[str] = None,
    ) -> TemplateExtractionOutput:
        """Convert AST into TemplateExtractionOutput, separating global rules and sections."""
        props = getattr(ast, "doc_metadata", None)
        file_stat = upload_path.stat() if upload_path.exists() else None
        effective_name = template_name or getattr(props, "document_name", None) or upload_path.stem

        metadata = TemplateMetadata(
            template_id=template_id,
            template_name=effective_name,
            author=getattr(props, "author", "") or "",
            creation_date=getattr(props, "creation_date", "") or "",
            modification_date=getattr(props, "modification_date", "") or "",
            file_type="docx",
            file_size_bytes=file_stat.st_size if file_stat else 0,
        )

        global_rules = TemplateGlobalRules()
        sections: list[TemplateSection] = []
        current_section: Optional[TemplateSection] = None
        has_entered_first_section = False
        paragraph_counter = 0

        buffered_icons: list[tuple[TemplateIconRef, Optional[BoundingBox]]] = []
        elem_bboxes: dict[int, BoundingBox] = {}
        icon_bboxes: dict[int, BoundingBox] = {}

        section_counter = 0

        def ensure_section(title: str, page: int, section_number: Optional[str] = None) -> TemplateSection:
            nonlocal current_section, has_entered_first_section, section_counter
            has_entered_first_section = True
            if section_number is None:
                extracted = _extract_section_number(title)
                if extracted:
                    section_number = extracted
                    if extracted.isdigit():
                        section_counter = int(extracted)
                else:
                    section_counter += 1
                    section_number = str(section_counter)

            sec = TemplateSection(
                section_number=section_number,
                title=title,
                page_start=page,
                page_end=page,
                elements=[],
                instructions=[],
            )
            sections.append(sec)
            current_section = sec
            return sec

        def flush_icons_onto(elem: TemplateElement):
            if not buffered_icons:
                return
            for icon_ref, bbox in buffered_icons:
                elem.icons.append(icon_ref)
                if bbox is not None:
                    icon_bboxes[id(icon_ref)] = bbox
            buffered_icons.clear()

        def add_element(elem: TemplateElement, bbox: Optional[BoundingBox] = None):
            nonlocal current_section
            if current_section is None:
                current_section = TemplateSection(
                    section_number="0",
                    title="0 PREAMBLE",
                    page_start=elem.page,
                    page_end=elem.page,
                    elements=[],
                    instructions=[],
                )
                sections.append(current_section)

            flush_icons_onto(elem)
            if bbox is not None:
                elem_bboxes[id(elem)] = bbox

            current_section.elements.append(elem)
            current_section.page_end = max(current_section.page_end, elem.page)

        def attach_icon(icon_ref: TemplateIconRef, bbox: Optional[BoundingBox] = None):
            buffered_icons.append((icon_ref, bbox))

        def check_is_instruction(node: Any) -> tuple[bool, Optional[str], Optional[str]]:
            """Check if node represents a blue-font instruction."""
            meta = getattr(node, "metadata", {}) or {}
            is_inst = meta.get("is_instruction", False)
            color_hex = meta.get("font_color_hex") or getattr(node, "highlight_color", None)
            inst_text = meta.get("instruction_text")

            # Also check highlight color if named/hex blue
            if not is_inst and color_hex:
                clean = str(color_hex).upper().lstrip("#")
                if clean in TemplateDocxParser.BLUE_HEX_VALUES or clean.startswith("STYLE_INSTRUCTION"):
                    is_inst = True

            return is_inst, color_hex, inst_text

        def traverse(node: Any, is_top: bool = False):
            nonlocal paragraph_counter, has_entered_first_section
            if node is None:
                return

            node_type = getattr(node, "node_type", None)
            loc = getattr(node, "source_location", None)
            page = getattr(loc, "page", 1) if loc else 1
            bbox = getattr(loc, "bbox", None) if loc else None

            if node_type == "document":
                for child in getattr(node, "children", []):
                    traverse(child, is_top=True)

            elif node_type == "section":
                heading = getattr(node, "heading", None)
                heading_level = getattr(heading, "level", 1) if heading else getattr(node, "level", 1)
                heading_text = (getattr(heading, "text", "") or "").strip() if heading else ""

                is_preamble_heading = heading_text.upper() in (
                    "GENERAL INFORMATION",
                    "GENERAL INSTRUCTIONS",
                    "TEMPLATE INSTRUCTIONS",
                    "INSTRUCTIONS",
                    "DOCUMENT INFORMATION",
                )

                # Major top-level section if top child or level <= 1, or numbered major heading
                is_major = False
                if heading_text and not is_preamble_heading:
                    if is_top or heading_level <= 1 or getattr(node, "level", 1) <= 1:
                        is_major = True
                    else:
                        extracted_num = _extract_section_number(heading_text)
                        if extracted_num and "." not in extracted_num:
                            is_major = True

                if is_major:
                    ensure_section(heading_text, page)
                elif heading and heading_text and not is_preamble_heading:
                    if current_section is not None:
                        add_element(
                            TemplateElement(
                                element_type="heading",
                                page=page,
                                level=max(2, heading_level),
                                text=heading_text,
                            ),
                            bbox=bbox,
                        )

                for child in getattr(node, "children", []):
                    traverse(child, is_top=False)

            elif node_type == "heading":
                text = (getattr(node, "text", "") or "").strip()
                if text:
                    level = getattr(node, "level", 1)
                    is_preamble_heading = text.upper() in (
                        "GENERAL INFORMATION",
                        "GENERAL INSTRUCTIONS",
                        "TEMPLATE INSTRUCTIONS",
                        "INSTRUCTIONS",
                        "DOCUMENT INFORMATION",
                    )
                    is_major = False
                    if not is_preamble_heading:
                        if is_top or level <= 1:
                            is_major = True
                        else:
                            extracted_num = _extract_section_number(text)
                            if extracted_num and "." not in extracted_num:
                                is_major = True

                    if is_major:
                        ensure_section(text, page)
                    elif not is_preamble_heading and current_section is not None:
                        add_element(
                            TemplateElement(
                                element_type="heading",
                                page=page,
                                level=max(2, level),
                                text=text,
                            ),
                            bbox=bbox,
                        )

            elif node_type == "paragraph":
                text = (getattr(node, "text", "") or "").strip()
                if text:
                    paragraph_counter += 1
                    is_inst, color_hex, inst_text = check_is_instruction(node)

                    # Global rules: ONLY blue instruction paragraphs before first section heading
                    if not has_entered_first_section:
                        if is_inst:
                            global_rules.instructions.append(
                                TemplateInstruction(
                                    text=text,
                                    font_color_hex=color_hex,
                                    paragraph_index=paragraph_counter,
                                    section_context=None,
                                    is_global=True,
                                )
                            )
                        else:
                            # Skip preamble headers like "GENERAL INFORMATION" from creating a dummy section
                            if text.upper() not in (
                                "GENERAL INFORMATION",
                                "GENERAL INSTRUCTIONS",
                                "TEMPLATE INSTRUCTIONS",
                                "INSTRUCTIONS",
                                "DOCUMENT INFORMATION",
                            ):
                                elem = TemplateElement(
                                    element_type="paragraph",
                                    page=page,
                                    text=text,
                                    is_instruction=False,
                                )
                                add_element(elem, bbox=bbox)
                    else:
                        elem = TemplateElement(
                            element_type="paragraph",
                            page=page,
                            text=text,
                            is_instruction=is_inst,
                            instruction_text=inst_text if is_inst else None,
                            font_color_hex=color_hex if is_inst else None,
                        )
                        add_element(elem, bbox=bbox)

                        if is_inst and current_section is not None:
                            current_section.instructions.append(
                                TemplateInstruction(
                                    text=text,
                                    font_color_hex=color_hex,
                                    paragraph_index=paragraph_counter,
                                    section_context=current_section.title,
                                    is_global=False,
                                )
                            )

            elif node_type == "list":
                items: list[str] = []
                list_type = getattr(node, "list_type", "") or ""
                has_instruction_items = False
                for item in getattr(node, "items", []):
                    item_text = (getattr(item, "text", "") or "").strip()
                    if not item_text:
                        continue
                    idx = getattr(item, "index", None)
                    formatted_text = f"{idx}. {item_text}" if str(list_type) == "ordered" and idx else item_text
                    items.append(formatted_text)

                    is_inst, color_hex, inst_text = check_is_instruction(item)
                    if is_inst:
                        has_instruction_items = True
                        paragraph_counter += 1
                        if not has_entered_first_section:
                            global_rules.instructions.append(
                                TemplateInstruction(
                                    text=item_text,
                                    font_color_hex=color_hex,
                                    paragraph_index=paragraph_counter,
                                    section_context=None,
                                    is_global=True,
                                )
                            )
                        elif current_section is not None:
                            current_section.instructions.append(
                                TemplateInstruction(
                                    text=item_text,
                                    font_color_hex=color_hex,
                                    paragraph_index=paragraph_counter,
                                    section_context=current_section.title,
                                    is_global=False,
                                )
                            )

                if items:
                    add_element(
                        TemplateElement(
                            element_type="list",
                            page=page,
                            items=items,
                            is_instruction=has_instruction_items,
                        ),
                        bbox=bbox,
                    )

            elif node_type == "table":
                table_elem, t_instructions = self._convert_table(
                    node, page, section_title=current_section.title if current_section else None
                )
                if table_elem:
                    add_element(table_elem, bbox=bbox)
                    if t_instructions and current_section is not None:
                        for t_inst in t_instructions:
                            paragraph_counter += 1
                            t_inst.paragraph_index = paragraph_counter
                            current_section.instructions.append(t_inst)
                elif t_instructions:
                    # Unwrapped layout container: emit each instruction as a paragraph element with its icon
                    for t_inst in t_instructions:
                        paragraph_counter += 1
                        t_inst.paragraph_index = paragraph_counter
                        if current_section is not None:
                            current_section.instructions.append(t_inst)
                        add_element(
                            TemplateElement(
                                element_type="paragraph",
                                page=page,
                                text=t_inst.text,
                                instruction_text=t_inst.text,
                                font_color_hex=t_inst.font_color_hex,
                                is_instruction=True,
                                icons=list(t_inst.icons),
                            ),
                            bbox=bbox,
                        )

            elif node_type == "image":
                path = getattr(node, "asset_path", "")
                if path:
                    caption = getattr(node, "caption", None) or getattr(node, "alt_text", None)
                    add_element(
                        TemplateElement(
                            element_type="image",
                            page=page,
                            title=caption,
                            image_path=path,
                        ),
                        bbox=bbox,
                    )

            elif node_type == "icon":
                path = getattr(node, "asset_path", "")
                if path:
                    icon_id = getattr(node, "node_id", "") or "icon"
                    attach_icon(
                        TemplateIconRef(
                            icon_id=str(icon_id),
                            image_path=path,
                            semantic_meaning=getattr(node, "semantic_meaning", "unknown") or "unknown",
                            section_context=current_section.title if current_section else None,
                        ),
                        bbox=bbox,
                    )

            elif hasattr(node, "children"):
                for child in getattr(node, "children", []):
                    traverse(child, is_top=False)

        traverse(ast, is_top=True)

        if buffered_icons and current_section and current_section.elements:
            flush_icons_onto(current_section.elements[-1])

        # Remove empty PREAMBLE if all pre-heading items were absorbed into global_rules
        if sections and sections[0].title == "0 PREAMBLE" and not sections[0].elements:
            sections.pop(0)

        # Count totals
        total_instructions = len(global_rules.instructions)
        total_icons = 0
        for sec in sections:
            total_instructions += len(sec.instructions)
            for elem in sec.elements:
                total_icons += len(elem.icons)

        return TemplateExtractionOutput(
            version="1.0",
            template_id=template_id,
            template_name=effective_name,
            metadata=metadata,
            global_rules=global_rules,
            sections=sections,
            total_instructions=total_instructions,
            total_icons=total_icons,
        )

    def _convert_table(
        self, table: TableNode, page: int, section_title: Optional[str] = None
    ) -> tuple[Optional[TemplateElement], list[TemplateInstruction]]:
        """Convert TableNode into a TemplateElement with MigrationTableCell list and extract instructions."""
        rows = getattr(table, "rows", [])
        if not rows:
            return None, []

        num_rows = len(rows)
        num_cols = getattr(table, "grid_cols", 0)
        if not num_cols:
            max_c = 0
            for r in rows:
                c_count = sum(getattr(cell, "col_span", 1) for cell in getattr(r, "cells", []))
                max_c = max(max_c, c_count)
            num_cols = max_c

        cells: list[MigrationTableCell] = []
        table_instructions: list[TemplateInstruction] = []
        table_icon_refs: list[TemplateIconRef] = []
        table_has_instructions = False

        for row_idx, row in enumerate(rows):
            is_header = getattr(row, "is_header", False)
            row_cells = getattr(row, "cells", [])
            row_icons: list[TemplateIconRef] = []
            row_texts: list[str] = []
            row_instruction_texts: list[str] = []
            row_is_instruction = False
            row_color_hex = None

            for cell in row_cells:
                if not getattr(cell, "is_merge_origin", True):
                    continue

                cell_text_parts: list[str] = []
                icon_path: Optional[str] = None
                image_path: Optional[str] = None
                background_color: Optional[str] = None
                cell_meta = getattr(cell, "metadata", {}) or {}

                for item in getattr(cell, "content", []):
                    item_type = getattr(item, "node_type", None)
                    item_meta = getattr(item, "metadata", {}) or {}

                    if item_type in ("paragraph", "heading"):
                        t = (getattr(item, "text", "") or "").strip()
                        if t:
                            cell_text_parts.append(t)
                        if not background_color:
                            background_color = getattr(item, "highlight_color", None)
                        if item_meta.get("is_instruction"):
                            row_is_instruction = True
                            row_color_hex = item_meta.get("font_color_hex") or row_color_hex
                            inst_t = item_meta.get("instruction_text") or t
                            if inst_t:
                                row_instruction_texts.append(inst_t)
                    elif item_type == "highlight":
                        t = (getattr(item, "text", "") or "").strip()
                        if t:
                            cell_text_parts.append(t)
                        if not background_color:
                            background_color = getattr(item, "color_hex", None) or getattr(item, "highlight_color", None)
                    elif item_type == "icon":
                        ip = getattr(item, "asset_path", None)
                        if ip:
                            if not icon_path:
                                icon_path = ip
                            icon_id = str(getattr(item, "node_id", getattr(item, "icon_id", "icon")))
                            semantic = getattr(item, "semantic_meaning", "unknown") or "unknown"
                            row_icons.append(
                                TemplateIconRef(
                                    icon_id=icon_id,
                                    image_path=ip,
                                    semantic_meaning=semantic,
                                    section_context=section_title,
                                )
                            )
                    elif item_type == "image":
                        ip = getattr(item, "asset_path", None)
                        if ip and not image_path:
                            image_path = ip
                    elif item_type == "list":
                        for litem in getattr(item, "items", []):
                            lt = (getattr(litem, "text", "") or "").strip()
                            if lt:
                                cell_text_parts.append(f"- {lt}")

                if cell_meta.get("is_instruction"):
                    row_is_instruction = True
                    row_color_hex = cell_meta.get("font_color_hex") or row_color_hex
                    c_inst = cell_meta.get("instruction_text")
                    if c_inst and not row_instruction_texts:
                        row_instruction_texts.append(c_inst)

                text = clean_table_cell_text(" ".join(cell_text_parts).strip())
                if text:
                    row_texts.append(text)

                if image_path and not icon_path and not text:
                    icon_path = image_path
                    image_path = None
                    row_icons.append(
                        TemplateIconRef(
                            icon_id="img_icon",
                            image_path=icon_path,
                            semantic_meaning="unknown",
                            section_context=section_title,
                        )
                    )

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
                        background_color=background_color,
                    )
                )

            # Associate row icons with row text
            full_row_text = " ".join(row_texts).strip()
            for ic in row_icons:
                ic.associated_text = full_row_text
                table_icon_refs.append(ic)

            # If this row is an instruction or contains blue instruction text
            if row_is_instruction and (row_instruction_texts or full_row_text):
                table_has_instructions = True
                unique_texts: list[str] = []
                for txt in row_instruction_texts:
                    t_clean = txt.strip()
                    if t_clean and t_clean not in unique_texts:
                        unique_texts.append(t_clean)
                inst_text_content = " ".join(unique_texts).strip() if unique_texts else full_row_text
                table_instructions.append(
                    TemplateInstruction(
                        text=inst_text_content,
                        font_color_hex=row_color_hex,
                        section_context=section_title,
                        is_global=False,
                        icons=list(row_icons),
                    )
                )

        if not any(c.text or c.icon_path or c.image_path or c.background_color for c in cells):
            return None, []

        # Detect if this table is an icon-instruction layout container (borderless table used to align icon and instruction text)
        is_layout_container = (
            num_cols == 2
            and len(table_instructions) == num_rows
            and len(table_icon_refs) == num_rows
            and all(
                any(c.col_index == 0 and c.icon_path for c in cells if c.row_index == r_idx)
                for r_idx in range(num_rows)
            )
        )

        if is_layout_container:
            # Layout container unwrapped: return None for table_elem so it is not emitted as a table
            return None, table_instructions

        # Grid collapse if sparse
        cells, num_rows, num_cols = self._collapse_cells(cells, num_rows, num_cols)

        table_elem = TemplateElement(
            element_type="table",
            page=page,
            title=getattr(table, "caption", None),
            num_rows=num_rows,
            num_cols=num_cols,
            cells=cells,
            icons=table_icon_refs,
            is_instruction=table_has_instructions,
        )

        return table_elem, table_instructions

    @staticmethod
    def _collapse_cells(
        cells: list[MigrationTableCell], num_rows: int, num_cols: int
    ) -> tuple[list[MigrationTableCell], int, int]:
        """Collapse redundant empty columns in table cells."""
        used_cols = {c.col_index for c in cells if c.text or c.icon_path or c.image_path}
        if not used_cols or len(used_cols) == num_cols:
            return cells, num_rows, num_cols

        col_remap = {old: new for new, old in enumerate(sorted(used_cols))}
        new_cells = []
        for c in cells:
            if c.col_index in col_remap:
                c.col_index = col_remap[c.col_index]
                new_cells.append(c)

        return new_cells, num_rows, len(col_remap)
