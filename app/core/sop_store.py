"""Persistent SQLite store for SOP extraction records (review status tracking).

Unlike the transient ``logs`` DB (see ``logging_config.py``, rows expire after
14 days), ``sop_records`` is business data and lives in its own DB file with
no cleanup. One row per extraction run, keyed by ``(document_uid,
gpdat_version)`` so a genuine re-upload creates a new row (history preserved)
while reprocessing the same version upserts metadata in place.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from loguru import logger

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS sop_records (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id           TEXT    NOT NULL,
    document_uid     TEXT    NOT NULL,
    document_number  TEXT,
    document_name    TEXT,
    document_title   TEXT,
    document_version TEXT,
    document_type    TEXT,
    file_type        TEXT,
    language         TEXT    DEFAULT 'en',
    page_count       INTEGER DEFAULT 0,
    gpdat_version    INTEGER DEFAULT 0,
    status           TEXT    NOT NULL DEFAULT 'approved'
                     CHECK(status IN ('in_review','approved','rejected')),
    source_filename  TEXT,
    output_path      TEXT,
    created_at       TEXT    NOT NULL,
    updated_at       TEXT    NOT NULL,
    UNIQUE(document_uid, gpdat_version)
);
CREATE INDEX IF NOT EXISTS idx_sop_uid    ON sop_records(document_uid);
CREATE INDEX IF NOT EXISTS idx_sop_status ON sop_records(status);
CREATE INDEX IF NOT EXISTS idx_sop_job    ON sop_records(job_id);
"""

_db_path: Optional[Path] = None


def init_sop_store(settings: Any) -> None:
    """Configure the DB path and create the schema. Call once at startup."""
    global _db_path
    _db_path = Path(settings.sop_db_path)
    conn = _connect()
    try:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
    logger.info("SOP records store initialized | db={db}", db=str(_db_path))


def get_sop_db_path() -> Optional[Path]:
    """Return the configured SOP records DB path (e.g. for diagnostics)."""
    return _db_path


def _connect() -> sqlite3.Connection:
    """Open a short-lived connection to the SOP records DB."""
    if _db_path is None:
        raise RuntimeError("SOP store not configured; call init_sop_store first.")
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def next_version(document_uid: str) -> int:
    """Return the next ``gpdat_version`` to assign for a document.

    Derived from existing history in ``sop_records`` (highest recorded
    version for this ``document_uid`` + 1, or 1 if no prior record exists).
    This makes versioning self-healing: with no separate counter to go
    stale, deleting a document's rows naturally resets its next version.
    """
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT COALESCE(MAX(gpdat_version), 0) AS max_v FROM sop_records WHERE document_uid = ?",
            (document_uid,),
        ).fetchone()
        return int(row["max_v"]) + 1
    finally:
        conn.close()


def upsert_record(
    *,
    job_id: str,
    document_uid: str,
    document_number: Optional[str],
    document_name: Optional[str],
    document_title: Optional[str],
    document_version: Optional[str],
    document_type: Optional[str],
    file_type: str,
    language: str,
    page_count: int,
    gpdat_version: int,
    source_filename: Optional[str],
    output_path: Optional[str],
) -> int:
    """Insert a new extraction-run row, or update it in place on a reprocess.

    A genuine re-upload has a higher ``gpdat_version`` and always inserts a
    fresh row, preserving history. Reprocessing the *same* version (e.g. a
    dev-server reload replaying the pipeline) updates metadata only —
    ``status`` is deliberately excluded from the conflict update so a
    reviewer's decision is never silently reset.
    """
    now = _now()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO sop_records (
                job_id, document_uid, document_number, document_name, document_title,
                document_version, document_type, file_type, language, page_count,
                gpdat_version, source_filename, output_path, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_uid, gpdat_version) DO UPDATE SET
                job_id=excluded.job_id,
                document_number=excluded.document_number,
                document_name=excluded.document_name,
                document_title=excluded.document_title,
                document_version=excluded.document_version,
                document_type=excluded.document_type,
                file_type=excluded.file_type,
                language=excluded.language,
                page_count=excluded.page_count,
                source_filename=excluded.source_filename,
                output_path=excluded.output_path,
                updated_at=excluded.updated_at
            """,
            (
                job_id, document_uid, document_number, document_name, document_title,
                document_version, document_type, file_type, language, page_count,
                gpdat_version, source_filename, output_path, now, now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT id FROM sop_records WHERE document_uid = ? AND gpdat_version = ?",
            (document_uid, gpdat_version),
        ).fetchone()
        return int(row["id"])
    finally:
        conn.close()


def list_records(
    status: Optional[str] = None,
    document_uid: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return SOP records, newest first, with optional status/document_uid filters."""
    where = []
    params: list[Any] = []
    if status:
        where.append("status = ?")
        params.append(status)
    if document_uid:
        where.append("document_uid = ?")
        params.append(document_uid)
    clause = f"WHERE {' AND '.join(where)}" if where else ""

    conn = _connect()
    try:
        rows = conn.execute(
            f"SELECT * FROM sop_records {clause} ORDER BY id DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_record(record_id: int) -> Optional[dict[str, Any]]:
    """Return one SOP record by its surrogate id, or None if missing."""
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM sop_records WHERE id = ?", (record_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def count_records_for_document(document_uid: str) -> int:
    """Count how many rows (across all gpdat_versions) still reference this document."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM sop_records WHERE document_uid = ?",
            (document_uid,),
        ).fetchone()
        return int(row["n"])
    finally:
        conn.close()


def delete_record(record_id: int) -> Optional[dict[str, Any]]:
    """Delete one SOP record by id. Returns its pre-delete data, or None if missing.

    Callers can inspect the returned row's ``document_uid`` (with
    ``count_records_for_document``) to decide whether it's now safe to also
    remove the underlying files, since the upload/output file paths are not
    versioned and may still be referenced by a sibling row.
    """
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM sop_records WHERE id = ?", (record_id,)).fetchone()
        if row is None:
            return None
        conn.execute("DELETE FROM sop_records WHERE id = ?", (record_id,))
        conn.commit()
        return dict(row)
    finally:
        conn.close()


def update_status(record_id: int, status: str) -> Optional[dict[str, Any]]:
    """Update a record's review status. Returns the updated row, or None if missing."""
    conn = _connect()
    try:
        cur = conn.execute(
            "UPDATE sop_records SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now(), record_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None
        row = conn.execute("SELECT * FROM sop_records WHERE id = ?", (record_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()
