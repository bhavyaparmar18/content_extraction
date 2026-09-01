"""TOC builder service for inserting Word-native Table of Contents fields and verifying heading styles."""

from __future__ import annotations

import re
from typing import Optional
from docx import Document
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from loguru import logger


class TOCBuilder:
    """Inserts a native Word TOC field that updates automatically from heading styles."""

    def insert_toc(self, doc: Document, plan=None):
        """Insert a native Word TOC field code after the Table of Contents heading."""
        toc_heading_idx = self._find_toc_heading(doc)

        if toc_heading_idx is not None:
            insert_after = doc.paragraphs[toc_heading_idx]._element
        else:
            # Create a new TOC heading
            toc_para = doc.add_paragraph("TABLE OF CONTENTS")
            if "Heading 1" in [s.name for s in doc.styles]:
                toc_para.style = doc.styles["Heading 1"]
            insert_after = toc_para._element

        # Create the TOC field element
        toc_field_para = self._create_toc_field_paragraph()

        # Insert after heading element
        insert_after.addnext(toc_field_para)
        logger.info("Inserted Word-native Table of Contents (TOC) field")

    def verify_heading_styles(self, doc: Document) -> list[str]:
        """Check all paragraphs and return list of headings not using native Word styles."""
        issues: list[str] = []

        for i, para in enumerate(doc.paragraphs):
            style_name = para.style.name if para.style else ""
            if style_name.startswith("Heading"):
                continue

            text = para.text.strip()
            if text and len(text) < 100:
                # Check for numbered heading pattern: e.g., "1 PURPOSE", "6.1 LANGUAGE"
                if re.match(r"^\d+(\.\d+)*\s+[A-Z]", text):
                    issues.append(
                        f"Paragraph[{i}] '{text[:50]}' appears to be a heading but uses style '{style_name}'"
                    )

        return issues

    def _find_toc_heading(self, doc: Document) -> Optional[int]:
        """Find the paragraph index of the TOC heading."""
        for i, para in enumerate(doc.paragraphs):
            text = para.text.strip().upper()
            if text in ("TABLE OF CONTENTS", "TABLE OF CONTENT", "CONTENTS", "INDEX"):
                return i
        return None

    def _create_toc_field_paragraph(self) -> OxmlElement:
        """Create a Word OXML paragraph containing the TOC field code.

        Inserts:
          <w:p>
            <w:r><w:fldChar w:fldCharType="begin"/></w:r>
            <w:r><w:instrText xml:space="preserve"> TOC \\o "1-3" \\h \\z \\u </w:instrText></w:r>
            <w:r><w:fldChar w:fldCharType="separate"/></w:r>
            <w:r><w:t>Right-click to update this Table of Contents</w:t></w:r>
            <w:r><w:fldChar w:fldCharType="end"/></w:r>
          </w:p>
        """
        paragraph = OxmlElement("w:p")

        # Begin field
        r_begin = OxmlElement("w:r")
        fld_begin = OxmlElement("w:fldChar")
        fld_begin.set(qn("w:fldCharType"), "begin")
        r_begin.append(fld_begin)
        paragraph.append(r_begin)

        # Field instruction
        r_instr = OxmlElement("w:r")
        instr_text = OxmlElement("w:instrText")
        instr_text.set(qn("xml:space"), "preserve")
        instr_text.text = ' TOC \\o "1-3" \\h \\z \\u '
        r_instr.append(instr_text)
        paragraph.append(r_instr)

        # Separator
        r_sep = OxmlElement("w:r")
        fld_sep = OxmlElement("w:fldChar")
        fld_sep.set(qn("w:fldCharType"), "separate")
        r_sep.append(fld_sep)
        paragraph.append(r_sep)

        # Placeholder text
        r_text = OxmlElement("w:r")
        text_el = OxmlElement("w:t")
        text_el.text = "Right-click to update Table of Contents"
        r_text.append(text_el)
        paragraph.append(r_text)

        # End field
        r_end = OxmlElement("w:r")
        fld_end = OxmlElement("w:fldChar")
        fld_end.set(qn("w:fldCharType"), "end")
        r_end.append(fld_end)
        paragraph.append(r_end)

        return paragraph
