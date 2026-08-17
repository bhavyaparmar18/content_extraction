import logging
import asyncio
from app.config.settings import Settings
from app.services.parser.pdf_parser import PDFParser
from app.services.extraction.tables import TableExtractor
from app.services.extraction.icons import IconExtractor
from app.services.extraction.captions import CaptionExtractor
from app.services.hierarchy.ast_builder import ASTBuilder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
settings = Settings()

logger.info("Parsing PDF...")
parser = PDFParser(settings, logger)
doc = parser.parse('data/uploads/590a0154-eb40-4164-8a9d-d807e6cbbff0.pdf')

logger.info("Extracting...")
extractors = [
    TableExtractor(settings),
    IconExtractor(settings),
    CaptionExtractor(settings),
]
for ex in extractors:
    doc = ex.extract(doc)

logger.info("Building AST...")
builder = ASTBuilder(settings, logger)
ast = builder.build(doc)

print("Done. Success!")
