"""Template records SQLite data store for persistence, versioning, and smart cleanup."""

import sqlite3
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, Any
from loguru import logger

from app.config.settings import Settings
from app.db import RecordInUseError, ensure_schema, transaction
from app.db.paths import data_root, row_from_stored, to_stored

PATH_COLUMNS = ("upload_path", "output_path", "model_path", "normalized_path")
_JOBS_USING = (
    "SELECT job_id FROM migration_jobs WHERE template_id = ? AND template_version = ? ORDER BY created_at"
)


class TemplateStore:
    """Manages persistence of Template metadata, version history, extraction state, and global rules."""

    def __init__(self, db_path: Path, settings: Settings):
        self.db_path = Path(db_path)
        self.settings = settings
        self._root = data_root(settings)
        ensure_schema(self.db_path)

    def get_next_version(self, template_uid: str) -> int:
        """Preview the next template_version for a template_uid (``upsert_record`` allocates it atomically)."""
        with transaction(self.db_path) as conn:
            return self._next_version(conn, template_uid)

    @staticmethod
    def _next_version(conn: sqlite3.Connection, template_uid: str) -> int:
        row = conn.execute(
            "SELECT MAX(template_version) AS max_ver FROM template_records WHERE template_uid = ?",
            (template_uid,),
        ).fetchone()
        if row and row["max_ver"] is not None:
            return row["max_ver"] + 1
        return 1

    def upsert_record(
        self,
        template_uid: str,
        template_name: str,
        file_type: str = "docx",
        file_size_bytes: int = 0,
        source_filename: Optional[str] = None,
        upload_path: Optional[str] = None,
        output_path: Optional[str] = None,
        status: str = "uploaded",
    ) -> dict[str, Any]:
        """Insert a new version record for a template."""
        now = datetime.utcnow().isoformat() + "Z"

        with transaction(self.db_path, immediate=True) as conn:
            next_ver = self._next_version(conn, template_uid)
            cursor = conn.execute(
                """
                INSERT INTO template_records (
                    template_uid, template_name, template_version, file_type,
                    file_size_bytes, source_filename, upload_path, output_path,
                    total_sections, total_elements, total_instructions, total_icons,
                    global_rules_json, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, NULL, ?, ?, ?)
                """,
                (
                    template_uid,
                    template_name,
                    next_ver,
                    file_type,
                    file_size_bytes,
                    source_filename,
                    to_stored(upload_path, self._root),
                    to_stored(output_path, self._root),
                    status,
                    now,
                    now,
                ),
            )
            record_id = cursor.lastrowid
        return self.get_record_by_id(record_id)

    def get_records(
        self,
        status: Optional[str] = None,
        template_uid: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List template records ordered by newest first."""
        query = "SELECT * FROM template_records WHERE 1=1"
        params: list[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if template_uid:
            query += " AND template_uid = ?"
            params.append(template_uid)

        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with transaction(self.db_path) as conn:
            rows = conn.execute(query, params).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def get_record_by_id(self, record_id: int) -> Optional[dict[str, Any]]:
        with transaction(self.db_path) as conn:
            row = conn.execute("SELECT * FROM template_records WHERE id = ?", (record_id,)).fetchone()
        return self._row_to_dict(row) if row else None

    def get_record_by_uid(self, template_uid: str) -> Optional[dict[str, Any]]:
        """Fetch the latest version of a template by UID."""
        with transaction(self.db_path) as conn:
            row = conn.execute(
                "SELECT * FROM template_records WHERE template_uid = ? ORDER BY template_version DESC LIMIT 1",
                (template_uid,),
            ).fetchone()
        return self._row_to_dict(row) if row else None

    def get_all_ready_templates(self) -> list[dict[str, Any]]:
        """All templates with status='ready' — for migration dropdown."""
        with transaction(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM template_records WHERE status = 'ready' ORDER BY template_name ASC, template_version DESC"
            ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def update_status(self, record_id: int, new_status: str) -> Optional[dict[str, Any]]:
        now = datetime.utcnow().isoformat() + "Z"
        with transaction(self.db_path) as conn:
            conn.execute(
                "UPDATE template_records SET status = ?, updated_at = ? WHERE id = ?",
                (new_status, now, record_id),
            )
        return self.get_record_by_id(record_id)

    def update_extraction_results(
        self,
        record_id: int,
        output_path: str,
        total_sections: int,
        total_elements: int,
        total_instructions: int,
        total_icons: int,
        total_callouts: int = 0,
        global_rules_json: Optional[str] = None,
        status: str = "ready",
    ) -> Optional[dict[str, Any]]:
        """Update extraction results post-pipeline."""
        now = datetime.utcnow().isoformat() + "Z"
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                UPDATE template_records
                SET output_path = ?,
                    total_sections = ?,
                    total_elements = ?,
                    total_instructions = ?,
                    total_icons = ?,
                    total_callouts = ?,
                    global_rules_json = ?,
                    status = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    to_stored(output_path, self._root),
                    total_sections,
                    total_elements,
                    total_instructions,
                    total_icons,
                    total_callouts,
                    global_rules_json,
                    status,
                    now,
                    record_id,
                ),
            )
        return self.get_record_by_id(record_id)

    def update_template_model(
        self,
        record_id: int,
        model_path: Optional[str],
        normalized_path: Optional[str],
        readiness_status: Optional[str],
    ) -> Optional[dict[str, Any]]:
        """Record the v2 TemplateModel files and readiness status of a template version."""
        now = datetime.utcnow().isoformat() + "Z"
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                UPDATE template_records
                SET model_path = ?, normalized_path = ?, readiness_status = ?, updated_at = ?
                WHERE id = ?
                """,
                (to_stored(model_path, self._root), to_stored(normalized_path, self._root), readiness_status, now, record_id),
            )
        return self.get_record_by_id(record_id)

    def delete_record(self, record_id: int) -> bool:
        """Delete a template record. If no sibling versions remain, perform smart cleanup.

        Raises ``RecordInUseError`` (and touches no file) if a migration job uses this version.
        """
        record = self.get_record_by_id(record_id)
        if not record:
            return False

        template_uid = record["template_uid"]
        upload_path = record.get("upload_path")
        output_path = record.get("output_path")
        model_path = record.get("model_path")
        normalized_path = record.get("normalized_path")

        with transaction(self.db_path, immediate=True) as conn:
            using = [r["job_id"] for r in conn.execute(_JOBS_USING, (template_uid, record["template_version"]))]
            if using:
                raise RecordInUseError("Template", f"{template_uid} v{record['template_version']}", using)
            conn.execute("DELETE FROM template_records WHERE id = ?", (record_id,))
            remaining = conn.execute(
                "SELECT COUNT(*) AS cnt FROM template_records WHERE template_uid = ?",
                (template_uid,),
            ).fetchone()["cnt"]

        # Delete specific version files
        if upload_path:
            Path(upload_path).unlink(missing_ok=True)
        if output_path:
            p = Path(output_path)
            p.unlink(missing_ok=True)
            p.with_name(f"{p.stem}_migration.json").unlink(missing_ok=True)
        if model_path:
            p = Path(model_path)
            p.unlink(missing_ok=True)
            p.with_name(p.name.replace("_model.json", "_readiness.json")).unlink(missing_ok=True)
        if normalized_path:
            Path(normalized_path).unlink(missing_ok=True)

        # If no siblings left, clean image/icon directories and any leftover files
        if remaining == 0:
            self._smart_cleanup(template_uid)

        return True

    def _smart_cleanup(self, template_uid: str):
        """Best-effort file cleanup for deleted template with no remaining versions."""
        logger.info(f"Performing smart cleanup for template {template_uid}")
        try:
            # Delete any remaining files matching prefix
            for upload_file in self.settings.template_upload_dir.glob(f"{template_uid}*"):
                upload_file.unlink(missing_ok=True)

            for output_file in self.settings.template_output_dir.glob(f"{template_uid}*"):
                output_file.unlink(missing_ok=True)

            # Delete extracted images
            img_dir = self.settings.template_extracted_images_dir / template_uid
            if img_dir.exists() and img_dir.is_dir():
                shutil.rmtree(img_dir, ignore_errors=True)

            # Delete extracted icons
            icon_dir = self.settings.template_extracted_icons_dir / template_uid
            if icon_dir.exists() and icon_dir.is_dir():
                shutil.rmtree(icon_dir, ignore_errors=True)

        except Exception as e:
            logger.warning(f"Error during smart cleanup of template {template_uid}: {e}")

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        """Convert sqlite3.Row to a dict with absolute file paths."""
        return row_from_stored(dict(row), PATH_COLUMNS, self._root)
