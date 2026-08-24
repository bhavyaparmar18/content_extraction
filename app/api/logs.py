"""Read-only endpoints for querying pipeline logs stored in SQLite."""

import sqlite3
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query

from app.core.logging_config import get_log_db_path

router = APIRouter(tags=["Logs"])

_ALLOWED_LEVELS = {"TRACE", "DEBUG", "INFO", "SUCCESS", "WARNING", "ERROR", "CRITICAL"}


def _read_connection() -> sqlite3.Connection:
    """Open a short-lived read connection to the log DB (WAL keeps it non-blocking)."""
    db_path = get_log_db_path()
    if db_path is None or not db_path.exists():
        raise HTTPException(status_code=404, detail="Log database not initialized yet.")
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn


def _query_logs(where: str, params: list[Any], limit: int) -> list[dict[str, Any]]:
    conn = _read_connection()
    try:
        rows = conn.execute(
            f"SELECT timestamp, level, logger_name, function, line, message,"
            f" job_id, document_id, stage, thread, exception, extra_json"
            f" FROM logs WHERE {where} ORDER BY id ASC LIMIT ?",
            (*params, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


@router.get("/jobs/{job_id}/logs")
async def get_job_logs(
    job_id: str,
    level: Optional[str] = Query(None, description="Filter to this level and above is not applied; exact match."),
    stage: Optional[str] = None,
    limit: int = Query(1000, ge=1, le=10000),
) -> dict[str, Any]:
    """Return log rows for a batch job, oldest first."""
    where = "job_id = ?"
    params: list[Any] = [job_id]
    if level:
        lvl = level.upper()
        if lvl not in _ALLOWED_LEVELS:
            raise HTTPException(status_code=400, detail=f"Invalid level '{level}'.")
        where += " AND level = ?"
        params.append(lvl)
    if stage:
        where += " AND stage = ?"
        params.append(stage)

    logs = _query_logs(where, params, limit)
    return {"job_id": job_id, "count": len(logs), "logs": logs}


@router.get("/documents/{document_id}/logs")
async def get_document_logs(
    document_id: str,
    level: Optional[str] = None,
    stage: Optional[str] = None,
    limit: int = Query(1000, ge=1, le=10000),
) -> dict[str, Any]:
    """Return log rows for a specific document, oldest first."""
    where = "document_id = ?"
    params: list[Any] = [document_id]
    if level:
        lvl = level.upper()
        if lvl not in _ALLOWED_LEVELS:
            raise HTTPException(status_code=400, detail=f"Invalid level '{level}'.")
        where += " AND level = ?"
        params.append(lvl)
    if stage:
        where += " AND stage = ?"
        params.append(stage)

    logs = _query_logs(where, params, limit)
    return {"document_id": document_id, "count": len(logs), "logs": logs}
