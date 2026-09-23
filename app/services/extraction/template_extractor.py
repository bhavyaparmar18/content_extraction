"""Template Extraction Service — Orchestrates full pipeline for template documents.

Reuses SOP extractors (Table, CrossPageTableStitcher, Icon, Caption), ASTBuilder,
HierarchicalChunker, and SemanticChunker, while producing the v2.0
``TemplateExtractionOutput``: a deduplicated icon library, a callout style
registry read from real template shading, machine-enforceable global rules, and
sections split into skeleton content versus authoring instructions.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Optional, Any

from loguru import logger

from app.config.settings import Settings
from app.schemas.ast_nodes import (
    DocumentNode,
    TableNode,
)
from app.schemas.document import BoundingBox
from app.schemas.template import (
    DirectiveType,
    InstructionScope,
    TemplateCalloutStyle,
    TemplateElement,
    TemplateExtractionOutput,
    TemplateGlobalRules,
    TemplateIconEntry,
    TemplateIconRef,
    TemplateInstruction,
    TemplateMachineRule,
    TemplateMetadata,
    TemplateSection,
    TemplateTableCell,
    TemplateTotals,
)
from app.services.chunking.hierarchical import HierarchicalChunker
from app.services.chunking.semantic import SemanticChunker
from app.services.export.migration_exporter import (
    _extract_section_number,
)
from app.services.extraction.captions import CaptionExtractor
from app.services.extraction.cross_page_stitcher import CrossPageTableStitcher
from app.services.extraction.icons import IconExtractor
from app.services.extraction.tables import (
    TableExtractor,
    clean_table_cell_text,
)
from app.services.hierarchy.ast_builder import ASTBuilder
from app.services.parser.template_parser import TemplateDocxParser


# ── Instruction classification ─────────────────────────────────────────

# Placeholder tokens the template uses for author-supplied values. Mirrors
# TemplateInspector.PLACEHOLDER_PATTERN so both sides agree on what counts.
_PLACEHOLDER_PATTERN = re.compile(
    r"(\$\{[^}]+\}|<<[^>]+>>|\[Insert\s+[^\]]+\]|\[Role\s*\d+\]|\bn\.0\b|BI-VQD-\d+)",
    re.IGNORECASE,
)

# The template's "Do NOT" list, mapped to rules a validator can enforce without
# asking the LLM. Every keyword in a row must be present for the rule to apply.
_MACHINE_RULE_MAP: tuple[tuple[tuple[str, ...], str, Any, str], ...] = (
    (("arial",), "font_family", "Arial", DirectiveType.FORMATTING.value),
    (("header", "footer"), "preserve_headers_footers", True, DirectiveType.PROHIBITION.value),
    (("chapter", "do not"), "allow_new_h1", False, DirectiveType.PROHIBITION.value),
    (("table of content",), "toc_auto_generated", True, DirectiveType.PROHIBITION.value),
    (("toc",), "toc_auto_generated", True, DirectiveType.PROHIBITION.value),
    (("blue text", "delete"), "strip_blue_text", True, DirectiveType.REQUIREMENT.value),
    (("initial page",), "skip_cover_page", True, DirectiveType.PROHIBITION.value),
    (("cover page",), "skip_cover_page", True, DirectiveType.PROHIBITION.value),
)

_PROHIBITION_MARKERS = (
    "do not", "don't", "must not", "cannot", "can not",
    "is not possible", "not allowed", "never", "avoid ",
)
_REQUIREMENT_MARKERS = (
    "must ", "shall ", "ensure", "required", "delete", "insert ", "make sure",
)
_FORMATTING_MARKERS = (
    "font", "arial", "header", "footer", "table of content", "toc",
    "style", "numbering", "page break", "formatting", "bold", "italic",
)

_PREAMBLE_HEADINGS = (
    "GENERAL INFORMATION",
    "GENERAL INSTRUCTIONS",
    "TEMPLATE INSTRUCTIONS",
    "INSTRUCTIONS",
    "DOCUMENT INFORMATION",
)


def _classify_instruction(text: str) -> tuple[str, Optional[TemplateMachineRule]]:
    """Derive ``directive_type`` and any enforceable ``machine_rule`` from text."""
    low = text.lower()

    for keywords, rule, value, directive in _MACHINE_RULE_MAP:
        if all(kw in low for kw in keywords):
            return directive, TemplateMachineRule(rule=rule, value=value, enforce="hard")

    if any(marker in low for marker in _PROHIBITION_MARKERS):
        return DirectiveType.PROHIBITION.value, None
    if "infographic" in low or "icon" in low:
        return DirectiveType.ICON_USAGE.value, None
    if _PLACEHOLDER_PATTERN.search(text):
        return DirectiveType.PLACEHOLDER_HINT.value, None
    if any(marker in low for marker in _FORMATTING_MARKERS):
        return DirectiveType.FORMATTING.value, None
    if any(marker in low for marker in _REQUIREMENT_MARKERS):
        return DirectiveType.REQUIREMENT.value, None
    return DirectiveType.GUIDANCE.value, None


def _find_placeholders(text: str) -> list[str]:
    """Return unique placeholder tokens in *text*, in first-seen order."""
    seen: list[str] = []
    for match in _PLACEHOLDER_PATTERN.findall(text or ""):
        token = match.strip()
        if token and token not in seen:
            seen.append(token)
    return seen


def _callout_type_for(*texts: Optional[str]) -> Optional[str]:
    """Name a callout from its own label, not from a fixed vocabulary.

    A legend row reads ``"Explanation – additional information..."``. The type is
    the text before the dash. A short sentence with no dash contributes its
    first word (``"Explanation text goes here."`` → ``explanation``). Longer
    prose is a trigger instruction, not a type name, and is ignored.
    """
    for text in texts:
        slug = _label_slug(text)
        if slug:
            return slug
    return None


def _label_slug(text: Optional[str]) -> Optional[str]:
    if not text or not text.strip():
        return None
    raw = text.strip()
    parts = re.split(r"\s+[–—-]\s+", raw, maxsplit=1)
    if len(parts) == 1:
        words = raw.split()
        if len(words) > 8:
            return None
        label = words[0]
    else:
        label = parts[0]
        if len(label.split()) > 8:
            return None
    label = label.strip().strip("\"'")
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    if len(slug) < 3:
        return None
    return slug[:48]


def _content_hash_from_path(asset_path: str) -> Optional[str]:
    """Recover the md5 fragment parsers embed in extracted asset filenames."""
    if not asset_path:
        return None
    candidate = Path(asset_path).stem.rsplit("_", 1)[-1].lower()
    if len(candidate) == 10 and all(c in "0123456789abcdef" for c in candidate):
        return candidate
    return None


def _id_slug(value: str) -> str:
    """Reduce a section number/title to something usable inside an identifier."""
    slug = re.sub(r"[^A-Za-z0-9]+", "", value or "")
    return slug or "x"


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
            f"Sections: {output.totals.sections}, Instructions: {output.totals.instructions}, "
            f"Icons: {output.totals.icons}, Callouts: {output.totals.callouts}"
        )
        return output

    # ── Path portability ────────────────────────────────────────────

    def _relativize(self, raw_path: Optional[str]) -> Optional[str]:
        """Make an on-disk asset path portable by relativising it to the project root.

        Extractors need real absolute paths while they move files around, so this
        runs at output-build time only.
        """
        if not raw_path:
            return raw_path
        path = Path(raw_path)
        if not path.is_absolute():
            return path.as_posix()
        try:
            return path.relative_to(self.settings.project_root).as_posix()
        except ValueError:
            return path.name

    def _relativize_output(
        self,
        icon_library: list[TemplateIconEntry],
        sections: list[TemplateSection],
    ) -> None:
        """Rewrite every asset path in the built output in place."""
        for entry in icon_library:
            entry.asset_path = self._relativize(entry.asset_path) or ""

        for section in sections:
            for element in section.skeleton_elements:
                element.image_path = self._relativize(element.image_path)
                for cell in element.cells:
                    cell.icon_path = self._relativize(cell.icon_path)
                    cell.image_path = self._relativize(cell.image_path)

    # ── Output building ─────────────────────────────────────────────

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
        icon_library: dict[str, TemplateIconEntry] = {}
        callout_styles: dict[str, TemplateCalloutStyle] = {}

        current_section: Optional[TemplateSection] = None
        has_entered_first_section = False
        paragraph_counter = 0
        global_instruction_seq = 0
        section_instruction_seq: dict[str, int] = {}
        section_counter = 0
        last_instruction_text: Optional[str] = None

        buffered_icons: list[tuple[TemplateIconRef, Optional[BoundingBox]]] = []

        # ── Registries ───────────────────────────────────────────

        def register_icon(
            node: Any = None,
            section_context: Optional[str] = None,
            associated_text: Optional[str] = None,
            asset_path: Optional[str] = None,
        ) -> Optional[str]:
            """Add an icon to the deduplicated library and return its stable key.

            Pass *asset_path* directly for images being used as icons, where
            there is no ``IconNode`` to read from.
            """
            asset_path = (
                asset_path
                or getattr(node, "asset_path", "")
                or getattr(node, "image_path", "")
                or ""
            )
            if not asset_path:
                return None

            content_hash = (
                getattr(node, "content_hash", None)
                or getattr(node, "image_hash", None)
                or _content_hash_from_path(asset_path)
            )
            icon_key = f"icon_{content_hash}" if content_hash else f"icon_{Path(asset_path).stem}"

            entry = icon_library.get(icon_key)
            if entry is None:
                entry = TemplateIconEntry(
                    icon_key=icon_key,
                    content_hash=content_hash,
                    asset_path=asset_path,
                    semantic_meaning=getattr(node, "semantic_meaning", "unknown") or "unknown",
                )
                icon_library[icon_key] = entry

            entry.occurrences += 1
            if section_context and section_context not in entry.allowed_sections:
                entry.allowed_sections.append(section_context)
            if associated_text and not entry.source_instruction:
                entry.source_instruction = associated_text
            return icon_key

        def register_callout(
            callout_type: str,
            background_hex: str,
            border_hex: Optional[str],
            font_hex: Optional[str],
            icon_key: Optional[str],
            trigger_instruction: Optional[str],
            section_context: Optional[str],
            page: int,
        ) -> str:
            """Add a callout style to the registry, filling gaps on repeat sightings."""
            entry = callout_styles.get(callout_type)
            if entry is None:
                entry = TemplateCalloutStyle(
                    callout_type=callout_type,
                    display_name=callout_type.replace("_", " ").title(),
                    background_color_hex=background_hex,
                    left_border_color_hex=border_hex,
                    font_color_hex=font_hex,
                    icon_key=icon_key,
                    trigger_instruction=trigger_instruction,
                    template_source={"section": section_context, "page": page},
                )
                callout_styles[callout_type] = entry
                return callout_type

            entry.left_border_color_hex = entry.left_border_color_hex or border_hex
            entry.font_color_hex = entry.font_color_hex or font_hex
            entry.icon_key = entry.icon_key or icon_key
            entry.trigger_instruction = entry.trigger_instruction or trigger_instruction
            return callout_type

        # ── Section / element plumbing ───────────────────────────

        def ensure_section(
            title: str,
            page: int,
            section_number: Optional[str] = None,
            heading_style: Optional[str] = None,
        ) -> TemplateSection:
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
                heading_style=heading_style,
                page_start=page,
                page_end=page,
            )
            sections.append(sec)
            current_section = sec
            return sec

        def flush_icons_onto(elem: TemplateElement):
            if not buffered_icons:
                return
            for icon_ref, _bbox in buffered_icons:
                elem.icons.append(icon_ref)
            buffered_icons.clear()

        def add_element(elem: TemplateElement, bbox: Optional[BoundingBox] = None):
            nonlocal current_section
            if current_section is None:
                current_section = TemplateSection(
                    section_number="0",
                    title="0 PREAMBLE",
                    page_start=elem.page,
                    page_end=elem.page,
                )
                sections.append(current_section)

            flush_icons_onto(elem)
            current_section.skeleton_elements.append(elem)
            current_section.page_end = max(current_section.page_end, elem.page)

        def attach_icon(icon_ref: TemplateIconRef, bbox: Optional[BoundingBox] = None):
            buffered_icons.append((icon_ref, bbox))

        def emit_instruction(
            text: str,
            color_hex: Optional[str] = None,
            detection_method: Optional[str] = None,
            icons: Optional[list[TemplateIconRef]] = None,
        ) -> TemplateInstruction:
            """Build an instruction, assign its id, and file it under the right scope."""
            nonlocal paragraph_counter, global_instruction_seq, last_instruction_text
            paragraph_counter += 1
            directive_type, machine_rule = _classify_instruction(text)
            is_global = not has_entered_first_section or current_section is None

            if is_global:
                global_instruction_seq += 1
                instruction_id = f"gr_{global_instruction_seq:03d}"
            else:
                bucket = current_section.section_number or str(len(sections))
                seq = section_instruction_seq.get(bucket, 0) + 1
                section_instruction_seq[bucket] = seq
                instruction_id = f"s{_id_slug(bucket)}_i{seq:03d}"

            instruction = TemplateInstruction(
                instruction_id=instruction_id,
                text=text,
                scope=InstructionScope.GLOBAL.value if is_global else InstructionScope.SECTION.value,
                directive_type=directive_type,
                font_color_hex=color_hex,
                color_detection_method=detection_method,
                paragraph_index=paragraph_counter,
                section_context=None if is_global else current_section.title,
                is_global=is_global,
                machine_rule=machine_rule,
                icons=list(icons or []),
            )

            if is_global:
                global_rules.instructions.append(instruction)
            else:
                current_section.authoring_instructions.append(instruction)
            last_instruction_text = text
            return instruction

        def check_is_instruction(
            node: Any,
        ) -> tuple[bool, Optional[str], Optional[str], Optional[str]]:
            """Check if a node represents a blue-font instruction.

            Returns ``(is_instruction, font_color_hex, detection_method, instruction_text)``.
            """
            meta = getattr(node, "metadata", {}) or {}
            is_inst = bool(meta.get("is_instruction", False))
            color_hex = meta.get("font_color_hex") or getattr(node, "font_color_hex", None)
            detection = meta.get("color_detection_method") or getattr(
                node, "color_detection_method", None
            )
            inst_text = meta.get("instruction_text")

            if not is_inst:
                if detection:
                    # The parser only records a detection method when it matched blue.
                    is_inst = True
                elif color_hex and str(color_hex).upper().lstrip("#") in TemplateDocxParser.BLUE_HEX_VALUES:
                    is_inst = True

            return is_inst, color_hex, detection, inst_text

        # ── Traversal ────────────────────────────────────────────

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
                heading_style = getattr(heading, "style_name", None) if heading else None

                is_preamble_heading = heading_text.upper() in _PREAMBLE_HEADINGS

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
                    ensure_section(heading_text, page, heading_style=heading_style)
                elif heading and heading_text and not is_preamble_heading:
                    if current_section is not None:
                        add_element(
                            TemplateElement(
                                element_type="heading",
                                page=page,
                                level=max(2, heading_level),
                                text=heading_text,
                                style_name=heading_style,
                            ),
                            bbox=bbox,
                        )

                for child in getattr(node, "children", []):
                    traverse(child, is_top=False)

            elif node_type == "heading":
                text = (getattr(node, "text", "") or "").strip()
                if text:
                    level = getattr(node, "level", 1)
                    heading_style = getattr(node, "style_name", None)
                    is_preamble_heading = text.upper() in _PREAMBLE_HEADINGS
                    is_major = False
                    if not is_preamble_heading:
                        if is_top or level <= 1:
                            is_major = True
                        else:
                            extracted_num = _extract_section_number(text)
                            if extracted_num and "." not in extracted_num:
                                is_major = True

                    if is_major:
                        ensure_section(text, page, heading_style=heading_style)
                    elif not is_preamble_heading and current_section is not None:
                        add_element(
                            TemplateElement(
                                element_type="heading",
                                page=page,
                                level=max(2, level),
                                text=text,
                                style_name=heading_style,
                            ),
                            bbox=bbox,
                        )

            elif node_type == "paragraph":
                text = (getattr(node, "text", "") or "").strip()
                if text:
                    is_inst, color_hex, detection, inst_text = check_is_instruction(node)
                    shading_hex = getattr(node, "shading_hex", None)

                    if is_inst:
                        # Blue text is an authoring instruction at whatever scope
                        # we are currently in; it is not part of the skeleton.
                        emit_instruction(text, color_hex, detection)
                        if has_entered_first_section:
                            add_element(
                                TemplateElement(
                                    element_type="paragraph",
                                    page=page,
                                    text=text,
                                    is_instruction=True,
                                    instruction_text=inst_text or text,
                                    font_color_hex=color_hex,
                                    color_detection_method=detection,
                                    shading_hex=shading_hex,
                                ),
                                bbox=bbox,
                            )
                    elif text.upper() not in _PREAMBLE_HEADINGS:
                        paragraph_counter += 1
                        add_element(
                            TemplateElement(
                                element_type="paragraph",
                                page=page,
                                text=text,
                                is_instruction=False,
                                shading_hex=shading_hex,
                            ),
                            bbox=bbox,
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

                    is_inst, color_hex, detection, _ = check_is_instruction(item)
                    if is_inst:
                        has_instruction_items = True
                        emit_instruction(item_text, color_hex, detection)

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
                # Captured before the table emits its own instructions, so a
                # trigger sitting in the paragraph above is still available.
                preceding_instruction = last_instruction_text
                table_elements, table_instructions = self._convert_table(
                    node,
                    page,
                    section_title=current_section.title if current_section else None,
                    register_icon=register_icon,
                    register_callout=register_callout,
                    emit_instruction=emit_instruction,
                    preceding_instruction=preceding_instruction,
                )
                if table_elements:
                    for table_elem in table_elements:
                        add_element(table_elem, bbox=bbox)
                elif table_instructions:
                    # Unwrapped layout container: emit each instruction as a
                    # paragraph element carrying its icon.
                    for t_inst in table_instructions:
                        add_element(
                            TemplateElement(
                                element_type="paragraph",
                                page=page,
                                text=t_inst.text,
                                instruction_text=t_inst.text,
                                font_color_hex=t_inst.font_color_hex,
                                color_detection_method=t_inst.color_detection_method,
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
                section_context = current_section.title if current_section else None
                icon_key = register_icon(node, section_context)
                if icon_key:
                    attach_icon(
                        TemplateIconRef(
                            icon_key=icon_key,
                            section_context=section_context,
                        ),
                        bbox=bbox,
                    )

            elif hasattr(node, "children"):
                for child in getattr(node, "children", []):
                    traverse(child, is_top=False)

        traverse(ast, is_top=True)

        if buffered_icons and current_section and current_section.skeleton_elements:
            flush_icons_onto(current_section.skeleton_elements[-1])

        # Remove empty PREAMBLE if all pre-heading items were absorbed into global_rules
        if sections and sections[0].title == "0 PREAMBLE" and not sections[0].skeleton_elements:
            sections.pop(0)

        self._finalize_sections(sections)
        self._relativize_output(list(icon_library.values()), sections)

        totals = TemplateTotals(
            sections=len(sections),
            elements=sum(len(sec.skeleton_elements) for sec in sections),
            instructions=len(global_rules.instructions)
            + sum(len(sec.authoring_instructions) for sec in sections),
            icons=len(icon_library),
            callouts=len(callout_styles),
        )

        return TemplateExtractionOutput(
            version="2.0",
            template_id=template_id,
            template_name=effective_name,
            metadata=metadata,
            icon_library=list(icon_library.values()),
            callout_styles=list(callout_styles.values()),
            global_rules=global_rules,
            sections=sections,
            totals=totals,
        )

    # ── Section contract ────────────────────────────────────────────

    @staticmethod
    def _finalize_sections(sections: list[TemplateSection]) -> None:
        """Derive the section contract fields from the collected content."""
        optional_markers = (
            "delete this section",
            "delete this chapter",
            "remove this section",
            "section is optional",
            "chapter is optional",
        )
        no_subsection_markers = (
            "do not add sub",
            "no subsection",
            "no sub-chapter",
            "subchapters are not",
            "sub-chapters are not",
        )

        for section in sections:
            instruction_texts = [i.text for i in section.authoring_instructions]
            skeleton_texts: list[str] = []
            for element in section.skeleton_elements:
                if element.text:
                    skeleton_texts.append(element.text)
                skeleton_texts.extend(element.items)
                skeleton_texts.extend(cell.text for cell in element.cells if cell.text)

            blob = " ".join(instruction_texts + skeleton_texts)
            instruction_blob = " ".join(instruction_texts).lower()
            title_low = section.title.lower()

            section.placeholders = _find_placeholders(blob)

            icon_keys: list[str] = []
            for element in section.skeleton_elements:
                for ref in element.icons:
                    if ref.icon_key not in icon_keys:
                        icon_keys.append(ref.icon_key)
                for cell in element.cells:
                    if cell.icon_key and cell.icon_key not in icon_keys:
                        icon_keys.append(cell.icon_key)
            for instruction in section.authoring_instructions:
                for ref in instruction.icons:
                    if ref.icon_key not in icon_keys:
                        icon_keys.append(ref.icon_key)
            section.icons_expected = icon_keys

            callout_types: list[str] = []
            for element in section.skeleton_elements:
                if element.callout_type and element.callout_type not in callout_types:
                    callout_types.append(element.callout_type)
            section.callouts_allowed = callout_types

            # A section whose skeleton already carries black prose is content the
            # migration must preserve verbatim; an empty one is the author's to fill.
            section.content_editable = not any(
                (element.text or "").strip()
                for element in section.skeleton_elements
                if not element.is_instruction and element.element_type in ("paragraph", "list")
            )
            section.required = not (
                "(optional)" in title_low
                or "(if applicable)" in title_low
                or any(marker in instruction_blob for marker in optional_markers)
            )
            section.allows_subsections = not any(
                marker in instruction_blob for marker in no_subsection_markers
            )

    # ── Table conversion ────────────────────────────────────────────

    def _convert_table(
        self,
        table: TableNode,
        page: int,
        section_title: Optional[str],
        register_icon: Callable[..., Optional[str]],
        register_callout: Callable[..., str],
        emit_instruction: Callable[..., TemplateInstruction],
        preceding_instruction: Optional[str] = None,
    ) -> tuple[list[TemplateElement], list[TemplateInstruction]]:
        """Convert a TableNode into template elements plus any instructions it carries.

        Returns a list because shaded infographic rows are promoted to individual
        ``callout`` elements rather than being rendered as a grid. An empty list
        with non-empty instructions means the table was an icon+instruction
        layout container that the caller should unwrap into paragraphs.
        """
        rows = getattr(table, "rows", [])
        if not rows:
            return [], []

        num_rows = len(rows)
        num_cols = getattr(table, "grid_cols", 0)
        if not num_cols:
            max_c = 0
            for r in rows:
                c_count = sum(getattr(cell, "col_span", 1) for cell in getattr(r, "cells", []))
                max_c = max(max_c, c_count)
            num_cols = max_c

        cells: list[TemplateTableCell] = []
        row_infos: list[dict[str, Any]] = []

        for row_idx, row in enumerate(rows):
            is_header = getattr(row, "is_header", False)
            info: dict[str, Any] = {
                "row_index": row_idx,
                "texts": [],
                "icon_refs": [],
                "icon_keys": [],
                "instruction_texts": [],
                "is_instruction": False,
                "color_hex": None,
                "detection_method": None,
                "shading_hex": None,
                "border_left_hex": None,
                "has_icon_in_first_col": False,
            }

            for cell in getattr(row, "cells", []):
                if not getattr(cell, "is_merge_origin", True):
                    continue

                cell_text_parts: list[str] = []
                icon_path: Optional[str] = None
                icon_key: Optional[str] = None
                image_path: Optional[str] = None
                cell_meta = getattr(cell, "metadata", {}) or {}
                cell_shading = getattr(cell, "shading_hex", None)
                cell_font_color: Optional[str] = None

                for item in getattr(cell, "content", []):
                    item_type = getattr(item, "node_type", None)
                    item_meta = getattr(item, "metadata", {}) or {}

                    if item_type in ("paragraph", "heading"):
                        t = (getattr(item, "text", "") or "").strip()
                        if t:
                            cell_text_parts.append(t)
                        cell_shading = cell_shading or getattr(item, "shading_hex", None)
                        cell_font_color = cell_font_color or getattr(item, "font_color_hex", None)
                        if item_meta.get("is_instruction"):
                            info["is_instruction"] = True
                            info["color_hex"] = item_meta.get("font_color_hex") or info["color_hex"]
                            info["detection_method"] = (
                                item_meta.get("color_detection_method") or info["detection_method"]
                            )
                            inst_t = item_meta.get("instruction_text") or t
                            if inst_t:
                                info["instruction_texts"].append(inst_t)
                    elif item_type == "highlight":
                        t = (getattr(item, "text", "") or "").strip()
                        if t:
                            cell_text_parts.append(t)
                        cell_shading = cell_shading or getattr(item, "color_hex", None)
                    elif item_type == "icon":
                        ip = getattr(item, "asset_path", None)
                        if ip:
                            key = register_icon(item, section_title)
                            if not icon_path:
                                icon_path = ip
                                icon_key = key
                            if key:
                                info["icon_keys"].append(key)
                                info["icon_refs"].append(
                                    TemplateIconRef(
                                        icon_key=key,
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
                    info["is_instruction"] = True
                    info["color_hex"] = cell_meta.get("font_color_hex") or info["color_hex"]
                    info["detection_method"] = (
                        cell_meta.get("color_detection_method") or info["detection_method"]
                    )
                    c_inst = cell_meta.get("instruction_text")
                    if c_inst and not info["instruction_texts"]:
                        info["instruction_texts"].append(c_inst)

                text = clean_table_cell_text(" ".join(cell_text_parts).strip())
                if text:
                    info["texts"].append(text)

                # An image alone in a cell is being used as an icon
                if image_path and not icon_path and not text:
                    icon_path = image_path
                    image_path = None
                    key = register_icon(section_context=section_title, asset_path=icon_path)
                    icon_key = key
                    if key:
                        info["icon_keys"].append(key)
                        info["icon_refs"].append(
                            TemplateIconRef(icon_key=key, section_context=section_title)
                        )

                col_index = getattr(cell, "col_index", 0)
                if col_index == 0 and icon_path:
                    info["has_icon_in_first_col"] = True

                info["shading_hex"] = info["shading_hex"] or cell_shading
                info["border_left_hex"] = info["border_left_hex"] or cell_meta.get(
                    "border_left_color_hex"
                )
                info["color_hex"] = info["color_hex"] or cell_font_color

                cells.append(
                    TemplateTableCell(
                        row_index=getattr(cell, "row_index", row_idx),
                        col_index=col_index,
                        row_span=getattr(cell, "row_span", 1),
                        col_span=getattr(cell, "col_span", 1),
                        text=text,
                        is_header=is_header,
                        icon_key=icon_key,
                        icon_path=icon_path,
                        image_path=image_path,
                        shading_hex=cell_shading,
                        text_direction=getattr(cell, "text_direction", None),
                        valign=getattr(cell, "valign", None),
                        bold=bool(getattr(cell, "bold", False)),
                    )
                )

            info["full_text"] = " ".join(info["texts"]).strip()
            for ref in info["icon_refs"]:
                ref.associated_text = info["full_text"]
            row_infos.append(info)

        if not any(c.text or c.icon_path or c.image_path or c.shading_hex for c in cells):
            return [], []

        shaded_rows = [info for info in row_infos if info["shading_hex"]]
        content_rows = [
            info for info in row_infos if info["full_text"] or info["icon_keys"]
        ]

        # An unshaded 2-column icon+text grid is a borderless layout container
        # used to align an icon beside its instruction, not a real table.
        is_layout_container = (
            num_cols == 2
            and not shaded_rows
            and all(info["is_instruction"] for info in row_infos)
            and all(info["icon_keys"] for info in row_infos)
            and all(info["has_icon_in_first_col"] for info in row_infos)
        )

        # Emit instructions in row order so paragraph indices stay sequential.
        # Cell icons stay on the cells. Copying them onto the table element makes
        # the renderer draw the same images again, above the grid, with no text.
        table_instructions: list[TemplateInstruction] = []
        for info in row_infos:
            if info["is_instruction"] and (info["instruction_texts"] or info["full_text"]):
                unique_texts: list[str] = []
                for txt in info["instruction_texts"]:
                    t_clean = txt.strip()
                    if t_clean and t_clean not in unique_texts:
                        unique_texts.append(t_clean)
                inst_text = " ".join(unique_texts).strip() if unique_texts else info["full_text"]
                table_instructions.append(
                    emit_instruction(
                        inst_text,
                        info["color_hex"],
                        info["detection_method"],
                        info["icon_refs"],
                    )
                )

        if is_layout_container:
            return [], table_instructions

        # Shaded rows are the template's coloured infographic boxes. Promote them
        # to callouts so their colours survive, and register the style so
        # migration can reproduce them instead of guessing.
        if shaded_rows:
            trigger = (
                table_instructions[-1].text if table_instructions else preceding_instruction
            )
            callout_elements: list[TemplateElement] = []
            for info in shaded_rows:
                icon_key = info["icon_keys"][0] if info["icon_keys"] else None
                callout_type = _callout_type_for(info["full_text"], trigger) or (
                    f"callout_{info['shading_hex'].lower()}"
                )
                register_callout(
                    callout_type,
                    f"#{info['shading_hex']}",
                    f"#{info['border_left_hex']}" if info["border_left_hex"] else None,
                    f"#{info['color_hex']}" if info["color_hex"] else None,
                    icon_key,
                    trigger,
                    section_title,
                    page,
                )
                callout_elements.append(
                    TemplateElement(
                        element_type="callout",
                        page=page,
                        text=info["full_text"],
                        callout_type=callout_type,
                        shading_hex=info["shading_hex"],
                        font_color_hex=info["color_hex"],
                        icons=list(info["icon_refs"]),
                        is_instruction=info["is_instruction"],
                    )
                )

            # Every content-bearing row is a callout — no grid left to render.
            if len(shaded_rows) >= len(content_rows):
                return callout_elements, table_instructions

            # Mixed table: keep the grid (cells retain their shading) and still
            # register the styles above so nothing is lost either way.

        cells, num_rows, num_cols = self._collapse_cells(cells, num_rows, num_cols)

        table_elem = TemplateElement(
            element_type="table",
            page=page,
            title=getattr(table, "caption", None),
            num_rows=num_rows,
            num_cols=num_cols,
            header_rows=getattr(table, "header_rows", 0) or None,
            style_name=getattr(table, "style_name", None),
            col_widths_pt=list(getattr(table, "col_widths_pt", []) or []),
            cells=cells,
            is_instruction=bool(table_instructions),
        )

        return [table_elem], table_instructions

    @staticmethod
    def _collapse_cells(
        cells: list[TemplateTableCell], num_rows: int, num_cols: int
    ) -> tuple[list[TemplateTableCell], int, int]:
        """Collapse redundant empty columns in table cells."""
        used_cols = {
            c.col_index
            for c in cells
            if c.text or c.icon_path or c.image_path or c.shading_hex
        }
        if not used_cols or len(used_cols) == num_cols:
            return cells, num_rows, num_cols

        col_remap = {old: new for new, old in enumerate(sorted(used_cols))}
        new_cells = []
        for c in cells:
            if c.col_index in col_remap:
                c.col_index = col_remap[c.col_index]
                new_cells.append(c)

        return new_cells, num_rows, len(col_remap)
