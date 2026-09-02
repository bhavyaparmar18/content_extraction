"""SOP Migration System — FastAPI Application Entrypoint.

Run with:  uvicorn app.main:app --reload
"""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from loguru import logger

from app.config.settings import get_settings
from app.core.exceptions import AppError
from app.core.logging_config import setup_logging, shutdown_logging
from app.core.sop_store import init_sop_store
from app.api import health, upload, extract, documents


from app.services.job_manager import JobManager

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup / shutdown lifecycle hook."""
    settings = get_settings()
    setup_logging(settings)
    logger.info(
        "SOP Migration System starting  |  log_level={level}  |  upload_dir={dir}",
        level=settings.log_level,
        dir=settings.upload_dir,
    )
    settings.ensure_directories()
    init_sop_store(settings)

    # Initialize JobManager.
    #
    # concurrency=1 is deliberate, not a placeholder: every pipeline stage
    # (parsing, table extraction, AST build, chunking, ...) is pure-Python,
    # CPU-bound work dispatched via asyncio.to_thread. Python threads don't
    # get real parallelism for that under the GIL — running N documents
    # "concurrently" just makes the GIL bounce between their threads, so
    # wall-clock throughput for the batch doesn't improve but each individual
    # document's stages take ~2x+ longer (measured: two documents' table
    # extraction alone went from ~6s each run sequentially to ~11s each run
    # concurrently, for the same total wall time). The FastAPI event loop
    # (and therefore /jobs polling) stays fully responsive regardless of this
    # value, since only the worker pool that drains the queue is affected.
    job_manager = JobManager(settings, concurrency=1)
    application.state.job_manager = job_manager
    await job_manager.start()
    
    yield
    
    logger.info("SOP Migration System shutting down.")
    await job_manager.stop()
    shutdown_logging()


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


app.add_middleware(
    CORSMiddleware,
    # The Vite dev server for the SOP Repository frontend. Add the deployed
    # frontend origin here too once it has a real host.
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    """Attach a short request_id to every log line emitted while handling a request.

    Lets an entire API call be traced in the ``logs`` table via ``request_id``,
    mirroring how job_id / document_id trace the background pipeline.
    """
    request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
    with logger.contextualize(request_id=request_id):
        logger.info("→ {method} {path}", method=request.method, path=request.url.path)
        response = await call_next(request)
        logger.info(
            "← {method} {path} [{status}]",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
        )
        response.headers["X-Request-ID"] = request_id
        return response


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    """Map a typed domain error to its status code and log it consistently."""
    if exc.log_level == "ERROR":
        logger.opt(exception=exc).error(
            "{code} on {path}: {msg}",
            code=exc.error_code, path=request.url.path, msg=exc.message,
        )
    else:
        logger.log(
            exc.log_level,
            "{code} on {path}: {msg}{detail}",
            code=exc.error_code, path=request.url.path, msg=exc.message,
            detail=f" | {exc.detail}" if exc.detail else "",
        )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": exc.message,
            "detail": exc.detail,
            "path": str(request.url.path),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log and return 422 for request-body / query validation failures."""
    logger.warning(
        "Validation error on {path}: {errors}",
        path=request.url.path, errors=exc.errors(),
    )
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": "Request validation failed.",
            "detail": exc.errors(),
            "path": str(request.url.path),
        },
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Catch-all for unhandled server errors (e.g. document parsing crashes)."""
    logger.exception(f"Unhandled error processing request {request.url}: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_error",
            "message": "An unexpected internal error occurred.",
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
from app.api import logs
app.include_router(logs.router)
from app.api import sops
app.include_router(sops.router)
