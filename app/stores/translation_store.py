"""Translation job persistence: jobs, versioned artifacts and an audit log.

Same pattern as ``MigrationStore``. Every status change goes through
``set_status``, which also writes an event, so the audit log is complete.
Artifact paths are stored relative to the data folder (``app.db.paths``).
"""

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from app.config.settings import Settings
from app.db import ensure_schema, transaction
from app.db.paths import data_root, from_stored, to_stored
from app.schemas.v2 import ArtifactKind, ArtifactRef, TranslationJob, TranslationStatus

# Columns update_job may change; status goes through set_status, approval through approve.
_UPDATABLE = frozenset({"error", "failed_stage", "cancel_requested"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TranslationStore:
    def __init__(self, db_path: Path, settings: Optional[Settings] = None):
        self.db_path = Path(db_path)
        self.settings = settings
        self._root = data_root(settings)
        ensure_schema(self.db_path)

    # ── Jobs ──────────────────────────────────────────────────────────

    def create_job(self, job: TranslationJob) -> TranslationJob:
        now = _now()
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO translation_jobs (
                    job_id, migration_job_id, language, glossary_id, glossary_version,
                    language_template_id, language_template_version, status, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.job_id, job.migration_job_id, job.language.value, job.glossary_id, job.glossary_version,
                    job.language_template_id, job.language_template_version, job.status.value, job.created_by,
                    now, now,
                ),
            )
            self._add_event(conn, job.job_id, job.created_by, "created", None, job.status.value, None)
        return self.get_job(job.job_id)

    def get_job(self, job_id: str) -> Optional[TranslationJob]:
        with transaction(self.db_path) as conn:
            row = conn.execute("SELECT * FROM translation_jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                return None
            artifacts = conn.execute(
                "SELECT * FROM translation_artifacts WHERE job_id = ? ORDER BY id", (job_id,)
            ).fetchall()
        return TranslationJob(
            job_id=row["job_id"],
            migration_job_id=row["migration_job_id"],
            language=row["language"],
            glossary_id=row["glossary_id"],
            glossary_version=row["glossary_version"],
            language_template_id=row["language_template_id"],
            language_template_version=row["language_template_version"],
            status=TranslationStatus(row["status"]),
            artifacts=[self._artifact(a) for a in artifacts],
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            approved_by=row["approved_by"],
            approved_at=row["approved_at"],
            error=row["error"],
        )

    def get_job_row(self, job_id: str) -> Optional[dict[str, Any]]:
        """Raw row, including the store-only columns (failed_stage, cancel_requested)."""
        with transaction(self.db_path) as conn:
            row = conn.execute("SELECT * FROM translation_jobs WHERE job_id = ?", (job_id,)).fetchone()
            return dict(row) if row else None

    def list_jobs(
        self,
        status: Optional[str] = None,
        migration_job_id: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query = "SELECT * FROM translation_jobs WHERE 1=1"
        params: list[Any] = []
        for column, value in (("status", status), ("migration_job_id", migration_job_id), ("language", language)):
            if value:
                query += f" AND {column} = ?"
                params.append(value)
        query += " ORDER BY created_at DESC, job_id DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        with transaction(self.db_path) as conn:
            return [dict(r) for r in conn.execute(query, params).fetchall()]

    def job_ids_with_status(self, statuses: list[TranslationStatus]) -> list[str]:
        if not statuses:
            return []
        marks = ",".join("?" for _ in statuses)
        with transaction(self.db_path) as conn:
            rows = conn.execute(
                f"SELECT job_id FROM translation_jobs WHERE status IN ({marks}) ORDER BY created_at",
                [s.value for s in statuses],
            ).fetchall()
        return [r["job_id"] for r in rows]

    def update_job(self, job_id: str, **fields: Any) -> None:
        unknown = set(fields) - _UPDATABLE
        if unknown:
            raise ValueError(f"cannot update translation_jobs columns: {sorted(unknown)}")
        if not fields:
            return
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with transaction(self.db_path) as conn:
            conn.execute(
                f"UPDATE translation_jobs SET {assignments}, updated_at = ? WHERE job_id = ?",
                (*fields.values(), _now(), job_id),
            )

    def set_status(
        self,
        job_id: str,
        status: TranslationStatus,
        actor: Optional[str] = None,
        event: str = "status",
        detail: Optional[dict] = None,
        expected: Optional[TranslationStatus] = None,
    ) -> bool:
        """Change the status and log it. With ``expected``, only if the job is still in that status."""
        with transaction(self.db_path, immediate=True) as conn:
            row = conn.execute("SELECT status FROM translation_jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if expected is not None and row["status"] != expected.value:
                return False
            conn.execute(
                "UPDATE translation_jobs SET status = ?, updated_at = ? WHERE job_id = ?",
                (status.value, _now(), job_id),
            )
            self._add_event(conn, job_id, actor, event, row["status"], status.value, detail)
        return True

    def approve(self, job_id: str, actor: str, detail: Optional[dict] = None) -> bool:
        """Mark a job awaiting review as approved by ``actor``; False if it is not awaiting review."""
        now = _now()
        with transaction(self.db_path, immediate=True) as conn:
            row = conn.execute("SELECT status FROM translation_jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if row["status"] != TranslationStatus.REVIEW_PENDING.value:
                return False
            conn.execute(
                "UPDATE translation_jobs SET status = ?, approved_by = ?, approved_at = ?, updated_at = ? "
                "WHERE job_id = ?",
                (TranslationStatus.APPROVED.value, actor, now, now, job_id),
            )
            self._add_event(conn, job_id, actor, "approved", row["status"], TranslationStatus.APPROVED.value, detail)
        return True

    # ── Artifacts ─────────────────────────────────────────────────────

    def next_artifact_version(self, job_id: str, kind: ArtifactKind, scope: Optional[str] = None) -> int:
        with transaction(self.db_path) as conn:
            row = conn.execute(
                "SELECT MAX(version) AS v FROM translation_artifacts WHERE job_id = ? AND kind = ? AND scope = ?",
                (job_id, kind.value, scope or ""),
            ).fetchone()
        return (row["v"] or 0) + 1

    def add_next_artifact(
        self, job_id: str, kind: ArtifactKind, scope: Optional[str], write: Callable[[int], ArtifactRef]
    ) -> ArtifactRef:
        """Allocate the next version, let ``write(version)`` create the file, and index it, all under one write lock.

        Two writers can never pick the same version. If indexing fails, the file just written is removed.
        """
        ref: Optional[ArtifactRef] = None
        try:
            with transaction(self.db_path, immediate=True) as conn:
                row = conn.execute(
                    "SELECT MAX(version) AS v FROM translation_artifacts WHERE job_id = ? AND kind = ? AND scope = ?",
                    (job_id, kind.value, scope or ""),
                ).fetchone()
                ref = write((row["v"] or 0) + 1)
                self._insert_artifact(conn, job_id, ref)
        except BaseException:
            if ref is not None:
                Path(ref.path).unlink(missing_ok=True)
            raise
        return ref

    def _insert_artifact(self, conn: sqlite3.Connection, job_id: str, ref: ArtifactRef) -> None:
        conn.execute(
            """
            INSERT INTO translation_artifacts (job_id, kind, scope, version, path, sha256, created_at, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id, ref.kind.value, ref.scope or "", ref.version, to_stored(ref.path, self._root), ref.sha256,
                (ref.created_at.isoformat() if ref.created_at else _now()), ref.created_by,
            ),
        )
        self._add_event(
            conn, job_id, ref.created_by, "artifact", None, None,
            {"kind": ref.kind.value, "scope": ref.scope, "version": ref.version},
        )

    def _artifact(self, row: sqlite3.Row) -> ArtifactRef:
        return ArtifactRef(
            kind=ArtifactKind(row["kind"]),
            version=row["version"],
            path=from_stored(row["path"], self._root),
            sha256=row["sha256"],
            scope=row["scope"] or None,
            created_at=row["created_at"],
            created_by=row["created_by"],
        )

    # ── Events ────────────────────────────────────────────────────────

    @staticmethod
    def _add_event(conn, job_id, actor, event, from_status, to_status, detail) -> None:
        conn.execute(
            """
            INSERT INTO translation_events (job_id, at, actor, event, from_status, to_status, detail)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, _now(), actor, event, from_status, to_status, json.dumps(detail) if detail is not None else None),
        )

    def add_event(self, job_id: str, event: str, actor: Optional[str] = None, detail: Optional[dict] = None) -> None:
        with transaction(self.db_path) as conn:
            self._add_event(conn, job_id, actor, event, None, None, detail)

    def list_events(self, job_id: str) -> list[dict[str, Any]]:
        with transaction(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM translation_events WHERE job_id = ? ORDER BY id", (job_id,)).fetchall()
        events = []
        for r in rows:
            event = dict(r)
            event["detail"] = json.loads(event["detail"]) if event["detail"] else None
            events.append(event)
        return events
