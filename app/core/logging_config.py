"""Central logging configuration for the SOP Migration System.

A single `setup_logging(settings)` call wires loguru to four destinations:

  * stderr        — human-readable console output
  * app.log       — every record at ``log_level`` (rotating)
  * error.log     — WARNING and above only (rotating)
  * SQLite ``logs`` table — structured, queryable rows

Pipeline traceability comes from ``logger.contextualize(job_id=..., document_id=...,
stage=...)``: those fields are carried into worker threads (``asyncio.to_thread``
copies the contextvars) and stored as dedicated columns for one-query tracing.

An ``InterceptHandler`` also redirects the standard ``logging`` module (and therefore
uvicorn's own logs and any third-party library) into the same sinks.
"""

from __future__ import annotations

import inspect
import json
import logging
import sqlite3
import sys
import traceback
from pathlib import Path
from typing import Any, Optional

from loguru import logger

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp    TEXT    NOT NULL,
    level        TEXT    NOT NULL,
    logger_name  TEXT,
    function     TEXT,
    line         INTEGER,
    message      TEXT    NOT NULL,
    job_id       TEXT,
    document_id  TEXT,
    stage        TEXT,
    request_id   TEXT,
    thread       TEXT,
    exception    TEXT,
    extra_json   TEXT
);
CREATE INDEX IF NOT EXISTS idx_logs_job      ON logs(job_id);
CREATE INDEX IF NOT EXISTS idx_logs_document ON logs(document_id);
CREATE INDEX IF NOT EXISTS idx_logs_level    ON logs(level);
CREATE INDEX IF NOT EXISTS idx_logs_time     ON logs(timestamp);
"""

_RESERVED_EXTRA = {"job_id", "document_id", "stage", "request_id"}

# Module-level state for the SQLite sink. The connection is created lazily inside
# loguru's single enqueue thread, so it is only ever touched by one thread.
_db_path: Optional[Path] = None
_conn: Optional[sqlite3.Connection] = None


def _get_connection() -> sqlite3.Connection:
    """Open (once) and return the SQLite connection used by the log sink."""
    global _conn
    if _conn is None:
        if _db_path is None:
            raise RuntimeError("Logging DB path not configured; call setup_logging first.")
        _db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(_db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA busy_timeout=5000;")
        conn.executescript(_SCHEMA_SQL)
        _migrate_schema(conn)
        conn.commit()
        _conn = conn
    return _conn


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Add columns introduced after a DB was first created (idempotent).

    Runs after the base schema so the request_id index is only created once the
    column is guaranteed to exist (handles DBs created before this column).
    """
    existing = {row[1] for row in conn.execute("PRAGMA table_info(logs)").fetchall()}
    if "request_id" not in existing:
        conn.execute("ALTER TABLE logs ADD COLUMN request_id TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_logs_request ON logs(request_id)")


def _sqlite_sink(message: Any) -> None:
    """loguru sink: persist one structured record into the ``logs`` table."""
    record = message.record
    extra = dict(record["extra"])

    exc_text: Optional[str] = None
    if record["exception"] is not None:
        exc = record["exception"]
        exc_text = "".join(traceback.format_exception(exc.type, exc.value, exc.traceback))

    other_extra = {k: v for k, v in extra.items() if k not in _RESERVED_EXTRA}

    try:
        conn = _get_connection()
        conn.execute(
            "INSERT INTO logs (timestamp, level, logger_name, function, line, message,"
            " job_id, document_id, stage, request_id, thread, exception, extra_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record["time"].isoformat(),
                record["level"].name,
                record["name"],
                record["function"],
                record["line"],
                record["message"],
                extra.get("job_id"),
                extra.get("document_id"),
                extra.get("stage"),
                extra.get("request_id"),
                record["thread"].name,
                exc_text,
                json.dumps(other_extra, default=str) if other_extra else None,
            ),
        )
        conn.commit()
    except Exception:  # noqa: BLE001 - a logging sink must never crash the app
        # Fall back to stderr so we at least see that persistence failed.
        print("SQLite log sink failed:\n" + traceback.format_exc(), file=sys.stderr)


class InterceptHandler(logging.Handler):
    """Route stdlib ``logging`` records (uvicorn, libraries) into loguru."""

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D102
        try:
            level = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        frame, depth = inspect.currentframe(), 0
        while frame and (depth == 0 or frame.f_code.co_filename == logging.__file__):
            frame = frame.f_back
            depth += 1

        logger.opt(depth=depth, exception=record.exc_info).log(
            level, record.getMessage()
        )


def _cleanup_old_rows(retention_days: int) -> None:
    """Delete log rows older than ``retention_days`` to bound DB growth."""
    try:
        conn = _get_connection()
        conn.execute(
            "DELETE FROM logs WHERE timestamp < datetime('now', ?)",
            (f"-{retention_days} days",),
        )
        conn.commit()
    except Exception:  # noqa: BLE001
        print("SQLite log cleanup failed:\n" + traceback.format_exc(), file=sys.stderr)


def setup_logging(settings: Any) -> None:
    """Configure loguru sinks and stdlib interception. Call once at startup."""
    global _db_path
    _db_path = Path(settings.log_db_path)

    logger.remove()

    console_format = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "{extra} | <level>{message}</level>"
    )
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=console_format,
        backtrace=True,
        diagnose=False,
        enqueue=True,
    )

    # app.log — everything at the configured level.
    logger.add(
        str(settings.log_file_path),
        level=settings.log_level,
        rotation="10 MB",
        retention="14 days",
        compression="zip",
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )

    # error.log — only problems, kept longer.
    logger.add(
        str(settings.error_file_path),
        level="WARNING",
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        enqueue=True,
        backtrace=True,
        diagnose=False,
    )

    # Structured SQLite sink.
    logger.add(_sqlite_sink, level=settings.log_level, enqueue=True)

    # Redirect stdlib logging (uvicorn, third-party libs) into loguru.
    logging.basicConfig(handlers=[InterceptHandler()], level=0, force=True)
    for name in ("uvicorn", "uvicorn.error", "fastapi"):
        std_logger = logging.getLogger(name)
        std_logger.handlers = [InterceptHandler()]
        std_logger.propagate = False

    # uvicorn.access duplicates our request middleware (→/←) log, which is richer
    # (carries request_id). Silence the access logger to avoid double HTTP logging.
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers = []
    access_logger.propagate = False
    access_logger.disabled = True

    _cleanup_old_rows(retention_days=14)
    logger.info("Logging initialized | level={level} | db={db}", level=settings.log_level, db=str(_db_path))


def get_log_db_path() -> Optional[Path]:
    """Return the configured SQLite log DB path (for read-only query endpoints)."""
    return _db_path


def shutdown_logging() -> None:
    """Flush and close all sinks on application shutdown."""
    logger.remove()
    global _conn
    if _conn is not None:
        try:
            _conn.close()
        finally:
            _conn = None
