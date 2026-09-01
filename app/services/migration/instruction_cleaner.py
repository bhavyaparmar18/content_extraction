"""Instruction cleaner service for removing blue instructional text and unused template scaffolding."""

from __future__ import annotations

import re
from typing import Optional, Set, Any
from docx import Document
from loguru import logger

from app.services.migration.schemas import MigrationPlan


class InstructionCleaner:
    """Removes all template scaffolding: blue instructional runs/paragraphs, instructional tables, and unused optional sections."""

    BLUE_HEX_VALUES = {
        "0000FF", "0070C0", "4472C4", "2E74B5", "5B9BD5", "00B0F0",
        "1F4E78", "2F5597", "41719C", "002060", "1B365D", "0072CE",
        "0075FF", "00A2E8", "004B87", "0080FF", "0099FF", "0066CC",
        "1B75BB", "005696", "3399FF", "003366", "2E75B6",
    }
    BRIGHT_BLUE_HEX_VALUES = {
        "0075FF", "0000FF", "0070C0", "00B0F0", "0072CE", "00A2E8",
        "0080FF", "0099FF", "3399FF", "4472C4", "2E74B5", "5B9BD5",
    }
    RED_HEX_VALUES = {
        "FF0000", "C00000", "E00000", "CC0000", "990000",
    }

    INSTRUCTION_KEYWORDS = (
        "brief description of what",
        "brief description of the intention",
        "explain which target roles",
        "executive summary/introduction",
        "explanation section",
        "attention section",
        "key-take-away section",
        "embedding of files is not possible",
        "for global and (cross-) divisional gp docs",
        "to ensure effective communication and compliance",
    )

    def clean(
        self,
        doc: Document,
        plan: MigrationPlan,
        protected_tbl_elements: Optional[Set[Any]] = None,
        clean_tables: bool = True,
    ):
        """Execute full cleanup on the output document."""
        # 1. Collect all explicit paragraph elements marked by LLM plan
        elements_to_delete = set()
        for sp in plan.section_plans:
            for idx in sp.template_paragraph_indices_to_delete:
                if 0 <= idx < len(doc.paragraphs):
                    elements_to_delete.add(doc.paragraphs[idx]._element)
            # Clear indices so a subsequent pass does not mistakenly delete shifted paragraphs
            sp.template_paragraph_indices_to_delete = []

        # 2. Clean instructional and unused scaffolding tables (must run BEFORE clearing cell paragraph runs)
        if clean_tables:
            self.clean_tables(doc, protected_tbl_elements=protected_tbl_elements)

        # 3. Safety net: Scan ALL remaining paragraphs (including any in valid tables)
        WNS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
        for p_elem in doc.element.body.iter(f"{{{WNS}}}p"):
            para = None
            try:
                from docx.text.paragraph import Paragraph
                para = Paragraph(p_elem, doc)
            except Exception:
                continue
            if self._is_instructional_paragraph(para):
                elements_to_delete.add(p_elem)

        # 4. Delete paragraphs by element reference
        deleted_count = 0
        for elem in elements_to_delete:
            parent = elem.getparent()
            if parent is not None:
                if parent.tag.endswith("tc") and len(parent.xpath("./w:p")) <= 1:
                    # Do not delete the only paragraph in a cell; clear its runs instead
                    for child in list(elem):
                        if child.tag.endswith("r") or child.tag.endswith("proofErr"):
                            elem.remove(child)
                else:
                    parent.remove(elem)
                deleted_count += 1

        logger.info(f"InstructionCleaner: Deleted/cleared {deleted_count} blue/instructional paragraphs")

        # 5. Remove sections marked for deletion (e.g. optional Distribution section)
        for sp in plan.section_plans:
            if not sp.has_source_content and sp.fallback_action == "delete_section":
                self._delete_section_by_heading(doc, sp.template_section_heading)

    def clean_tables(self, doc: Document, protected_tbl_elements: Optional[Set[Any]] = None):
        """Remove instructional callout tables and unpopulated template placeholder tables."""
        tables_to_remove = []
        protected = protected_tbl_elements or set()

        for tbl in list(doc.tables):
            if tbl._element in protected:
                continue

            # Check if this is a cover page vault table
            is_vault = False
            all_text_list = []
            has_blue_in_table = False
            has_instruction_kw = False
            has_placeholder_token = False

            for row in tbl.rows:
                for cell in row.cells:
                    txt = cell.text.strip()
                    if "${vault:" in txt.lower():
                        is_vault = True
                        break
                    if txt:
                        all_text_list.append(txt)
                    txt_lower = txt.lower()
                    if any(kw in txt_lower for kw in self.INSTRUCTION_KEYWORDS):
                        has_instruction_kw = True
                    if re.search(r"(\[Insert\s+[^\]]+\]|\[Role\s*\d+\]|e\.g\.,\s*xxx-AD|\bn\.0\b)", txt, re.I):
                        has_placeholder_token = True

                    for p in cell.paragraphs:
                        if self._is_instructional_paragraph(p):
                            has_blue_in_table = True

                if is_vault:
                    break

            if is_vault:
                continue

            # Check if table should be deleted:
            # 1. Has bright blue text or instructional keywords
            if has_blue_in_table or has_instruction_kw:
                tables_to_remove.append(tbl._element)
                continue

            # 2. Is Infographics guide table ("Infographics | Description")
            if tbl.rows and len(tbl.rows[0].cells) >= 2:
                r0_texts = [c.text.strip().lower() for c in tbl.rows[0].cells]
                if "infographics" in r0_texts and "description" in r0_texts:
                    tables_to_remove.append(tbl._element)
                    continue

            # 3. Empty or unpopulated placeholder table
            # If all data rows (row 1+) are empty or contain only placeholder tokens
            if len(tbl.rows) > 1:
                data_rows_have_content = False
                for r_idx in range(1, len(tbl.rows)):
                    for cell in tbl.rows[r_idx].cells:
                        c_txt = cell.text.strip()
                        if c_txt and not re.search(r"^(\d+|n\.0|\[Insert[^\]]*\]|\[Role[^\]]*\]|e\.g\..*)$", c_txt, re.I):
                            data_rows_have_content = True
                            break
                    if data_rows_have_content:
                        break
                if not data_rows_have_content and has_placeholder_token:
                    tables_to_remove.append(tbl._element)
                    continue

        deleted_tables_count = 0
        for elem in tables_to_remove:
            parent = elem.getparent()
            if parent is not None:
                parent.remove(elem)
                deleted_tables_count += 1

        if deleted_tables_count:
            logger.info(f"InstructionCleaner: Deleted {deleted_tables_count} instructional/scaffolding tables")

        # Strip any extra completely blank row 0 from remaining non-vault tables
        for tbl in list(doc.tables):
            if tbl._element in tables_to_remove:
                continue
            is_vault = any("${vault:" in c.text.lower() for r in tbl.rows for c in r.cells)
            if is_vault:
                continue
            if len(tbl.rows) > 1 and all(not c.text.strip() for c in tbl.rows[0].cells):
                first_tr = tbl.rows[0]._tr
                if first_tr.getparent() is not None:
                    first_tr.getparent().remove(first_tr)
                    logger.info("InstructionCleaner: Stripped extra empty row 0 from table")

    def _has_blue_runs(self, para) -> bool:
        """Check if any run in paragraph has blue/instruction font color."""
        return self._is_instructional_paragraph(para)

    def _is_blue_color(self, hex_val: Optional[str] = None, rgb_tuple: Optional[tuple] = None) -> bool:
        """Helper to determine if a color is blue."""
        if hex_val:
            clean = hex_val.upper().lstrip("#")
            if clean in self.BLUE_HEX_VALUES:
                return True
            if len(clean) == 6:
                try:
                    r = int(clean[0:2], 16)
                    g = int(clean[2:4], 16)
                    b = int(clean[4:6], 16)
                    if (b > 130 and b > r + 30) or (b > 140 and r < 100):
                        return True
                except ValueError:
                    pass

        if rgb_tuple and len(rgb_tuple) >= 3:
            try:
                r, g, b = rgb_tuple[0], rgb_tuple[1], rgb_tuple[2]
                if (b > 130 and b > r + 30) or (b > 140 and r < 100):
                    return True
            except Exception:
                pass

        return False

    def _is_instructional_paragraph(self, para) -> bool:
        """Check if paragraph is template scaffolding (blue/red text or instruction style)."""
        WNS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

        # Check for instruction keywords in paragraph text
        p_text = (para.text or "").strip().lower()
        if any(kw in p_text for kw in self.INSTRUCTION_KEYWORDS):
            return True

        # Style check: explicit "instruction" style
        if para.style and para.style.name:
            st_name = para.style.name.lower()
            if "instruction" in st_name:
                return True

        # Check run colors
        has_blue = False
        has_red = False
        has_bright_blue = False

        for run in para.runs:
            # 1. Python-docx RGB
            if run.font and run.font.color and run.font.color.rgb:
                rgb_str = str(run.font.color.rgb).upper()
                if rgb_str in self.RED_HEX_VALUES:
                    has_red = True
                if rgb_str in self.BRIGHT_BLUE_HEX_VALUES:
                    has_bright_blue = True
                if self._is_blue_color(rgb_str, run.font.color.rgb):
                    has_blue = True

            # 2. OXML color
            r_pr = run._element.find(f"{{{WNS}}}rPr")
            if r_pr is not None:
                color_el = r_pr.find(f"{{{WNS}}}color")
                if color_el is not None:
                    val = (
                        color_el.get(f"{{{WNS}}}val", "")
                        or color_el.get("w:val", "")
                        or color_el.get("val", "")
                    ).upper()
                    if val in self.RED_HEX_VALUES:
                        has_red = True
                    if val in self.BRIGHT_BLUE_HEX_VALUES:
                        has_bright_blue = True
                    if self._is_blue_color(val):
                        has_blue = True

                    theme_color = (
                        color_el.get(f"{{{WNS}}}themeColor", "")
                        or color_el.get("w:themeColor", "")
                        or color_el.get("themeColor", "")
                    ).lower()
                    if theme_color in {"accent1", "accent2", "accent5", "hyperlink"}:
                        has_blue = True
                        has_bright_blue = True

        # 3. Paragraph-level formatting
        p_pr = para._element.find(f"{{{WNS}}}pPr")
        if p_pr is not None:
            r_pr = p_pr.find(f"{{{WNS}}}rPr")
            if r_pr is not None:
                color_el = r_pr.find(f"{{{WNS}}}color")
                if color_el is not None:
                    val = (
                        color_el.get(f"{{{WNS}}}val", "")
                        or color_el.get("w:val", "")
                        or color_el.get("val", "")
                    ).upper()
                    if self._is_blue_color(val):
                        has_blue = True
                    if val in self.BRIGHT_BLUE_HEX_VALUES:
                        has_bright_blue = True

        if not has_blue and not has_red:
            return False

        # Table header row protection:
        # ONLY protect row 0 if the table has MULTIPLE rows (> 1 row)
        # AND the text is NOT bright blue instruction text (e.g. 0075FF).
        try:
            parent_tc = para._element.getparent()
            if parent_tc is not None and parent_tc.tag.endswith("tc"):
                parent_tr = parent_tc.getparent()
                if parent_tr is not None and parent_tr.tag.endswith("tr"):
                    parent_tbl = parent_tr.getparent()
                    if parent_tbl is not None and parent_tbl.tag.endswith("tbl"):
                        tr_elements = parent_tbl.xpath("./w:tr")
                        # If table only has 1 row, it is a callout/instruction box, NOT a header!
                        if len(tr_elements) > 1 and parent_tr == tr_elements[0]:
                            # If row 0 has bright blue instructional color, do not protect it
                            if not has_bright_blue:
                                return False
        except Exception:
            pass

        return True

    def _delete_section_by_heading(self, doc: Document, heading_text: str):
        """Remove a section heading and its immediate child paragraphs and tables."""
        norm_target = heading_text.strip().lower()
        to_delete = []
        found_heading = False

        for para in doc.paragraphs:
            p_text = para.text.strip().lower()
            if p_text == norm_target or (norm_target and norm_target in p_text and len(p_text) < 80):
                found_heading = True
                to_delete.append(para._element)
                continue

            if found_heading:
                style_name = para.style.name if para.style else ""
                if style_name.startswith("Heading 1") or style_name.startswith("Heading 2"):
                    break
                to_delete.append(para._element)

        for elem in to_delete:
            parent = elem.getparent()
            if parent is not None:
                parent.remove(elem)

        if to_delete:
            logger.info(f"Deleted unused section '{heading_text}' ({len(to_delete)} elements removed)")
