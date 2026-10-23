"""GWP guide records: one row per uploaded guide version, with its status and artifact paths.

Same SQLite pattern as ``TemplateStore``. The rules themselves live in the
JSON file at ``rules_path``, which stays the source of truth after review.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from app.config.settings import Settings
from app.db import RecordInUseError, ensure_schema, transaction
from app.db.paths import data_root, row_from_stored, to_stored

# Must match the CHECK constraint in app/db/migrations/0001_initial.sql.
GUIDE_STATUSES = ("uploaded", "parsed", "extracting", "in_review", "approved", "failed")

PATH_COLUMNS = ("upload_path", "units_path", "rules_path", "report_path")

# Columns update_fields may change.
_UPDATABLE = frozenset({
    "guide_name", "units_path", "rules_path", "report_path", "status", "total_units",
    "total_rules", "approved_rules", "candidate_rules", "prompt_version", "model", "error",
})


class GwpStore:
    def __init__(self, db_path: Path, settings: Settings):
        self.db_path = Path(db_path)
        self.settings = settings
        self._root = data_root(settings)
        ensure_schema(self.db_path)

    @staticmethod
    def _now() -> str:
        return datetime.utcnow().isoformat() + "Z"

    def _row(self, row) -> Optional[dict[str, Any]]:
        return row_from_stored(dict(row), PATH_COLUMNS, self._root) if row else None

    def get_next_version(self, guide_id: str) -> int:
        """Preview the next version (``create_record`` allocates it atomically)."""
        with transaction(self.db_path) as conn:
            return self._next_version(conn, guide_id)

    @staticmethod
    def _next_version(conn, guide_id: str) -> int:
        row = conn.execute(
            "SELECT MAX(version) AS max_ver FROM gwp_guides WHERE guide_id = ?", (guide_id,)
        ).fetchone()
        return (row["max_ver"] or 0) + 1

    def create_record(
        self,
        guide_id: str,
        guide_name: str,
        file_type: str,
        file_size_bytes: int = 0,
        source_filename: Optional[str] = None,
        upload_path: Optional[str] = None,
    ) -> dict[str, Any]:
        """Insert the next version of a guide."""
        now = self._now()
        with transaction(self.db_path, immediate=True) as conn:
            version = self._next_version(conn, guide_id)
            cursor = conn.execute(
                """
                INSERT INTO gwp_guides (
                    guide_id, guide_name, version, file_type, file_size_bytes,
                    source_filename, upload_path, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'uploaded', ?, ?)
                """,
                (guide_id, guide_name, version, file_type, file_size_bytes, source_filename,
                 to_stored(upload_path, self._root), now, now),
            )
            record_id = cursor.lastrowid
        return self.get_record_by_id(record_id)

    def get_record_by_id(self, record_id: int) -> Optional[dict[str, Any]]:
        with transaction(self.db_path) as conn:
            return self._row(conn.execute("SELECT * FROM gwp_guides WHERE id = ?", (record_id,)).fetchone())

    def get_latest(self, guide_id: str) -> Optional[dict[str, Any]]:
        with transaction(self.db_path) as conn:
            return self._row(conn.execute(
                "SELECT * FROM gwp_guides WHERE guide_id = ? ORDER BY version DESC LIMIT 1", (guide_id,)
            ).fetchone())

    def get_records(self, guide_id: Optional[str] = None, status: Optional[str] = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM gwp_guides WHERE 1=1"
        params: list[Any] = []
        if guide_id:
            query += " AND guide_id = ?"
            params.append(guide_id)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY id DESC"
        with transaction(self.db_path) as conn:
            return [self._row(row) for row in conn.execute(query, params).fetchall()]

    def get_active(self) -> Optional[dict[str, Any]]:
        """The most recently updated approved guide version (a migration still has to name it)."""
        with transaction(self.db_path) as conn:
            return self._row(conn.execute(
                "SELECT * FROM gwp_guides WHERE status = 'approved' ORDER BY updated_at DESC, id DESC LIMIT 1"
            ).fetchone())

    def update_fields(self, record_id: int, **fields: Any) -> Optional[dict[str, Any]]:
        unknown = set(fields) - _UPDATABLE
        if unknown:
            raise ValueError(f"cannot update gwp_guides columns: {sorted(unknown)}")
        if "status" in fields and fields["status"] not in GUIDE_STATUSES:
            raise ValueError(f"invalid guide status {fields['status']!r}")
        if fields:
            fields = {k: (to_stored(v, self._root) if k in PATH_COLUMNS else v) for k, v in fields.items()}
            assignments = ", ".join(f"{name} = ?" for name in fields)
            with transaction(self.db_path) as conn:
                conn.execute(
                    f"UPDATE gwp_guides SET {assignments}, updated_at = ? WHERE id = ?",
                    (*fields.values(), self._now(), record_id),
                )
        return self.get_record_by_id(record_id)

    def delete_record(self, record_id: int) -> bool:
        """Delete one guide version and its upload, units, rules and report files.

        Raises ``RecordInUseError`` (and touches no file) if a migration job uses this version.
        """
        record = self.get_record_by_id(record_id)
        if not record:
            return False
        with transaction(self.db_path, immediate=True) as conn:
            using = [r["job_id"] for r in conn.execute(
                "SELECT job_id FROM migration_jobs WHERE gwp_id = ? AND gwp_version = ? ORDER BY created_at",
                (record["guide_id"], record["version"]),
            )]
            if using:
                raise RecordInUseError("GWP guide", f"{record['guide_id']} v{record['version']}", using)
            conn.execute("DELETE FROM gwp_guides WHERE id = ?", (record_id,))
        for key in PATH_COLUMNS:
            if record.get(key):
                Path(record[key]).unlink(missing_ok=True)
        return True
