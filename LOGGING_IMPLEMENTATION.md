# Logging Implementation Guide

Simple, traceable logging for the SOP Migration pipeline using **loguru** (already a dependency) with a **SQLite** sink. Every log line is automatically stamped with `job_id`, `document_id`, and `stage` so a full pipeline run can be traced with one query.

## Goals

- One logging setup, configured once at startup — no per-file boilerplate.
- Capture every pipeline stage (parse → extract → AST → chunk → export).
- Thread-safe, non-blocking persistence to SQLite (workers run in threads).
- Keep it minimal: no new dependencies, no external log services.

## Architecture

```
services / API  ──▶  loguru.logger  ──▶  [ console sink   ]  (human-readable)
(self.logger)         │                  [ app.log        ]  (all levels, rotating)
                      │                  [ error.log      ]  (WARNING+ only, rotating)
                      │                  [ sqlite sink     ]  (structured, queryable)
                      │
            logger.contextualize(job_id, document_id, stage)
            → fields flow into worker threads via asyncio.to_thread
```

Two file sinks by design: **`app.log`** captures everything at `log_level`, while **`error.log`** captures only `WARNING`+ so problems are visible without scanning the full log. Both use the same rotation/retention.

- **Single facade:** all existing `self.logger` / global `logger` calls keep working; only the sink config changes.
- **`enqueue=True`** on the file + SQLite sinks routes every record through loguru's one background thread → serialized, non-blocking writes (no `SQLITE_BUSY`).
- **`contextualize()`** stores context in a `contextvar`, which `asyncio.to_thread` copies into worker threads — so logs emitted deep in the parser/extractors carry the run identifiers automatically.

## File structure / changes

| File | Change |
|------|--------|
| `app/core/logging_config.py` | **New.** `setup_logging(settings)` + SQLite sink + schema init. |
| `app/config/settings.py` | Add `log_dir`, `log_file_path`, `error_file_path`, `log_db_path`; register in `ensure_directories()` and `resolve_paths()`. |
| `app/main.py` | Call `setup_logging(settings)` first in `lifespan`; `logger.remove()` on shutdown to flush. |
| `app/services/job_manager.py` | Wrap `_process_document` stages in `logger.contextualize(...)`; change worker-loop `logger.error` → `logger.exception`. |
| `app/services/export/migration_exporter.py` | Switch stdlib `logging` → loguru (or add an `InterceptHandler` in setup to capture stdlib + uvicorn). |

New runtime artifacts (git-ignored): `data/logs/app.log`, `data/logs/error.log`, `data/logs/logs.db`.

## SQLite schema

```sql
CREATE TABLE IF NOT EXISTS logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    TEXT    NOT NULL,   -- ISO8601 UTC
    level        TEXT    NOT NULL,
    logger_name  TEXT,
    function     TEXT,
    line         INTEGER,
    message      TEXT    NOT NULL,
    job_id       TEXT,               -- from contextualize()
    document_id  TEXT,               -- from contextualize()
    stage        TEXT,               -- parse / tables / icons / ast / chunk / export
    thread       TEXT,
    exception    TEXT,               -- full traceback when present
    extra_json   TEXT                -- any other bound fields, as JSON
);
CREATE INDEX IF NOT EXISTS idx_logs_job      ON logs(job_id);
CREATE INDEX IF NOT EXISTS idx_logs_document ON logs(document_id);
CREATE INDEX IF NOT EXISTS idx_logs_level    ON logs(level);
CREATE INDEX IF NOT EXISTS idx_logs_time     ON logs(timestamp);
```

Connection PRAGMAs (set once): `journal_mode=WAL`, `synchronous=NORMAL`, `busy_timeout=5000`.

## Workflow

**Setup (startup)**
1. `lifespan` calls `setup_logging(settings)`.
2. `logger.remove()` drops the default handler; add the sinks:
```python
logger.remove()
logger.add(sys.stderr, level=settings.log_level, backtrace=True, diagnose=False)
logger.add(settings.log_file_path,  level=settings.log_level, rotation="10 MB",
           retention="14 days", enqueue=True)                       # app.log — all levels
logger.add(settings.error_file_path, level="WARNING", rotation="10 MB",
           retention="30 days", enqueue=True)                       # error.log — problems only
logger.add(_sqlite_sink, level=settings.log_level, enqueue=True)    # structured DB
```
3. SQLite sink lazily opens the DB (inside loguru's enqueue thread), applies PRAGMAs, creates the table.

**Per document (in `JobManager._process_document`)**
```python
with logger.contextualize(job_id=job_id, document_id=document_id, stage="parse"):
    raw = await asyncio.to_thread(parser.parse, ...)
    with logger.contextualize(stage="tables"):
        raw = await asyncio.to_thread(table_ext.extract, raw)
    with logger.contextualize(stage="icons"):
        raw = await asyncio.to_thread(icon_ext.extract, raw, document_id=document_id)
    # ... captions, ast, chunk, export
```
Every log from any nested service inherits `job_id` / `document_id` / current `stage`.

**Tracing a run**
```sql
-- Full timeline for one document
SELECT timestamp, level, stage, message
FROM logs WHERE document_id = ? ORDER BY id;

-- Only problems
SELECT * FROM logs WHERE level = 'ERROR' ORDER BY id DESC LIMIT 50;
```

## Feature / function-specific tracking

No extra work needed — loguru records the source of every log, and the schema stores it:

| Column | Meaning | Example filter |
|--------|---------|----------------|
| `logger_name` | Module = **feature/component** | `WHERE logger_name LIKE '%icons%'` |
| `function` | **Function** that logged | `WHERE function = 'extract'` |
| `line` | Line number | debugging |
| `stage` | Pipeline phase (bound via `contextualize`) | `WHERE stage = 'tables'` |

```sql
-- Everything the icon extractor did for one document
SELECT timestamp, function, line, message
FROM logs WHERE document_id = ? AND logger_name LIKE '%icons%' ORDER BY id;
```

For an explicit label that is independent of the module path, bind a custom field
(`logger.bind(feature="table_stitching").info(...)`) — it lands in `extra_json`.

## Retention

- **File:** handled by loguru — `rotation="10 MB"`, `retention="14 days"`.
- **SQLite:** one-line cleanup on startup — `DELETE FROM logs WHERE timestamp < date('now','-14 days')`.

## Optional (not required for MVP)

- Read-only API endpoints: `GET /jobs/{job_id}/logs`, `GET /documents/{document_id}/logs?level=ERROR` (use a separate read connection; WAL keeps reads non-blocking).
- `InterceptHandler` to funnel uvicorn/stdlib logs into the same sinks.
- A `pipeline_runs` summary table (one row per document: status, duration, error) for dashboard-style queries.

## Explicitly out of scope

External aggregators (Datadog/ELK/Loki), OTLP, dead-letter queues, per-log async batching — unnecessary for a local POC. loguru's `serialize=True` leaves a clean upgrade path to JSON export if needed later.
