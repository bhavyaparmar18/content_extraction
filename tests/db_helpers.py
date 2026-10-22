"""Rows that migration jobs reference: the shared app.db enforces their links."""

from pathlib import Path

from app.config.settings import Settings
from app.db import transaction
from app.stores.auth_store import AuthStore
from app.stores.sop_store import SopStore
from app.stores.template_store import TemplateStore


def seed_users(db_path: Path, *user_ids: str) -> None:
    """Users with fixed ids (``migration_jobs.created_by`` must name a user)."""
    AuthStore(db_path)  # schema and roles
    with transaction(db_path) as conn:
        role_id = conn.execute("SELECT role_id FROM roles WHERE role_code = 'REGULAR_USER'").fetchone()[0]
        for user_id in user_ids:
            conn.execute(
                """
                INSERT OR IGNORE INTO users (user_id, first_name, last_name, bi_email, role_id, created_at, updated_at)
                VALUES (?, 'Test', 'User', ?, ?, '2026-01-01', '2026-01-01')
                """,
                (user_id, f"{user_id}@example.com", role_id),
            )


def seed_job_inputs(db_path: Path, settings: Settings, template_uid: str = "tpl", document_uid: str = "SOP-T") -> int:
    """An SOP record and template v1 for a job built by hand; returns the SOP record id."""
    templates = TemplateStore(db_path, settings)
    if templates.get_record_by_uid(template_uid) is None:
        templates.upsert_record(template_uid=template_uid, template_name=template_uid)
    return SopStore(db_path, settings).upsert_record(job_id="x", document_uid=document_uid)["id"]
