# SOP Migration & Content Extraction System

An intelligent document extraction, AST analysis, and template migration platform for Standard Operating Procedures (SOPs). Supports PDF and DOCX parsing, table & icon extraction, cross-page stitching, hierarchical AST generation, automated QA, and DOCX template migration with an interactive React reviewer UI.

---

## 🚀 Quick Start

### 1. Backend (FastAPI)

```powershell
# Create & activate virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run the backend API server
uvicorn app.main:app --reload --port 8000
```
- Interactive API Docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

### 2. Frontend (React + Vite + TypeScript + Tailwind)

```powershell
cd frontend
npm install
npm run dev
```
- Web Application: `http://localhost:5173`

---

## 📁 Project Structure

```
├── app/
│   ├── main.py                   # FastAPI application entrypoint & lifecycle
│   ├── api/                      # REST API endpoints & WebSocket routes
│   │   ├── health.py             # Health check endpoint
│   │   ├── upload.py             # Single & batch file upload handlers
│   │   ├── extract.py            # Synchronous extraction endpoint
│   │   ├── documents.py          # Document detail, AST, chunk & asset endpoints
│   │   ├── jobs.py               # Batch job polling & WebSocket progress
│   │   ├── migration.py          # DOCX template migration, plan & status
│   │   ├── sops.py               # SOP Repository CRUD & review status
│   │   └── review.py             # Bootstrap context for Review workspace
│   ├── config/
│   │   └── settings.py           # Central Pydantic application settings
│   ├── schemas/                  # Pydantic models & data contracts
│   │   ├── ast_nodes.py          # AST Node definitions (Sections, Tables, Lists)
│   │   ├── document.py           # RawDocument, Elements & Chunk schemas
│   │   ├── jobs.py               # Batch job & document processing status
│   │   ├── layout.py             # Bounding boxes, lines & spans
│   │   ├── migration.py          # Migration format & element representations
│   │   └── output.py             # v2 extraction envelope & asset manifest
│   ├── services/
│   │   ├── chunking/             # Hierarchical & semantic chunking
│   │   ├── export/               # JSON & migration format exporters
│   │   ├── extraction/           # Tables, cross-page stitcher, icons, metadata
│   │   ├── hierarchy/            # AST Builder for document trees
│   │   ├── layout/               # PDF layout analyzer & reading order detector
│   │   ├── llm/                  # LLM chains, prompts & rate limiting
│   │   ├── migration/            # 5-phase DOCX migration & styling engine
│   │   ├── parser/               # PDF & DOCX parsers (PyMuPDF & python-docx)
│   │   └── job_manager.py        # Asynchronous batch job worker pool
│   └── stores/
│       └── sop_store.py          # SQLite database storage for SOP records
├── docs/
│   └── plans/                    # Specification documents and architecture plans
├── frontend/                     # Modern React + Vite frontend application
│   ├── src/
│   │   ├── components/           # UI components (Viewer, Editor, QA, Issues)
│   │   ├── pages/                # Upload, Repository, Review, Migration pages
│   │   ├── lib/                  # API client, WebSocket hooks & utilities
│   │   └── types.ts              # TypeScript interface definitions
├── tests/                        # Comprehensive pytest test suite (66 tests)
├── pytest.ini                    # Pytest configuration
├── requirements.txt              # Python package dependencies
└── README.md
```

---

## 📡 API Endpoints

| Category | Method | Path | Description |
|---|---|---|---|
| **System** | `GET` | `/health` | Server health and operational status |
| **Authentication** | `GET` | `/api/v1/auth/secret-questions` | Retrieve active secret questions for signup |
| **Authentication** | `POST` | `/api/v1/auth/signup` | Register new user account with default role & JWT |
| **Upload** | `POST` | `/documents/upload` | Upload single PDF/DOCX file |
| **Upload** | `POST` | `/documents/upload/batch` | Upload multiple files and enqueue batch job |
| **Jobs** | `GET` | `/jobs/{job_id}` | Poll batch job status and item progress |
| **Jobs** | `WS` | `/jobs/{job_id}/progress` | Real-time WebSocket streaming of job updates |
| **SOP Repository** | `GET` | `/sops` | List SOP records with status/document filtering |
| **SOP Repository** | `GET` | `/sops/{record_id}` | Get single SOP record metadata |
| **SOP Repository** | `PATCH` | `/sops/{record_id}/status` | Update SOP review status (`in_review`, `approved`, `rejected`) |
| **SOP Repository** | `DELETE`| `/sops/{record_id}` | Delete SOP record and underlying disk files |
| **Review** | `GET` | `/review/{record_id}` | Bootstrap configuration and metadata for Review Page |
| **Documents** | `GET` | `/documents/v2/{document_id}/json` | Fetch extracted AST v2 JSON |
| **Documents** | `GET` | `/documents/{document_id}/file` | Serve original PDF or DOCX file for viewer |
| **Documents** | `GET` | `/documents/{document_id}/assets/{filename}` | Serve extracted image and icon assets |
| **Migration** | `POST` | `/documents/migrate` | Execute DOCX template migration pipeline |
| **Migration** | `GET` | `/documents/{document_id}/migration-plan` | Retrieve LLM-generated migration plan |
| **Migration** | `GET` | `/documents/{document_id}/migration-status`| Retrieve migration status & QA validation report |
| **Migration** | `GET` | `/documents/{document_id}/download-docx` | Download final migrated `.docx` document |

---

## 🧪 Testing

Run the test suite using pytest:

```powershell
# Run all unit and integration tests
.\venv\Scripts\pytest

# Run tests with verbose output
.\venv\Scripts\pytest -v
```
