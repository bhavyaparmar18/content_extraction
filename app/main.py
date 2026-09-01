"""SOP Migration System — FastAPI Application Entrypoint.

Run with:  uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.config.settings import get_settings
from app.api import health, upload, extract, documents, jobs, migration, sops, review
from app.services.job_manager import JobManager
from app.stores.sop_store import SopStore


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup / shutdown lifecycle hook."""
    settings = get_settings()
    logger.info(
        "SOP Migration System starting  |  log_level={level}  |  upload_dir={dir}",
        level=settings.log_level,
        dir=settings.upload_dir,
    )
    settings.ensure_directories()
    
    # Initialize SopStore
    sop_db_path = settings.project_root / "data" / "sop_records.db"
    sop_store = SopStore(sop_db_path, settings)
    application.state.sop_store = sop_store

    # Initialize JobManager
    job_manager = JobManager(settings, concurrency=1, sop_store=sop_store)
    application.state.job_manager = job_manager
    await job_manager.start()

    # Initialize ChainFactory
    from app.services.llm.chain_factory import ChainFactory
    chain_factory = ChainFactory(settings)
    application.state.chain_factory = chain_factory

    yield

    logger.info("SOP Migration System shutting down.")
    await job_manager.stop()


app = FastAPI(
    title="SOP Migration System",
    description=(
        "Extract document structure, text, tables, images, icons, and metadata "
        "from PDF / DOCX SOPs. Performs hybrid chunking and outputs structured "
        "JSON for migration into new templates."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS Middleware ─────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled server errors (e.g. document parsing crashes)."""
    logger.exception(f"Unhandled error processing request {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal Server Error",
            "message": str(exc),
            "path": str(request.url.path),
        },
    )


# ── Register routers ────────────────────────────────────────────────────
app.include_router(health.router)
app.include_router(upload.router)
app.include_router(extract.router)
app.include_router(documents.router)
app.include_router(jobs.router)
app.include_router(migration.router)
app.include_router(sops.router)
app.include_router(review.router)
