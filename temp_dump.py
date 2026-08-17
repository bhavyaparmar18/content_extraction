import logging
from app.config.settings import Settings
from app.services.parser.pdf_parser import PDFParser
from app.services.extraction.icons import IconExtractor

settings = Settings()
parser = PDFParser(settings, logging.getLogger())
doc = parser.parse('data/uploads/590a0154-eb40-4164-8a9d-d807e6cbbff0.pdf')
doc = IconExtractor(settings).extract(doc)

for page in doc.pages:
    if page.page_number == 3:
        for el in page.elements:
            if el.element_type.name in ('PARAGRAPH', 'HEADING', 'ICON', 'IMAGE'):
                bbox = getattr(el, 'bbox', None)
                if el.element_type.name == 'ICON':
                    meaning = getattr(el, 'semantic_meaning', 'unknown')
                    print(f'{el.element_type.name} (bbox={bbox}): {meaning}')
                else:
                    text = el.content[:50].replace('\n', ' ')
                    print(f'{el.element_type.name} (bbox={bbox}): {text}...')
