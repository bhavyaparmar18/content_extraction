"""SOP Migration System — FastAPI Application Entrypoint.

Run with:  uvicorn app.main:app --reload
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from loguru import logger

from app.config.settings import get_settings
from app.api import health, upload, extract, documents


from app.services.job_manager import JobManager

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
    
    # Initialize JobManager
    job_manager = JobManager(settings, concurrency=3)
    application.state.job_manager = job_manager
    await job_manager.start()
    
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
    version="0.1.0",
    lifespan=lifespan,
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
from app.api import jobs
app.include_router(jobs.router)
