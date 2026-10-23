"""Migration v2 job persistence: jobs, per-section state, versioned artifacts and an audit log.

Same SQLite pattern as the other stores. Every status change goes through
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
from app.schemas.v2 import ArtifactKind, ArtifactRef, JobMode, JobStatus, MigrationJob, SectionState, SectionStatus

# Columns update_job may change; status goes through set_status.
_UPDATABLE = frozenset({"error", "failed_stage", "cancel_requested"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MigrationStore:
    def __init__(self, db_path: Path, settings: Optional[Settings] = None):
        self.db_path = Path(db_path)
        self.settings = settings
        self._root = data_root(settings)
        ensure_schema(self.db_path)

    # ── Jobs ──────────────────────────────────────────────────────────

    def create_job(self, job: MigrationJob) -> MigrationJob:
        now = _now()
        with transaction(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO migration_jobs (
                    job_id, sop_record_id, template_id, template_version, gwp_id, gwp_version,
                    mode, status, created_by, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job.job_id, job.sop_record_id, job.template_id, job.template_version, job.gwp_id,
                    job.gwp_version, job.mode.value, job.status.value, job.created_by, now, now,
                ),
            )
            self._add_event(conn, job.job_id, job.created_by, "created", None, job.status.value, None)
        return self.get_job(job.job_id)

    def get_job(self, job_id: str) -> Optional[MigrationJob]:
        with transaction(self.db_path) as conn:
            row = conn.execute("SELECT * FROM migration_jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                return None
            sections = conn.execute(
                "SELECT * FROM migration_sections WHERE job_id = ? ORDER BY position, target_section_id", (job_id,)
            ).fetchall()
            artifacts = conn.execute(
                "SELECT * FROM migration_artifacts WHERE job_id = ? ORDER BY id", (job_id,)
            ).fetchall()
        return MigrationJob(
            job_id=row["job_id"],
            sop_record_id=row["sop_record_id"],
            template_id=row["template_id"],
            template_version=row["template_version"],
            gwp_id=row["gwp_id"],
            gwp_version=row["gwp_version"],
            mode=JobMode(row["mode"]),
            status=JobStatus(row["status"]),
            sections=[
                SectionState(
                    target_section_id=s["target_section_id"], status=SectionStatus(s["status"]),
                    attempts=s["attempts"], last_error=s["last_error"],
                )
                for s in sections
            ],
            artifacts=[self._artifact(a) for a in artifacts],
            created_by=row["created_by"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            error=row["error"],
        )

    def get_job_row(self, job_id: str) -> Optional[dict[str, Any]]:
        """Raw row, including the store-only columns (failed_stage, cancel_requested)."""
        with transaction(self.db_path) as conn:
            row = conn.execute("SELECT * FROM migration_jobs WHERE job_id = ?", (job_id,)).fetchone()
            return dict(row) if row else None

    def list_jobs(self, status: Optional[str] = None, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        query = "SELECT * FROM migration_jobs"
        params: list[Any] = []
        if status:
            query += " WHERE status = ?"
            params.append(status)
        query += " ORDER BY created_at DESC, job_id DESC LIMIT ? OFFSET ?"
        params += [limit, offset]
        with transaction(self.db_path) as conn:
            return [dict(r) for r in conn.execute(query, params).fetchall()]

    def job_ids_with_status(self, statuses: list[JobStatus]) -> list[str]:
        if not statuses:
            return []
        marks = ",".join("?" for _ in statuses)
        with transaction(self.db_path) as conn:
            rows = conn.execute(
                f"SELECT job_id FROM migration_jobs WHERE status IN ({marks}) ORDER BY created_at",
                [s.value for s in statuses],
            ).fetchall()
        return [r["job_id"] for r in rows]

    def update_job(self, job_id: str, **fields: Any) -> None:
        unknown = set(fields) - _UPDATABLE
        if unknown:
            raise ValueError(f"cannot update migration_jobs columns: {sorted(unknown)}")
        if not fields:
            return
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with transaction(self.db_path) as conn:
            conn.execute(
                f"UPDATE migration_jobs SET {assignments}, updated_at = ? WHERE job_id = ?",
                (*fields.values(), _now(), job_id),
            )

    def set_status(
        self,
        job_id: str,
        status: JobStatus,
        actor: Optional[str] = None,
        event: str = "status",
        detail: Optional[dict] = None,
        expected: Optional[JobStatus] = None,
    ) -> bool:
        """Change the status and log it. With ``expected``, only if the job is still in that status."""
        with transaction(self.db_path, immediate=True) as conn:
            row = conn.execute("SELECT status FROM migration_jobs WHERE job_id = ?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            if expected is not None and row["status"] != expected.value:
                return False
            conn.execute(
                "UPDATE migration_jobs SET status = ?, updated_at = ? WHERE job_id = ?",
                (status.value, _now(), job_id),
            )
            self._add_event(conn, job_id, actor, event, row["status"], status.value, detail)
        return True

    # ── Sections ──────────────────────────────────────────────────────

    def init_sections(self, job_id: str, target_section_ids: list[str]) -> None:
        """Create the per-section rows once; keeps existing rows (a stage re-run must not reset them)."""
        with transaction(self.db_path) as conn:
            for position, section_id in enumerate(target_section_ids):
                conn.execute(
                    """
                    INSERT OR IGNORE INTO migration_sections (job_id, target_section_id, position, status)
                    VALUES (?, ?, ?, ?)
                    """,
                    (job_id, section_id, position, SectionStatus.PENDING.value),
                )

    def update_section(
        self,
        job_id: str,
        target_section_id: str,
        status: Optional[SectionStatus] = None,
        attempts: Optional[int] = None,
        last_error: Optional[str] = None,
    ) -> None:
        fields: dict[str, Any] = {}
        if status is not None:
            fields["status"] = status.value
        if attempts is not None:
            fields["attempts"] = attempts
        fields["last_error"] = last_error
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with transaction(self.db_path) as conn:
            conn.execute(
                f"UPDATE migration_sections SET {assignments} WHERE job_id = ? AND target_section_id = ?",
                (*fields.values(), job_id, target_section_id),
            )

    # ── Artifacts ─────────────────────────────────────────────────────

    def next_artifact_version(self, job_id: str, kind: ArtifactKind, scope: Optional[str] = None) -> int:
        with transaction(self.db_path) as conn:
            row = conn.execute(
                "SELECT MAX(version) AS v FROM migration_artifacts WHERE job_id = ? AND kind = ? AND scope = ?",
                (job_id, kind.value, scope or ""),
            ).fetchone()
        return (row["v"] or 0) + 1

    def add_artifact(self, job_id: str, ref: ArtifactRef) -> None:
        with transaction(self.db_path) as conn:
            self._insert_artifact(conn, job_id, ref)

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
                    "SELECT MAX(version) AS v FROM migration_artifacts WHERE job_id = ? AND kind = ? AND scope = ?",
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
            INSERT INTO migration_artifacts (job_id, kind, scope, version, path, sha256, created_at, created_by)
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
            INSERT INTO migration_events (job_id, at, actor, event, from_status, to_status, detail)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, _now(), actor, event, from_status, to_status, json.dumps(detail) if detail is not None else None),
        )

    def add_event(self, job_id: str, event: str, actor: Optional[str] = None, detail: Optional[dict] = None) -> None:
        with transaction(self.db_path) as conn:
            self._add_event(conn, job_id, actor, event, None, None, detail)

    def list_events(self, job_id: str) -> list[dict[str, Any]]:
        with transaction(self.db_path) as conn:
            rows = conn.execute("SELECT * FROM migration_events WHERE job_id = ? ORDER BY id", (job_id,)).fetchall()
        events = []
        for r in rows:
            event = dict(r)
            event["detail"] = json.loads(event["detail"]) if event["detail"] else None
            events.append(event)
        return events
