import logging
import asyncio
import uuid
from app.config.settings import Settings
from app.services.parser.pdf_parser import PDFParser
from app.services.extraction.tables import TableExtractor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = Settings()

logger.info("Parsing PDF...")
parser = PDFParser(settings, logger)
doc = parser.parse('data/uploads/590a0154-eb40-4164-8a9d-d807e6cbbff0.pdf')

doc_page = doc.pages[0] # Page 1
page_media = [
    el for el in doc_page.elements
    if el.element_type.name in ('IMAGE', 'ICON')
    and el.bbox is not None
]

print(f"Found {len(page_media)} media elements on page 1")
for m in page_media:
    is_vec = "VectorGraphic" in getattr(m, 'content', '')
    print(f"Media {m.content}: bbox={m.bbox}, is_vector={is_vec}")

import pdfplumber
with pdfplumber.open('data/uploads/590a0154-eb40-4164-8a9d-d807e6cbbff0.pdf') as pdf:
    p = pdf.pages[0]
    tables = p.find_tables()
    for i, t in enumerate(tables):
        print(f"Table {i}: bbox={t.bbox}")
        
        # Test the overlap logic
        table_bbox_x0, table_bbox_y0, table_bbox_x1, table_bbox_y1 = t.bbox
        margin = 10.0
        for m in page_media:
            mb = m.bbox
            
            overlap_x0 = max(mb.x0, table_bbox_x0)
            overlap_y0 = max(mb.y0, table_bbox_y0)
            overlap_x1 = min(mb.x1, table_bbox_x1)
            overlap_y1 = min(mb.y1, table_bbox_y1)

            overlap_w = max(0, overlap_x1 - overlap_x0)
            overlap_h = max(0, overlap_y1 - overlap_y0)
            overlap_area = overlap_w * overlap_h

            media_area = (mb.x1 - mb.x0) * (mb.y1 - mb.y0)
            table_area = (table_bbox_x1 - table_bbox_x0) * (table_bbox_y1 - table_bbox_y0)

            is_inside = (
                mb.x0 >= table_bbox_x0 - margin and
                mb.y0 >= table_bbox_y0 - margin and
                mb.x1 <= table_bbox_x1 + margin and
                mb.y1 <= table_bbox_y1 + margin
            )
            
            if overlap_area > 0:
                print(f"  Overlap with {m.content}: is_inside={is_inside}, overlap_area={overlap_area}, table_area={table_area}")
                if not is_inside:
                    print(f"    Failed is_inside check! mb.x0={mb.x0} table.x0={table_bbox_x0} mb.y0={mb.y0} table.y0={table_bbox_y0}")
                    print(f"    mb.x1={mb.x1} table.x1={table_bbox_x1} mb.y1={mb.y1} table.y1={table_bbox_y1}")
