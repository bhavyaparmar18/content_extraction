"""SOP records SQLite data store for persistence, versioning, and smart cleanup."""

import sqlite3
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
from loguru import logger

from app.config.settings import Settings
from app.db import RecordInUseError, ensure_schema, transaction
from app.db.paths import data_root, row_from_stored, to_stored

PATH_COLUMNS = ("output_path", "units_path", "migrated_path")
_JOBS_USING = "SELECT job_id FROM migration_jobs WHERE sop_record_id = ? ORDER BY created_at"


class SopStore:
    """Manages persistence of SOP metadata, version history, and review states."""

    def __init__(self, db_path: Path, settings: Settings):
        self.db_path = Path(db_path)
        self.settings = settings
        self._root = data_root(settings)
        ensure_schema(self.db_path)

    def get_next_version(self, document_uid: str) -> int:
        """Preview the next gpdat_version for a document_uid (``upsert_record`` allocates it atomically)."""
        with transaction(self.db_path) as conn:
            return self._next_version(conn, document_uid)

    @staticmethod
    def _next_version(conn: sqlite3.Connection, document_uid: str) -> int:
        row = conn.execute(
            "SELECT MAX(gpdat_version) AS max_ver FROM sop_records WHERE document_uid = ?",
            (document_uid,),
        ).fetchone()
        if row and row["max_ver"] is not None:
            return row["max_ver"] + 1
        return 1

    def upsert_record(
        self,
        job_id: str,
        document_uid: str,
        document_number: Optional[str] = None,
        document_name: Optional[str] = None,
        document_title: Optional[str] = None,
        document_version: Optional[str] = None,
        document_type: Optional[str] = None,
        file_type: Optional[str] = None,
        language: str = "en",
        page_count: int = 0,
        source_filename: Optional[str] = None,
        output_path: Optional[str] = None,
        status: Optional[str] = None,
        units_path: Optional[str] = None,
    ) -> dict[str, Any]:
        """Insert the next version of a document."""
        now = datetime.utcnow().isoformat() + "Z"
        record_status = status or "in_review"

        with transaction(self.db_path, immediate=True) as conn:
            next_ver = self._next_version(conn, document_uid)
            cursor = conn.execute(
                """
                INSERT INTO sop_records (
                    job_id, document_uid, document_number, document_name,
                    document_title, document_version, document_type, file_type,
                    language, page_count, gpdat_version, status,
                    source_filename, output_path, units_path, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    document_uid,
                    document_number,
                    document_name,
                    document_title,
                    document_version,
                    document_type,
                    file_type,
                    language,
                    page_count,
                    next_ver,
                    record_status,
                    source_filename,
                    to_stored(output_path, self._root),
                    to_stored(units_path, self._root),
                    now,
                    now,
                ),
            )
            record_id = cursor.lastrowid
        return self.get_record_by_id(record_id)

    def get_records(
        self,
        status: Optional[str] = None,
        document_uid: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List SOP records ordered by newest first."""
        query = "SELECT * FROM sop_records WHERE 1=1"
        params: list[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if document_uid:
            query += " AND document_uid = ?"
            params.append(document_uid)

        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with transaction(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_record_by_id(self, record_id: int) -> Optional[dict[str, Any]]:
        with transaction(self.db_path) as conn:
            row = conn.execute("SELECT * FROM sop_records WHERE id = ?", (record_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def get_record_by_uid(self, document_uid: str) -> Optional[dict[str, Any]]:
        with transaction(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM sop_records WHERE document_uid = ? ORDER BY gpdat_version DESC LIMIT 1",
                (document_uid,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def update_status(self, record_id: int, new_status: str) -> Optional[dict[str, Any]]:
        now = datetime.utcnow().isoformat() + "Z"
        with transaction(self.db_path) as conn:
            conn.execute(
                "UPDATE sop_records SET status = ?, updated_at = ? WHERE id = ?",
                (new_status, now, record_id),
            )
        return self.get_record_by_id(record_id)

    def mark_migrated(self, record_id: int, job_id: str, path: str) -> Optional[dict[str, Any]]:
        """This SOP version was exported by a v2 migration job: the final Word file it produced."""
        now = datetime.utcnow().isoformat() + "Z"
        with transaction(self.db_path) as conn:
            conn.execute(
                "UPDATE sop_records SET migrated_path = ?, migrated_job_id = ?, migrated_at = ?, updated_at = ? WHERE id = ?",
                (to_stored(path, self._root), job_id, now, now, record_id),
            )
        return self.get_record_by_id(record_id)

    def delete_record(self, record_id: int) -> bool:
        """Delete an SOP record. If no sibling versions remain, perform smart cleanup.

        Raises ``RecordInUseError`` (and touches no file) if a migration job uses this version.
        """
        record = self.get_record_by_id(record_id)
        if not record:
            return False

        doc_uid = record["document_Uid"]

        with transaction(self.db_path, immediate=True) as conn:
            using = [r["job_id"] for r in conn.execute(_JOBS_USING, (record_id,))]
            if using:
                raise RecordInUseError("SOP", f"{doc_uid} v{record['gpdat_version']}", using)
            conn.execute("DELETE FROM sop_records WHERE id = ?", (record_id,))
            remaining = conn.execute(
                "SELECT COUNT(*) AS cnt FROM sop_records WHERE document_uid = ?", (doc_uid,)
            ).fetchone()["cnt"]

        if remaining == 0:
            self._smart_cleanup(doc_uid)

        return True

    def _smart_cleanup(self, document_id: str):
        """Best-effort file cleanup for deleted document with no sibling versions."""
        logger.info(f"Performing smart cleanup for document {document_id}")
        try:
            # Delete upload files
            for ext in self.settings.allowed_extensions:
                upload_file = self.settings.upload_dir / f"{document_id}{ext}"
                if upload_file.exists():
                    upload_file.unlink(missing_ok=True)

            # Delete v2 json
            v2_json = self.settings.output_dir / f"{document_id}_v2.json"
            if v2_json.exists():
                v2_json.unlink(missing_ok=True)

            # Delete legacy json
            legacy_json = self.settings.output_dir / f"{document_id}.json"
            if legacy_json.exists():
                legacy_json.unlink(missing_ok=True)

            # Delete extracted images
            img_dir = self.settings.extracted_images_dir / document_id
            if img_dir.exists() and img_dir.is_dir():
                shutil.rmtree(img_dir, ignore_errors=True)

            # Delete extracted icons
            icon_dir = self.settings.extracted_icons_dir / document_id
            if icon_dir.exists() and icon_dir.is_dir():
                shutil.rmtree(icon_dir, ignore_errors=True)

        except Exception as e:
            logger.warning(f"Error during smart cleanup of {document_id}: {e}")

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Format row with casing compatible with both spec and camelCase/snake_case."""
        d = row_from_stored(dict(row), PATH_COLUMNS, self._root)
        # normalize document_uid to document_Uid for frontend compatibility
        d["document_Uid"] = d.pop("document_uid")
        return d
