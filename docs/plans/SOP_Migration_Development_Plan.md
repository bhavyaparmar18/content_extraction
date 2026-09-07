# SOP Migration System -- Development Plan

## Overview

Build a production-ready SOP extraction and migration backend using
**FastAPI** and Python libraries only (no cloud services). The system
extracts document structure, text, tables, images, icons, and metadata,
performs hybrid chunking (hierarchical + semantic), and outputs
structured JSON for migration into new templates.

------------------------------------------------------------------------

# 0. Development Standards

> **All code in this project MUST follow a class-based architecture.**
> Plain functions or script-style modules are not acceptable for service,
> parser, extractor, or chunking logic.

## Class Design Principles

| Principle | Expectation |
|---|---|
| **Abstract Base Classes** | Every family of components (parsers, extractors, chunkers, exporters) must define an ABC with a clear public interface. |
| **Concrete Implementations** | Each format- or algorithm-specific variant is a subclass that overrides the abstract methods. |
| **Single Responsibility** | One class = one well-defined responsibility. |
| **Constructor Injection** | Dependencies (config, logger, NLP model, …) are injected through `__init__`, never imported as globals inside methods. |
| **Pydantic Models** | All data contracts (input/output schemas) are defined as `pydantic.BaseModel` subclasses — no raw `dict` passing between layers. |
| **No Module-Level Side Effects** | Files must not execute code at import time; all logic lives inside class methods. |

## Illustrative Pattern

```python
# services/parser/base_parser.py
from abc import ABC, abstractmethod
from app.schemas.document import RawDocument

class BaseParser(ABC):
    """Abstract contract every parser must fulfill."""

    def __init__(self, config: dict, logger) -> None:
        self.config = config
        self.logger = logger

    @abstractmethod
    def parse(self, file_path: str) -> RawDocument:
        """Parse a document and return a RawDocument schema."""
        ...


# services/parser/pdf_parser.py
import fitz  # PyMuPDF
from app.schemas.document import RawDocument
from .base_parser import BaseParser

class PDFParser(BaseParser):
    """Concrete parser for digital and scanned PDF files."""

    def parse(self, file_path: str) -> RawDocument:
        self.logger.info(f"Parsing PDF: {file_path}")
        doc = fitz.open(file_path)
        # ... extraction logic ...
        return RawDocument(source=file_path, pages=pages)
```

This same pattern applies to **every** layer:
`BaseExtractor → HeadingExtractor / TableExtractor / ImageExtractor …`
`BaseChunker → HierarchicalChunker / SemanticChunker`
`BaseExporter → JSONExporter`

------------------------------------------------------------------------

# 1. System Requirements

## Functional Requirements

-   Upload PDF and DOCX SOPs
-   Support digital and scanned PDFs
-   Extract:
    -   Metadata
    -   Headings
    -   Paragraphs
    -   Numbered procedures
    -   Bullet lists
    -   Tables
    -   Images
    -   Icons
    -   Captions
    -   Headers/Footers
    -   References
-   Preserve document hierarchy
-   Detect semantic sections
-   Generate structured chunks
-   Export JSON
-   Support future template mapping

## Non-Functional Requirements

-   Modular architecture
-   Stateless FastAPI services
-   Async processing where appropriate
-   Structured logging
-   Configuration driven
-   Unit/integration tests
-   Deterministic outputs

------------------------------------------------------------------------

# 2. Technology Stack

  Area               Library
  ------------------ ------------------------
  Backend            FastAPI
  Validation         Pydantic
  PDF Parsing        PyMuPDF
  DOCX               python-docx
  Tables             Camelot + pdfplumber
  OCR                pytesseract (optional)
  NLP                spaCy
  Embeddings         sentence-transformers
  Similarity         scikit-learn
  Image Processing   Pillow, imagehash
  Tree Structure     anytree (optional)
  Testing            pytest
  Logging            loguru

------------------------------------------------------------------------

# 3. Recommended Folder Structure

``` text
project/
│
├── app/
│   ├── main.py
│   ├── api/
│   │   ├── upload.py
│   │   ├── extract.py
│   │   └── health.py
│   ├── config/
│   ├── models/
│   ├── schemas/
│   ├── services/
│   │   ├── parser/
│   │   │   ├── pdf_parser.py
│   │   │   ├── docx_parser.py
│   │   │   └── ocr.py
│   │   ├── extraction/
│   │   │   ├── headings.py
│   │   │   ├── paragraphs.py
│   │   │   ├── tables.py
│   │   │   ├── images.py
│   │   │   ├── icons.py
│   │   │   └── captions.py
│   │   ├── hierarchy/
│   │   │   ├── tree_builder.py
│   │   │   └── classifier.py
│   │   ├── chunking/
│   │   │   ├── hierarchical.py
│   │   │   ├── semantic.py
│   │   │   ├── validator.py
│   │   │   └── metadata.py
│   │   ├── export/
│   │   │   └── json_export.py
│   │   └── migration/
│   ├── utils/
│   └── tests/
│
├── data/
│   ├── uploads/
│   ├── extracted_images/
│   ├── extracted_icons/
│   ├── temp/
│   └── output/
│
├── models_local/
├── requirements.txt
└── README.md
```

------------------------------------------------------------------------

# 4. End-to-End Extraction Flow

``` text
Client Upload
      │
      ▼
FastAPI
      │
      ▼
File Validation
      │
      ▼
Parser Selection
      │
      ├── PDF
      └── DOCX
      │
      ▼
Element Extraction
      │
      ├── Metadata
      ├── Headings
      ├── Paragraphs
      ├── Lists
      ├── Tables
      ├── Images
      ├── Icons
      ├── Captions
      └── Headers/Footers
      │
      ▼
Hierarchy Builder
      │
      ▼
Hybrid Chunker
      │
      ├── Structure-aware chunking
      └── Semantic refinement
      │
      ▼
Metadata Enrichment
      │
      ▼
Validation
      │
      ▼
JSON Output
```

------------------------------------------------------------------------

# 5. Hybrid Chunking Strategy

## Stage A -- Hierarchical Chunking

Split only at logical document boundaries: - Heading - Subheading -
Procedure - Responsibility - Reference - Appendix

Never split: - Tables - Numbered procedures - Warnings - Notes -
Captions

## Stage B -- Semantic Refinement

Within each section: 1. Generate paragraph embeddings. 2. Compare
adjacent paragraphs. 3. Split only when semantic similarity drops below
a tuned threshold. 4. Keep related procedure steps together.

------------------------------------------------------------------------

# 6. Element Handling

## Text

Preserve formatting and reading order.

## Tables

Extract into structured headers/rows.

## Images

Store file path, caption, page, coordinates.

## Icons

Treat as first-class elements.

Capture: - icon_id - semantic meaning - page - coordinates - associated
paragraph/table cell

Maintain an icon dictionary (e.g., Warning, PPE Required, Mandatory,
Prohibited, Information).

## Figures

Link figures with captions.

## Headers/Footers

Store separately; exclude from chunk content unless required.

------------------------------------------------------------------------

# 7. Chunk Metadata

Each chunk should include: - chunk_id - parent_id - section - heading -
page - sequence - type - contains_table - contains_image -
contains_icon - related_chunks - source_coordinates

------------------------------------------------------------------------

# 8. Output Schema (High Level)

``` json
{
  "document_id": "...",
  "title": "...",
  "chunks": [
    {
      "chunk_id": "...",
      "type": "procedure",
      "heading": "...",
      "content": "...",
      "tables": [],
      "images": [],
      "icons": [],
      "metadata": {}
    }
  ]
}
```

------------------------------------------------------------------------

# 9. FastAPI Endpoints

-   `POST /documents/upload`
-   `POST /documents/extract`
-   `GET /documents/{id}`
-   `GET /documents/{id}/chunks`
-   `GET /documents/{id}/json`
-   `GET /health`

------------------------------------------------------------------------

# 10. Development Roadmap

## Phase 1

-   FastAPI project
-   Upload API
-   Parser abstraction

## Phase 2

-   PDF parser
-   DOCX parser
-   Metadata extraction

## Phase 3

-   Tables
-   Images
-   Icons
-   Captions

## Phase 4

-   Hierarchy builder
-   Element classifier

## Phase 5

-   Hierarchical chunking
-   Semantic chunking
-   Metadata enrichment

## Phase 6

-   Validation
-   JSON exporter
-   API integration

## Phase 7

-   Testing
-   Performance optimization
-   Documentation

------------------------------------------------------------------------

# 11. Success Criteria

-   Logical document hierarchy preserved
-   No procedure split across chunks
-   Tables remain structured
-   Icons retain semantic meaning
-   Images remain associated with captions
-   Deterministic JSON output
-   Ready for downstream template mapping with minimal manual
    intervention
