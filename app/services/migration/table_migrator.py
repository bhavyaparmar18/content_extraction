from __future__ import annotations

from pathlib import Path
from typing import Optional
from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from loguru import logger

from app.schemas.migration import MigrationElement, DocxMigrationOutput, MigrationTableCell
from app.services.migration.schemas import PlaceholderTablePlan


class TableMigrator:
    """Constructs brand-new Word tables and populates or deletes placeholder tables."""

    def insert_table(
        self,
        doc: Document,
        source_element: MigrationElement,
        font_family: str = "Arial",
    ):
        """Build a new Word table with proper borders, padding, widths, and left-aligned icons."""
        num_rows = max(1, source_element.num_rows or 1)
        num_cols = max(1, source_element.num_cols or 1)

        # Build table
        table = doc.add_table(rows=num_rows, cols=num_cols)
        if "Table Grid" in [s.name for s in doc.styles]:
            table.style = "Table Grid"

        # Apply table styling (alignment, cell padding, borders, column widths)
        self._set_table_styling(table, num_cols, source_element=source_element)

        # Track written cells to avoid duplicate overwrites on merged spans
        written_positions = set()

        for cell_data in source_element.cells:
            r_idx = cell_data.row_index
            c_idx = cell_data.col_index

            if r_idx >= num_rows or c_idx >= num_cols:
                continue

            cell = table.cell(r_idx, c_idx)
            is_hdr = cell_data.is_header or (r_idx == 0 and num_rows > 1)

            # Populate cell with icon on the left (if present) and text
            self._populate_cell(
                cell=cell,
                text=cell_data.text or "",
                font_family=font_family,
                is_header=is_hdr,
                icon_path=cell_data.icon_path,
                image_path=cell_data.image_path,
                background_color=cell_data.background_color,
            )

            # Handle cell merging
            if cell_data.col_span > 1 or cell_data.row_span > 1:
                end_r = min(num_rows - 1, r_idx + cell_data.row_span - 1)
                end_c = min(num_cols - 1, c_idx + cell_data.col_span - 1)
                try:
                    target_cell = table.cell(end_r, end_c)
                    cell.merge(target_cell)
                except Exception as exc:
                    logger.debug(f"Cell merge error at [{r_idx},{c_idx}] to [{end_r},{end_c}]: {exc}")

            written_positions.add((r_idx, c_idx))

        # If row 0 is completely empty (no text in any cell) and there are multiple rows, remove the extra empty row
        if len(table.rows) > 1 and all(not c.text.strip() for c in table.rows[0].cells):
            first_tr = table.rows[0]._tr
            if first_tr.getparent() is not None:
                first_tr.getparent().remove(first_tr)

        return table

    def populate(
        self,
        doc: Document,
        plan: PlaceholderTablePlan,
        extracted: DocxMigrationOutput,
    ):
        """Populate an existing template placeholder table with extracted cell data."""
        if plan.table_index >= len(doc.tables):
            logger.warning(f"Table index {plan.table_index} exceeds document table count ({len(doc.tables)})")
            return

        template_table = doc.tables[plan.table_index]
        source_elem = self._find_source_table(extracted, plan)

        if source_elem is None:
            logger.warning(f"Source table for placeholder '{plan.table_purpose}' not found")
            return

        # Apply standard table styling
        num_cols = len(template_table.columns) or 2
        self._set_table_styling(template_table, num_cols, source_element=source_elem)

        # Extract structured data rows (cells) from source table
        data_rows = self._extract_data_cell_rows(source_elem)

        # Sort alphabetically if required
        if plan.sort_alphabetically and data_rows:
            data_rows.sort(key=lambda row: (row[0].text or "").lower() if row else "")

        if not data_rows:
            return

        # Use the first data row (index 1) as the placeholder row to overwrite
        placeholder_row_index = 1
        if len(template_table.rows) <= 1:
            # If there's no placeholder row, just add one
            template_table.add_row()

        placeholder_row = template_table.rows[placeholder_row_index]
        
        # Capture shading from the placeholder row to apply to new rows
        from docx.oxml.ns import qn
        from docx.oxml import parse_xml
        from docx.oxml.ns import nsdecls
        
        placeholder_shading = []
        for c in placeholder_row.cells:
            shading = None
            tcPr = c._tc.get_or_add_tcPr()
            shd = tcPr.find(qn("w:shd"))
            if shd is not None:
                shading = shd.get(qn("w:fill"))
            placeholder_shading.append(shading)

        # Total rows needed: header row (placeholder_row_index) + data rows
        total_needed = placeholder_row_index + len(data_rows)

        # Add missing rows if template table has fewer rows than needed
        while len(template_table.rows) < total_needed:
            new_row = template_table.add_row()
            # Copy shading to new row
            for col_idx, target_cell in enumerate(new_row.cells):
                if col_idx < len(placeholder_shading) and placeholder_shading[col_idx]:
                    shading_elm = parse_xml(r'<w:shd {} w:fill="{}"/>'.format(nsdecls('w'), placeholder_shading[col_idx]))
                    target_cell._tc.get_or_add_tcPr().append(shading_elm)

        # Remove excess placeholder rows if template table has more rows than needed
        while len(template_table.rows) > total_needed:
            excess_tr = template_table.rows[-1]._tr
            excess_tr.getparent().remove(excess_tr)

        # Clear existing text in all placeholder rows to be populated
        for r_idx in range(placeholder_row_index, total_needed):
            for c in template_table.rows[r_idx].cells:
                c.text = ""

        # Populate all data rows starting from the placeholder row index
        for r_idx, row_cells in enumerate(data_rows):
            target_row = template_table.rows[placeholder_row_index + r_idx]
            tr_pr = target_row._tr.get_or_add_trPr()
            tr_pr.append(OxmlElement("w:cantSplit"))

            if len(target_row.cells) == len(row_cells):
                for col_idx, cell_obj in enumerate(row_cells):
                    target_cell = target_row.cells[col_idx]
                    self._populate_cell(
                        cell=target_cell,
                        text=cell_obj.text or "",
                        font_family="Arial",
                        is_header=False,
                        icon_path=cell_obj.icon_path,
                        image_path=cell_obj.image_path,
                        background_color=cell_obj.background_color,
                    )
            else:
                # Source row has different number of columns than template table.
                # Intelligently map content cells to the available template columns:
                content_cells = [c for c in row_cells if (c.text and c.text.strip()) or c.icon_path or c.image_path]
                if len(target_row.cells) == 2 and content_cells:
                    # 2-col template table (e.g. Infographics | Description):
                    # Col 0 gets media/icon or first short token, Col 1 gets description text
                    media_cell = next((c for c in content_cells if c.icon_path or c.image_path), None)
                    text_cells = [c for c in content_cells if c.text and c.text.strip()]

                    if media_cell and text_cells:
                        self._populate_cell(
                            cell=target_row.cells[0],
                            text=media_cell.text or "",
                            font_family="Arial",
                            is_header=False,
                            icon_path=media_cell.icon_path,
                            image_path=media_cell.image_path,
                            background_color=media_cell.background_color,
                        )
                        full_text = "\n".join(c.text.strip() for c in text_cells)
                        self._populate_cell(
                            cell=target_row.cells[1],
                            text=full_text,
                            font_family="Arial",
                            is_header=False,
                            background_color=text_cells[0].background_color,
                        )
                    else:
                        for col_idx in range(min(len(target_row.cells), len(content_cells))):
                            c_obj = content_cells[col_idx]
                            self._populate_cell(
                                cell=target_row.cells[col_idx],
                                text=c_obj.text or "",
                                font_family="Arial",
                                is_header=False,
                                icon_path=c_obj.icon_path,
                                image_path=c_obj.image_path,
                                background_color=c_obj.background_color,
                            )
                else:
                    for col_idx, cell_obj in enumerate(row_cells[:len(target_row.cells)]):
                        target_cell = target_row.cells[col_idx]
                        self._populate_cell(
                            cell=target_cell,
                            text=cell_obj.text or "",
                            font_family="Arial",
                            is_header=False,
                            icon_path=cell_obj.icon_path,
                            image_path=cell_obj.image_path,
                            background_color=cell_obj.background_color,
                        )

        # Ensure header row (row 0) has header text if it is currently blank
        header_cells = [c for c in source_elem.cells if c.row_index == 0 and c.text and c.text.strip()]
        if header_cells and all(not c.text.strip() for c in template_table.rows[0].cells):
            for cell_obj in header_cells:
                if cell_obj.col_index < len(template_table.rows[0].cells):
                    self._populate_cell(
                        cell=template_table.rows[0].cells[cell_obj.col_index],
                        text=cell_obj.text or "",
                        font_family="Arial",
                        is_header=True,
                    )

        # If row 0 is completely blank after population, remove the extra empty row
        if len(template_table.rows) > 1 and all(not c.text.strip() for c in template_table.rows[0].cells):
            first_tr = template_table.rows[0]._tr
            if first_tr.getparent() is not None:
                first_tr.getparent().remove(first_tr)

        logger.info(f"Populated placeholder table {plan.table_index} ('{plan.table_purpose}') with {len(data_rows)} rows")

    def delete_table(self, doc: Document, table_index: int):
        """Remove a table from the document by index."""
        if 0 <= table_index < len(doc.tables):
            tbl = doc.tables[table_index]
            tbl._element.getparent().remove(tbl._element)
            logger.info(f"Deleted unused placeholder table at index {table_index}")

    def _set_table_styling(self, table, num_cols: int, source_element: Optional[MigrationElement] = None):
        """Configure table-level borders, cell padding, and intelligent column widths."""
        tbl_pr = table._tbl.tblPr

        # 1. Center alignment
        jc = OxmlElement("w:jc")
        jc.set(qn("w:val"), "center")
        tbl_pr.append(jc)

        # 2. Table cell margins (padding: top/bottom 6pt, left/right 8pt)
        tbl_cell_mar = OxmlElement("w:tblCellMar")
        for side, val in [("top", "120"), ("bottom", "120"), ("left", "160"), ("right", "160")]:
            m = OxmlElement(f"w:{side}")
            m.set(qn("w:w"), val)
            m.set(qn("w:type"), "dxa")
            tbl_cell_mar.append(m)
        tbl_pr.append(tbl_cell_mar)

        # 3. Clean borders
        tbl_borders = OxmlElement("w:tblBorders")
        for side in ["top", "left", "bottom", "right", "insideH", "insideV"]:
            b = OxmlElement(f"w:{side}")
            b.set(qn("w:val"), "single")
            b.set(qn("w:sz"), "4")
            b.set(qn("w:space"), "0")
            b.set(qn("w:color"), "D3D3D3")
            tbl_borders.append(b)
        tbl_pr.append(tbl_borders)

        # 4. Set column widths intelligently
        widths = self._calculate_column_widths(num_cols, source_element)
        for row in table.rows:
            tr_pr = row._tr.get_or_add_trPr()
            tr_pr.append(OxmlElement("w:cantSplit"))
            for col_idx, cell in enumerate(row.cells):
                if col_idx < len(widths):
                    cell.width = Inches(widths[col_idx])

        # 5. Header row repeat across page splits
        if table.rows:
            r0_pr = table.rows[0]._tr.get_or_add_trPr()
            r0_pr.append(OxmlElement("w:tblHeader"))

    def _calculate_column_widths(
        self, num_cols: int, source_element: Optional[MigrationElement] = None
    ) -> list[float]:
        """Determine column widths in inches for clean document aesthetics."""
        total_width = 6.5

        if source_element and source_element.cells:
            col0_has_media = any(c.icon_path or c.image_path for c in source_element.cells if c.col_index == 0)
            col0_all_short = all(len((c.text or "").strip()) < 15 for c in source_element.cells if c.col_index == 0)

            if num_cols == 2 and col0_has_media and col0_all_short:
                # 2-col icon box: compact left column for icon, wide right column for content
                return [0.9, 5.6]

            if num_cols == 4 and any(c.icon_path or c.image_path for c in source_element.cells if c.col_index in (0, 1)):
                # 4-col infographic / callout box
                return [0.3, 0.9, 0.2, 5.1]

            if num_cols == 2:
                return [1.8, 4.7]

            if num_cols == 3:
                return [1.5, 2.0, 3.0]

        if num_cols == 2:
            return [1.8, 4.7]
        elif num_cols == 3:
            return [1.5, 2.0, 3.0]
        else:
            w = total_width / max(1, num_cols)
            return [w] * num_cols

    def _populate_cell(
        self,
        cell,
        text: str,
        font_family: str,
        is_header: bool = False,
        icon_path: Optional[str] = None,
        image_path: Optional[str] = None,
        background_color: Optional[str] = None,
    ):
        """Populate cell contents with left-aligned icon (if any), text, and styling."""
        cell.text = ""
        para = cell.paragraphs[0]
        para.paragraph_format.line_spacing = 1.15
        para.paragraph_format.space_after = Pt(2.0)

        # 1. Embed icon on the LEFT if present (24pt legible size)
        if icon_path:
            p = Path(icon_path)
            if p.exists():
                try:
                    icon_run = para.add_run()
                    icon_run.add_picture(str(p), width=Pt(24.0), height=Pt(24.0))
                    if text.strip():
                        para.add_run("\u2003\u2002")
                except Exception as exc:
                    logger.debug(f"Failed to embed icon in cell: {exc}")

        # 2. Embed image on the LEFT if present (36pt size)
        if image_path:
            p = Path(image_path)
            if p.exists():
                try:
                    img_run = para.add_run()
                    img_run.add_picture(str(p), width=Pt(36.0), height=Pt(36.0))
                    if text.strip():
                        para.add_run("\u2003\u2002")
                except Exception as exc:
                    logger.debug(f"Failed to embed image in cell: {exc}")

        # 3. Add text
        if text.strip():
            text_run = para.add_run(text)
            text_run.font.name = font_family
            text_run.font.size = Pt(9.5)
            if is_header:
                text_run.bold = True
                text_run.font.color.rgb = RGBColor(0x1F, 0x4E, 0x78)

        # 4. Apply background color shading when present (from source document highlights)
        if background_color:
            hex_color = background_color.lstrip("#").upper()
            tc_pr = cell._tc.get_or_add_tcPr()
            shd = OxmlElement("w:shd")
            shd.set(qn("w:val"), "clear")
            shd.set(qn("w:color"), "auto")
            shd.set(qn("w:fill"), hex_color)
            tc_pr.append(shd)

    def _extract_data_cell_rows(self, source_elem: MigrationElement) -> list[list[MigrationTableCell]]:
        """Extract rows of MigrationTableCell objects from a MigrationElement table."""
        num_rows = source_elem.num_rows or 0
        num_cols = source_elem.num_cols or 0

        grid: list[list[MigrationTableCell]] = [
            [MigrationTableCell(row_index=r, col_index=c, text="") for c in range(num_cols)]
            for r in range(num_rows)
        ]

        for c in source_elem.cells:
            if 0 <= c.row_index < num_rows and 0 <= c.col_index < num_cols:
                grid[c.row_index][c.col_index] = c

        # Filter out header row (row 0) if it was headers
        data_rows = []
        for r_idx, row in enumerate(grid):
            is_header_row = any(c.is_header for c in row) or (r_idx == 0 and num_rows > 1)
            has_content = any((c.text and c.text.strip()) or c.icon_path or c.image_path for c in row)

            if has_content:
                if not is_header_row or r_idx > 0:
                    data_rows.append(row)

        return data_rows or (grid[1:] if len(grid) > 1 else grid)

    def _find_source_table(
        self, extracted: DocxMigrationOutput, plan: PlaceholderTablePlan
    ) -> Optional[MigrationElement]:
        """Locate the source table in extracted JSON matching the plan."""
        for sec in extracted.sections:
            if plan.source_section_title and sec.title == plan.source_section_title:
                if plan.source_element_index is not None and plan.source_element_index < len(sec.elements):
                    elem = sec.elements[plan.source_element_index]
                    if elem.element_type == "table":
                        return elem
                # Fallback: first table in this section
                for elem in sec.elements:
                    if elem.element_type == "table":
                        return elem

        # Global fallback: search by purpose matching
        for sec in extracted.sections:
            for elem in sec.elements:
                if elem.element_type == "table":
                    if plan.table_purpose.lower() in (sec.title.lower() + (elem.title or "").lower()):
                        return elem

        return None

    def _extract_data_rows(self, source_elem: MigrationElement) -> list[list[str]]:
        """Extract rows of text strings from a MigrationElement table."""
        num_rows = source_elem.num_rows or 0
        num_cols = source_elem.num_cols or 0

        grid: list[list[str]] = [["" for _ in range(num_cols)] for _ in range(num_rows)]

        for c in source_elem.cells:
            if 0 <= c.row_index < num_rows and 0 <= c.col_index < num_cols:
                grid[c.row_index][c.col_index] = c.text or ""

        # Filter out header row (row 0) if it was headers
        data_rows = []
        for r_idx, row in enumerate(grid):
            is_header_row = any(
                c.is_header for c in source_elem.cells if c.row_index == r_idx
            ) or r_idx == 0

            if any(cell.strip() for cell in row):
                if not is_header_row or r_idx > 0:
                    data_rows.append(row)

        return data_rows or grid[1:] if len(grid) > 1 else grid
