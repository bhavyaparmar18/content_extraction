# SOP Migration System

Production-ready SOP extraction and migration backend.

## Quick Start

```bash
# 1. Create virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the development server
uvicorn app.main:app --reload

# 4. Open interactive API docs
# http://127.0.0.1:8000/docs
```

## Project Structure

```
project/
├── app/
│   ├── main.py                   # FastAPI entrypoint
│   ├── api/                      # Route handlers
│   ├── config/                   # Settings (Pydantic)
│   ├── models/                   # DB / in-memory models
│   ├── schemas/                  # Pydantic data contracts
│   ├── services/
│   │   ├── parser/               # BaseParser → PDF / DOCX / OCR
│   │   ├── extraction/           # BaseExtractor → Headings, Tables, …
│   │   ├── hierarchy/            # Tree builder & classifier
│   │   ├── chunking/             # BaseChunker → Hierarchical / Semantic
│   │   ├── export/               # BaseExporter → JSON
│   │   └── migration/            # Future template mapping
│   ├── utils/
│   └── tests/
├── data/                         # Runtime data (auto-created)
├── requirements.txt
└── README.md
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/documents/upload` | Upload a PDF or DOCX |
| `POST` | `/documents/extract` | Trigger extraction pipeline |
| `GET`  | `/health` | Service health check |
