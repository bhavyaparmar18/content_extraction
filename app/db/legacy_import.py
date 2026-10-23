"""One-time import of the former per-store databases into ``app.db``.

Before 0001 the data lived in five files next to where ``app.db`` now goes:
auth.db, sop_records.db, template_records.db, gwp_guides.db and migrations.db.
``import_legacy`` copies them (with SQLite's backup API, so the copy is
consistent) into ``legacy_db_backup_<timestamp>/``, builds the new database
from those copies in ``app.db.importing``, verifies it and only then renames
it to ``app.db``. The old files are left in place, unused, for a rollback.

While copying it:
- drops migration jobs whose SOP, template or GWP version no longer exists,
  with their sections, artifacts and events (their artifact folders are moved
  into the backup folder, not deleted);
- clears ``sop_records.migrated_job_id`` that pointed at a dropped job;
- clears ``migration_jobs.created_by`` that names no existing user;
- replaces a numeric ``migration_jobs.template_id`` (a template record id) with its template_uid;
- stores every file path relative to the data folder.
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Optional

from app.config.settings import Settings
from app.db.connection import connect
from app.db.paths import data_root, to_stored
from app.db.schema import ensure_schema, forget

LEGACY_FILES = {
    "auth": "auth.db",
    "sop": "sop_records.db",
    "tpl": "template_records.db",
    "gwp": "gwp_guides.db",
    "mig": "migrations.db",
}

# (legacy alias, table, path columns) in insert order: parents first.
TABLES: list[tuple[str, str, tuple[str, ...]]] = [
    ("auth", "roles", ()),
    ("auth", "secret_questions", ()),
    ("auth", "users", ()),
    ("auth", "user_security", ()),
    ("auth", "user_sessions", ()),
    ("auth", "audit_events", ()),
    ("sop", "sop_records", ("output_path", "units_path", "migrated_path")),
    ("tpl", "template_records", ("upload_path", "output_path", "model_path", "normalized_path")),
    ("gwp", "gwp_guides", ("upload_path", "units_path", "rules_path", "report_path")),
    ("mig", "migration_jobs", ()),
    ("mig", "migration_sections", ()),
    ("mig", "migration_artifacts", ("path",)),
    ("mig", "migration_events", ()),
]


class LegacyImportError(RuntimeError):
    pass


@dataclass
class ImportReport:
    db_path: Path
    backup_dir: Optional[Path]
    dry_run: bool
    copied: dict[str, int] = field(default_factory=dict)
    dropped_jobs: dict[str, str] = field(default_factory=dict)  # job_id -> reason
    dropped_children: dict[str, int] = field(default_factory=dict)
    cleared_migrated_job_ids: list[int] = field(default_factory=list)
    cleared_created_by: list[str] = field(default_factory=list)
    remapped_template_ids: dict[str, str] = field(default_factory=dict)
    moved_job_dirs: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [f"{'Dry run: would import' if self.dry_run else 'Imported'} legacy databases into {self.db_path}"]
        if self.backup_dir:
            lines.append(f"  backup of the old files: {self.backup_dir}")
        for table, count in self.copied.items():
            lines.append(f"  {table:<20} {count:>6} rows")
        if self.dropped_jobs:
            lines.append(f"  dropped {len(self.dropped_jobs)} orphaned migration job(s):")
            lines += [f"    {job_id}: {reason}" for job_id, reason in self.dropped_jobs.items()]
            lines += [f"    with {n} {table} row(s)" for table, n in self.dropped_children.items() if n]
        if self.moved_job_dirs:
            lines.append(f"  moved {len(self.moved_job_dirs)} orphaned job folder(s) into the backup")
        if self.cleared_migrated_job_ids:
            lines.append(f"  cleared migrated_job_id on SOP record(s) {self.cleared_migrated_job_ids}")
        if self.cleared_created_by:
            lines.append(f"  cleared created_by (unknown user) on job(s) {self.cleared_created_by}")
        if self.remapped_template_ids:
            lines.append(f"  template ids replaced by template_uid: {self.remapped_template_ids}")
        return "\n".join(lines)


def legacy_files(db_path: Path) -> dict[str, Path]:
    """The old database files next to ``db_path`` (empty files are ignored)."""
    folder = Path(db_path).parent
    found = {}
    for alias, name in LEGACY_FILES.items():
        path = folder / name
        if path.is_file() and path.stat().st_size > 0:
            found[alias] = path
    return found


def needs_import(settings: Settings) -> bool:
    return not Path(settings.db_path).exists() and bool(legacy_files(settings.db_path))


def _backup(sources: dict[str, Path], target_dir: Path) -> dict[str, Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    copies = {}
    for alias, path in sources.items():
        copy = target_dir / path.name
        src = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        dst = sqlite3.connect(str(copy))
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()
        copies[alias] = copy
    return copies


def _columns(conn: sqlite3.Connection, schema: str, table: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA {schema}.table_info({table})")]


def _has_table(conn: sqlite3.Connection, schema: str, table: str) -> bool:
    return conn.execute(
        f"SELECT 1 FROM {schema}.sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone() is not None


def _copy(
    conn: sqlite3.Connection,
    alias: str,
    table: str,
    path_columns: tuple[str, ...],
    root: Path,
    keep: Callable[[dict[str, Any]], bool] = lambda row: True,
    fix: Callable[[dict[str, Any]], None] = lambda row: None,
) -> tuple[int, int]:
    """Copy the columns both schemas have; returns (copied, skipped)."""
    target = _columns(conn, "main", table)
    source = set(_columns(conn, alias, table))
    columns = [c for c in target if c in source]
    marks = ",".join("?" for _ in columns)
    copied = skipped = 0
    for raw in conn.execute(f"SELECT {', '.join(columns)} FROM {alias}.{table} ORDER BY rowid").fetchall():
        row = dict(zip(columns, raw))
        if not keep(row):
            skipped += 1
            continue
        fix(row)
        for column in path_columns:
            if column in row:
                row[column] = to_stored(row[column], root)
        conn.execute(f"INSERT INTO main.{table} ({', '.join(columns)}) VALUES ({marks})", list(row.values()))
        copied += 1
    return copied, skipped


def _orphaned_jobs(conn: sqlite3.Connection, attached: set[str], report: ImportReport) -> set[str]:
    """Jobs whose SOP, template or GWP version is missing; also records template id remaps."""
    if "mig" not in attached:
        return set()
    sops = {r[0] for r in conn.execute("SELECT id FROM sop.sop_records")} if "sop" in attached else set()
    templates, template_by_id = set(), {}
    if "tpl" in attached:
        for rid, uid, version in conn.execute("SELECT id, template_uid, template_version FROM tpl.template_records"):
            templates.add((uid, version))
            template_by_id[str(rid)] = uid
    guides = {(g, v) for g, v in conn.execute("SELECT guide_id, version FROM gwp.gwp_guides")} if "gwp" in attached else set()

    dropped = set()
    for job_id, sop_id, template_id, template_version, gwp_id, gwp_version in conn.execute(
        "SELECT job_id, sop_record_id, template_id, template_version, gwp_id, gwp_version FROM mig.migration_jobs"
    ):
        if (template_id, template_version) not in templates and template_id in template_by_id:
            report.remapped_template_ids[job_id] = template_by_id[template_id]
            template_id = template_by_id[template_id]
        reasons = []
        if sop_id not in sops:
            reasons.append(f"SOP record {sop_id} is missing")
        if (template_id, template_version) not in templates:
            reasons.append(f"template {template_id} v{template_version} is missing")
        if gwp_id is not None and (gwp_id, gwp_version) not in guides:
            reasons.append(f"GWP guide {gwp_id} v{gwp_version} is missing")
        if reasons:
            report.dropped_jobs[job_id] = "; ".join(reasons)
            dropped.add(job_id)
    return dropped


def _build(target: Path, copies: dict[str, Path], root: Path, report: ImportReport) -> None:
    forget(target)
    ensure_schema(target)
    conn = connect(target)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")  # rows arrive parents-first, but sop_records <-> migration_jobs is circular
        for alias, path in copies.items():
            conn.execute(f"ATTACH DATABASE ? AS {alias}", (str(path),))
        attached = {a for a in copies}

        conn.execute("BEGIN IMMEDIATE")
        try:
            dropped = _orphaned_jobs(conn, attached, report)
            users = {r[0] for r in conn.execute("SELECT user_id FROM auth.users")} if "auth" in attached else set()
            kept_jobs = (
                {r[0] for r in conn.execute("SELECT job_id FROM mig.migration_jobs")} - dropped if "mig" in attached else set()
            )

            def fix_sop(row):
                if row.get("migrated_job_id") and row["migrated_job_id"] not in kept_jobs:
                    report.cleared_migrated_job_ids.append(row["id"])
                    row["migrated_job_id"] = None

            def fix_job(row):
                row["template_id"] = report.remapped_template_ids.get(row["job_id"], row["template_id"])
                if row.get("created_by") is not None and row["created_by"] not in users:
                    report.cleared_created_by.append(row["job_id"])
                    row["created_by"] = None

            for alias, table, path_columns in TABLES:
                if alias not in attached or not _has_table(conn, alias, table):
                    continue
                if table == "sop_records":
                    copied, _ = _copy(conn, alias, table, path_columns, root, fix=fix_sop)
                elif table == "migration_jobs":
                    copied, _ = _copy(conn, alias, table, path_columns, root,
                                      keep=lambda row: row["job_id"] not in dropped, fix=fix_job)
                elif alias == "mig":
                    copied, skipped = _copy(conn, alias, table, path_columns, root,
                                            keep=lambda row: row["job_id"] not in dropped)
                    report.dropped_children[table] = skipped
                else:
                    copied, _ = _copy(conn, alias, table, path_columns, root)
                report.copied[table] = copied

            problems = conn.execute("PRAGMA main.foreign_key_check").fetchall()
            if problems:
                raise LegacyImportError(f"foreign key check failed: {[tuple(p) for p in problems[:10]]}")
            for alias, table, _ in TABLES:
                if alias in attached and _has_table(conn, alias, table):
                    source = conn.execute(f"SELECT COUNT(*) FROM {alias}.{table}").fetchone()[0]
                    target_count = conn.execute(f"SELECT COUNT(*) FROM main.{table}").fetchone()[0]
                    expected = source - report.dropped_children.get(table, 0) - (
                        len(dropped) if table == "migration_jobs" else 0
                    )
                    if target_count != expected:
                        raise LegacyImportError(f"{table}: {target_count} rows imported, expected {expected}")
            conn.execute("COMMIT")
        except BaseException:
            conn.execute("ROLLBACK")
            raise
        for alias in copies:
            conn.execute(f"DETACH DATABASE {alias}")
        conn.execute("PRAGMA journal_mode = DELETE")  # fold the WAL into the file before it is renamed
    finally:
        conn.close()


def import_legacy(settings: Settings, dry_run: bool = False) -> ImportReport:
    db_path = Path(settings.db_path)
    if db_path.exists():
        raise LegacyImportError(f"{db_path} already exists; nothing to import into")
    sources = legacy_files(db_path)
    if not sources:
        raise LegacyImportError(f"no legacy databases found next to {db_path}")
    root = data_root(settings)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    work = Path(tempfile.mkdtemp(prefix="app_db_dry_run_")) if dry_run else db_path.parent / f"legacy_db_backup_{stamp}"
    report = ImportReport(db_path=db_path, backup_dir=None if dry_run else work, dry_run=dry_run)
    target = work / "app.db.importing" if dry_run else db_path.with_name(db_path.name + ".importing")
    for leftover in (target, Path(f"{target}-wal"), Path(f"{target}-shm")):
        leftover.unlink(missing_ok=True)
    try:
        copies = _backup(sources, work)
        _build(target, copies, root, report)
        if dry_run:
            return report
        os.replace(target, db_path)
    except BaseException:
        for leftover in (target, Path(f"{target}-wal"), Path(f"{target}-shm")):
            leftover.unlink(missing_ok=True)
        raise
    finally:
        if dry_run:
            shutil.rmtree(work, ignore_errors=True)

    # Artifact folders of dropped jobs: kept with the backup, out of data/migrations.
    for job_id in report.dropped_jobs:
        folder = Path(settings.migration_v2_dir) / job_id
        if folder.is_dir():
            destination = work / "orphaned_job_artifacts" / job_id
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(folder), str(destination))
            report.moved_job_dirs.append(job_id)
    return report
