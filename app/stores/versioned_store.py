"""A table of uploaded, versioned records (one row per version), as ``GwpStore`` keeps GWP guides.

Subclasses name the table, its id and status columns, and which translation-job
columns point at it; deleting a version a translation job uses is refused.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config.settings import Settings
from app.db import RecordInUseError, ensure_schema, transaction
from app.db.paths import data_root, row_from_stored, to_stored
from app.services.translation.languages import get_language


class VersionedRecordStore:
    TABLE: str
    ID_COLUMN: str
    LABEL: str                       # for RecordInUseError, e.g. "Glossary"
    STATUSES: tuple[str, ...]        # must match the table's CHECK constraint
    PATH_COLUMNS: tuple[str, ...]
    UPDATABLE: frozenset[str]
    INSERTABLE: frozenset[str]       # columns create_record may set besides id, name, language and version
    JOB_COLUMNS: tuple[str, str]     # translation_jobs columns holding (id, version)

    def __init__(self, db_path: Path, settings: Settings):
        self.db_path = Path(db_path)
        self.settings = settings
        self._root = data_root(settings)
        ensure_schema(self.db_path)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def _row(self, row) -> Optional[dict[str, Any]]:
        return row_from_stored(dict(row), self.PATH_COLUMNS, self._root) if row else None

    def _next_version(self, conn, record_id: str) -> int:
        row = conn.execute(
            f"SELECT MAX(version) AS max_ver FROM {self.TABLE} WHERE {self.ID_COLUMN} = ?", (record_id,)
        ).fetchone()
        return (row["max_ver"] or 0) + 1

    def get_next_version(self, record_id: str) -> int:
        """Preview the next version (``create_record`` allocates it atomically)."""
        with transaction(self.db_path) as conn:
            return self._next_version(conn, record_id)

    def create_record(self, record_id: str, name: str, language: str, created_by: Optional[str] = None,
                      **columns: Any) -> dict[str, Any]:
        """Insert the next version of a record; ``columns`` are further insert-time columns (file details, paths)."""
        unknown = set(columns) - self.INSERTABLE
        if unknown:
            raise ValueError(f"cannot insert {self.TABLE} columns: {sorted(unknown)}")
        language = get_language(language).word_lang
        now = self._now()
        columns = {k: (to_stored(v, self._root) if k in self.PATH_COLUMNS else v) for k, v in columns.items()}
        names = [self.ID_COLUMN, "name", "language", "version", "created_by", "created_at", "updated_at", *columns]
        with transaction(self.db_path, immediate=True) as conn:
            version = self._next_version(conn, record_id)
            cursor = conn.execute(
                f"INSERT INTO {self.TABLE} ({', '.join(names)}) VALUES ({', '.join('?' for _ in names)})",
                (record_id, name, language, version, created_by, now, now, *columns.values()),
            )
            row_id = cursor.lastrowid
        return self.get_record_by_id(row_id)

    def get_record_by_id(self, row_id: int) -> Optional[dict[str, Any]]:
        with transaction(self.db_path) as conn:
            return self._row(conn.execute(f"SELECT * FROM {self.TABLE} WHERE id = ?", (row_id,)).fetchone())

    def get_version(self, record_id: str, version: int) -> Optional[dict[str, Any]]:
        with transaction(self.db_path) as conn:
            return self._row(conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE {self.ID_COLUMN} = ? AND version = ?", (record_id, version)
            ).fetchone())

    def get_latest(self, record_id: str) -> Optional[dict[str, Any]]:
        with transaction(self.db_path) as conn:
            return self._row(conn.execute(
                f"SELECT * FROM {self.TABLE} WHERE {self.ID_COLUMN} = ? ORDER BY version DESC LIMIT 1", (record_id,)
            ).fetchone())

    def get_records(self, record_id: Optional[str] = None, language: Optional[str] = None,
                    status: Optional[str] = None) -> list[dict[str, Any]]:
        query = f"SELECT * FROM {self.TABLE} WHERE 1=1"
        params: list[Any] = []
        for column, value in ((self.ID_COLUMN, record_id), ("language", language), ("status", status)):
            if value:
                query += f" AND {column} = ?"
                params.append(value)
        query += " ORDER BY id DESC"
        with transaction(self.db_path) as conn:
            return [self._row(row) for row in conn.execute(query, params).fetchall()]

    def update_fields(self, row_id: int, **fields: Any) -> Optional[dict[str, Any]]:
        unknown = set(fields) - self.UPDATABLE
        if unknown:
            raise ValueError(f"cannot update {self.TABLE} columns: {sorted(unknown)}")
        if "status" in fields and fields["status"] not in self.STATUSES:
            raise ValueError(f"invalid {self.TABLE} status {fields['status']!r}")
        if fields:
            fields = {k: (to_stored(v, self._root) if k in self.PATH_COLUMNS else v) for k, v in fields.items()}
            assignments = ", ".join(f"{name} = ?" for name in fields)
            with transaction(self.db_path) as conn:
                conn.execute(
                    f"UPDATE {self.TABLE} SET {assignments}, updated_at = ? WHERE id = ?",
                    (*fields.values(), self._now(), row_id),
                )
        return self.get_record_by_id(row_id)

    def delete_record(self, row_id: int) -> bool:
        """Delete one version and its files.

        Raises ``RecordInUseError`` (and touches no file) if a translation job uses this version.
        """
        record = self.get_record_by_id(row_id)
        if not record:
            return False
        id_column, version_column = self.JOB_COLUMNS
        with transaction(self.db_path, immediate=True) as conn:
            using = [r["job_id"] for r in conn.execute(
                f"SELECT job_id FROM translation_jobs WHERE {id_column} = ? AND {version_column} = ? "
                "ORDER BY created_at",
                (record[self.ID_COLUMN], record["version"]),
            )]
            if using:
                raise RecordInUseError(self.LABEL, f"{record[self.ID_COLUMN]} v{record['version']}", using,
                                       job_kind="translation")
            conn.execute(f"DELETE FROM {self.TABLE} WHERE id = ?", (row_id,))
        for key in self.PATH_COLUMNS:
            if record.get(key):
                Path(record[key]).unlink(missing_ok=True)
        return True
