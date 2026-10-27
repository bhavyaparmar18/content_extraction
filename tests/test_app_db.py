"""The single application database: schema versions, enforced links, blocked deletes,
race-free version numbers, relative paths and the one-time import of the old files."""

import sqlite3
import threading
from pathlib import Path

import pytest

from app.config.settings import Settings
from app.db import RecordInUseError, connect, ensure_schema, transaction
from app.db.legacy_import import import_legacy, needs_import
from app.db.paths import from_stored, relocate, to_stored
from app.db.schema import latest_version
from app.schemas.v2 import ArtifactKind, MigrationJob
from app.services.migration_v2.artifacts import ArtifactWriter
from app.stores.auth_store import AuthStore
from app.stores.gwp_store import GwpStore
from app.stores.migration_store import MigrationStore
from app.stores.sop_store import SopStore
from app.stores.template_store import TemplateStore
from tests.db_helpers import seed_job_inputs, seed_users


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("SOP_DB_PATH", str(tmp_path / "data" / "app.db"))  # where the app keeps it: data/app.db
    s = Settings(project_root=tmp_path)
    s.resolve_paths(tmp_path)
    s.ensure_directories()
    return s


def _job(store: MigrationStore, sop_id: int, job_id: str = "MIG-1", **kwargs) -> MigrationJob:
    return store.create_job(MigrationJob(job_id=job_id, sop_record_id=sop_id, template_id="tpl", template_version=1, **kwargs))


# ── Schema and connection ────────────────────────────────────────────


def test_schema_is_versioned_and_idempotent(settings):
    assert ensure_schema(settings.db_path) == latest_version() == 2
    assert ensure_schema(settings.db_path) == 2
    conn = connect(settings.db_path)
    try:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    finally:
        conn.close()
    assert {"users", "sop_records", "template_records", "gwp_guides", "migration_jobs", "migration_artifacts",
            "glossaries", "language_templates", "translation_jobs", "translation_artifacts"} <= tables


def test_every_store_shares_one_file(settings):
    for store in (SopStore, TemplateStore, GwpStore, MigrationStore):
        store(settings.db_path, settings)
    AuthStore(settings.db_path, settings)
    assert [p.name for p in settings.db_path.parent.glob("*.db")] == ["app.db"]


def test_transaction_rolls_back_on_error(settings):
    ensure_schema(settings.db_path)
    with pytest.raises(RuntimeError):
        with transaction(settings.db_path) as conn:
            conn.execute("INSERT INTO roles (role_id, role_code, role_name, created_at, updated_at) VALUES ('r', 'R', 'R', '', '')")
            raise RuntimeError("boom")
    with transaction(settings.db_path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM roles WHERE role_id = 'r'").fetchone()[0] == 0


# ── Enforced links ───────────────────────────────────────────────────


def test_a_job_needs_an_existing_sop_template_gwp_and_user(settings):
    store = MigrationStore(settings.db_path, settings)
    sop_id = seed_job_inputs(settings.db_path, settings)
    with pytest.raises(sqlite3.IntegrityError):
        _job(store, sop_id + 100)
    with pytest.raises(sqlite3.IntegrityError):
        store.create_job(MigrationJob(job_id="MIG-T", sop_record_id=sop_id, template_id="nope", template_version=1))
    with pytest.raises(sqlite3.IntegrityError):
        _job(store, sop_id, gwp_id="GWP", gwp_version=1)
    with pytest.raises(sqlite3.IntegrityError):
        _job(store, sop_id, created_by="ghost")

    seed_users(settings.db_path, "alice")
    assert _job(store, sop_id, created_by="alice").created_by == "alice"  # no GWP is fine (optional)


def test_deleting_a_job_removes_its_sections_artifacts_and_events_and_unlinks_the_sop(settings, tmp_path):
    store = MigrationStore(settings.db_path, settings)
    sops = SopStore(settings.db_path, settings)
    sop_id = seed_job_inputs(settings.db_path, settings)
    _job(store, sop_id)
    store.init_sections("MIG-1", ["TGT-1"])
    ArtifactWriter(tmp_path / "artifacts", store).write("MIG-1", ArtifactKind.SECTION_PLAN, {"a": 1})
    sops.mark_migrated(sop_id, "MIG-1", str(tmp_path / "final.docx"))

    with transaction(settings.db_path) as conn:
        conn.execute("DELETE FROM migration_jobs WHERE job_id = 'MIG-1'")
        for table in ("migration_sections", "migration_artifacts", "migration_events"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
    assert sops.get_record_by_id(sop_id)["migrated_job_id"] is None


# ── Blocked deletes ──────────────────────────────────────────────────


def test_inputs_of_a_job_cannot_be_deleted_and_keep_their_files(settings):
    store = MigrationStore(settings.db_path, settings)
    sops, templates, guides = (SopStore(settings.db_path, settings), TemplateStore(settings.db_path, settings),
                               GwpStore(settings.db_path, settings))
    upload = settings.upload_dir / "SOP-T.docx"
    upload.write_bytes(b"sop")
    model = settings.template_output_dir / "tpl_v1_model.json"
    model.write_text("{}")
    rules = settings.gwp_dir / "GWP_v1_rules.json"
    rules.write_text("{}")

    sop_id = seed_job_inputs(settings.db_path, settings)
    template = templates.get_record_by_uid("tpl")
    templates.update_template_model(template["id"], str(model), None, "ready")
    guide = guides.create_record("GWP", "Guide", "pdf")
    guides.update_fields(guide["id"], rules_path=str(rules))
    _job(store, sop_id, gwp_id="GWP", gwp_version=1)

    with pytest.raises(RecordInUseError) as in_use:
        sops.delete_record(sop_id)
    assert in_use.value.status_code == 409 and in_use.value.job_ids == ["MIG-1"]
    with pytest.raises(RecordInUseError):
        templates.delete_record(template["id"])
    with pytest.raises(RecordInUseError):
        guides.delete_record(guide["id"])

    assert upload.exists() and model.exists() and rules.exists()
    assert sops.get_record_by_id(sop_id) and templates.get_record_by_id(template["id"]) and guides.get_record_by_id(guide["id"])

    # An unused version still deletes normally.
    other = sops.upsert_record(job_id="x", document_uid="OTHER")
    assert sops.delete_record(other["id"]) and sops.get_record_by_id(other["id"]) is None


def test_delete_api_answers_409_with_the_job_ids(settings):
    from fastapi.testclient import TestClient

    from app.main import app

    store = MigrationStore(settings.db_path, settings)
    sops = SopStore(settings.db_path, settings)
    _job(store, seed_job_inputs(settings.db_path, settings))
    with TestClient(app) as client:
        previous = app.state.sop_store
        app.state.sop_store = sops
        try:
            response = client.delete(f"/sops/{sops.get_records()[0]['id']}")
        finally:
            app.state.sop_store = previous
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RECORD_IN_USE" and "MIG-1" in response.json()["error"]["message"]


# ── Version numbers under concurrency ────────────────────────────────


def _parallel(n: int, work) -> list:
    results, errors = [None] * n, []
    barrier = threading.Barrier(n)

    def run(i):
        barrier.wait()
        try:
            results[i] = work(i)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    return results


def test_concurrent_uploads_get_distinct_versions(settings):
    sops = SopStore(settings.db_path, settings)
    templates = TemplateStore(settings.db_path, settings)
    guides = GwpStore(settings.db_path, settings)
    n = 8
    assert sorted(r["gpdat_version"] for r in _parallel(n, lambda i: sops.upsert_record(job_id="j", document_uid="D"))) == list(range(1, n + 1))
    assert sorted(r["template_version"] for r in _parallel(n, lambda i: templates.upsert_record(template_uid="T", template_name="T"))) == list(range(1, n + 1))
    assert sorted(r["version"] for r in _parallel(n, lambda i: guides.create_record("G", "G", "pdf"))) == list(range(1, n + 1))


def test_concurrent_artifact_writes_get_distinct_versions_and_intact_files(settings, tmp_path):
    store = MigrationStore(settings.db_path, settings)
    _job(store, seed_job_inputs(settings.db_path, settings))
    writer = ArtifactWriter(settings.migration_v2_dir, store)
    n = 8
    refs = _parallel(n, lambda i: writer.write("MIG-1", ArtifactKind.SECTION_PLAN, {"writer": i}))
    assert sorted(r.version for r in refs) == list(range(1, n + 1))
    for ref in store.get_job("MIG-1").artifacts:
        assert ArtifactWriter.read(ref)["writer"] in range(n)  # sha256 matches: no file was overwritten


def test_a_failed_index_insert_removes_the_file_it_wrote(settings):
    store = MigrationStore(settings.db_path, settings)
    writer = ArtifactWriter(settings.migration_v2_dir, store)
    with pytest.raises(sqlite3.IntegrityError):  # no such job: the foreign key refuses the index row
        writer.write("MIG-NONE", ArtifactKind.SECTION_PLAN, {"a": 1})
    assert not list(settings.migration_v2_dir.glob("MIG-NONE/*"))


def test_concurrent_failed_logins_are_all_counted(settings):
    auth = AuthStore(settings.db_path, settings)
    with transaction(settings.db_path) as conn:
        question = conn.execute("SELECT secret_question_id FROM secret_questions LIMIT 1").fetchone()[0]
    user = auth.create_user_with_security(
        "A", "B", "a@b.com", auth.get_default_role()["roleId"], "h", question, "h", correlation_id="c"
    )
    _parallel(6, lambda i: auth.record_failed_login(user["userId"], max_failed_attempts=100))
    assert auth.get_user_with_security_by_email("a@b.com")["failedLoginAttempts"] == 6


# ── Stored paths ─────────────────────────────────────────────────────


def test_a_path_recorded_under_another_data_folder_is_found_under_this_one(tmp_path):
    root = tmp_path / "data"
    moved = root / "template_output" / "T_v1_normalized.docx"
    moved.parent.mkdir(parents=True)
    moved.write_bytes(b"x")
    assert relocate(r"Z:\Other PC\data\project\data\template_output\T_v1_normalized.docx", root) == moved
    assert relocate("/home/someone/project/data/template_output/T_v1_normalized.docx", root) == moved
    assert relocate("template_output/T_v1_normalized.docx", root) == moved
    assert relocate(str(moved), root) == moved
    assert relocate(r"Z:\Other PC\data\template_output\missing.docx", root) is None
    assert relocate(r"Z:\Other PC\data", root) is None  # the data folder itself is not a file
    assert relocate(None, root) is None and relocate("", root) is None


def test_paths_are_stored_relative_to_the_data_folder(settings, tmp_path):
    root = tmp_path / "data"
    inside = root / "output" / "x_units.json"
    assert to_stored(str(inside), root) == "output/x_units.json"
    assert from_stored("output/x_units.json", root) == str(inside)
    outside = tmp_path / "elsewhere.json"
    assert to_stored(str(outside), root) == str(outside) and from_stored(str(outside), root) == str(outside)
    assert to_stored(None, root) is None and from_stored(None, root) is None

    sops = SopStore(settings.db_path, settings)
    record = sops.upsert_record(job_id="j", document_uid="D", units_path=str(inside))
    assert record["units_path"] == str(inside)
    with transaction(settings.db_path) as conn:
        assert conn.execute("SELECT units_path FROM sop_records").fetchone()[0] == "output/x_units.json"


# ── Import of the old per-store databases ────────────────────────────


def _legacy(data: Path, files: dict[str, str]) -> None:
    for name, sql in files.items():
        conn = sqlite3.connect(data / name)
        conn.executescript(sql)
        conn.commit()
        conn.close()


def _legacy_data(settings: Settings) -> Path:
    data = settings.db_path.parent
    d = str(data).replace("'", "''")
    _legacy(data, {
        "auth.db": f"""
            CREATE TABLE roles (role_id TEXT PRIMARY KEY, role_code TEXT, role_name TEXT, description TEXT,
                is_default INTEGER, is_active INTEGER, created_at TEXT, updated_at TEXT);
            INSERT INTO roles VALUES ('r1', 'REGULAR_USER', 'Regular User', '', 1, 1, 't', 't');
            CREATE TABLE users (user_id TEXT PRIMARY KEY, first_name TEXT, last_name TEXT, bi_email TEXT, role_id TEXT,
                status TEXT, is_email_verified INTEGER, email_verified_at TEXT, last_login_at TEXT, created_at TEXT,
                updated_at TEXT, deactivated_at TEXT);
            INSERT INTO users VALUES ('u1', 'A', 'B', 'a@b.com', 'r1', 'ACTIVE', 0, NULL, NULL, 't', 't', NULL);
        """,
        # No ALTER-added columns: the import copies the columns both schemas have.
        "sop_records.db": f"""
            CREATE TABLE sop_records (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, document_uid TEXT NOT NULL,
                gpdat_version INTEGER, status TEXT NOT NULL DEFAULT 'in_review', output_path TEXT,
                migrated_job_id TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
            INSERT INTO sop_records VALUES (5, 'b', 'SOP-A', 1, 'in_review', '{d}\\output\\SOP-A_v2.json', 'MIG-OK', 't', 't');
            INSERT INTO sop_records VALUES (6, 'b', 'SOP-B', 1, 'in_review', NULL, 'MIG-ORPHAN', 't', 't');
        """,
        "template_records.db": """
            CREATE TABLE template_records (id INTEGER PRIMARY KEY AUTOINCREMENT, template_uid TEXT, template_name TEXT,
                template_version INTEGER, status TEXT, created_at TEXT, updated_at TEXT);
            INSERT INTO template_records VALUES (21, 'TPL', 'Template', 1, 'ready', 't', 't');
        """,
        "gwp_guides.db": "CREATE TABLE gwp_guides (id INTEGER PRIMARY KEY, guide_id TEXT, guide_name TEXT, version INTEGER, status TEXT, created_at TEXT, updated_at TEXT);",
        "migrations.db": f"""
            CREATE TABLE migration_jobs (job_id TEXT PRIMARY KEY, sop_record_id INTEGER, template_id TEXT,
                template_version INTEGER, gwp_id TEXT, gwp_version INTEGER, mode TEXT, status TEXT, created_by TEXT,
                error TEXT, failed_stage TEXT, cancel_requested INTEGER DEFAULT 0, created_at TEXT, updated_at TEXT);
            INSERT INTO migration_jobs VALUES ('MIG-OK', 5, '21', 1, NULL, NULL, 'review', 'COMPLETED', 'u1', NULL, NULL, 0, '2026-01-01T00:00:00', '2026-01-01T00:00:00');
            INSERT INTO migration_jobs VALUES ('MIG-GHOST', 6, 'TPL', 1, NULL, NULL, 'review', 'COMPLETED', 'deleted-user', NULL, NULL, 0, '2026-01-01T00:00:00', '2026-01-01T00:00:00');
            INSERT INTO migration_jobs VALUES ('MIG-ORPHAN', 18, 'TPL', 1, NULL, NULL, 'review', 'COMPLETED', 'u1', NULL, NULL, 0, '2026-01-01T00:00:00', '2026-01-01T00:00:00');
            CREATE TABLE migration_sections (job_id TEXT, target_section_id TEXT, position INTEGER, status TEXT,
                attempts INTEGER, last_error TEXT, PRIMARY KEY (job_id, target_section_id));
            INSERT INTO migration_sections VALUES ('MIG-ORPHAN', 'TGT-1', 0, 'drafted', 0, NULL);
            CREATE TABLE migration_artifacts (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, kind TEXT, scope TEXT,
                version INTEGER, path TEXT, sha256 TEXT, created_at TEXT, created_by TEXT);
            INSERT INTO migration_artifacts VALUES (1, 'MIG-OK', 'section_plan', '', 1, '{d}\\migrations\\MIG-OK\\section_plan_v1.json', 'x', '2026-01-01T00:00:00', 'system');
            INSERT INTO migration_artifacts VALUES (2, 'MIG-ORPHAN', 'section_plan', '', 1, '{d}\\migrations\\MIG-ORPHAN\\section_plan_v1.json', 'x', '2026-01-01T00:00:00', 'system');
            CREATE TABLE migration_events (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, at TEXT, actor TEXT,
                event TEXT, from_status TEXT, to_status TEXT, detail TEXT);
            INSERT INTO migration_events (job_id, at, event) VALUES ('MIG-OK', 't', 'created'), ('MIG-ORPHAN', 't', 'created');
        """,
    })
    (settings.migration_v2_dir / "MIG-ORPHAN").mkdir(parents=True)
    (settings.migration_v2_dir / "MIG-ORPHAN" / "section_plan_v1.json").write_text("{}")
    return data


def test_legacy_import_dry_run_changes_nothing(settings):
    data = _legacy_data(settings)
    before = sorted(p.name for p in data.iterdir())
    assert needs_import(settings)
    report = import_legacy(settings, dry_run=True)
    assert report.dropped_jobs.keys() == {"MIG-ORPHAN"}
    assert sorted(p.name for p in data.iterdir()) == before and not settings.db_path.exists()


def test_legacy_import_merges_drops_orphans_and_relativizes_paths(settings):
    data = _legacy_data(settings)
    report = import_legacy(settings)

    assert settings.db_path.exists() and not needs_import(settings)
    assert report.backup_dir.is_dir() and (report.backup_dir / "migrations.db").exists()
    assert (data / "migrations.db").exists()  # old files stay, unused, for a rollback
    assert report.dropped_jobs == {"MIG-ORPHAN": "SOP record 18 is missing"}
    assert report.dropped_children == {"migration_sections": 1, "migration_artifacts": 1, "migration_events": 1}
    assert report.remapped_template_ids == {"MIG-OK": "TPL"}
    assert report.cleared_created_by == ["MIG-GHOST"] and report.cleared_migrated_job_ids == [6]
    assert not (settings.migration_v2_dir / "MIG-ORPHAN").exists()
    assert (report.backup_dir / "orphaned_job_artifacts" / "MIG-ORPHAN" / "section_plan_v1.json").exists()

    store = MigrationStore(settings.db_path, settings)
    assert {j["job_id"] for j in store.list_jobs()} == {"MIG-OK", "MIG-GHOST"}
    job = store.get_job("MIG-OK")
    assert job.template_id == "TPL" and job.created_by == "u1"
    assert job.artifacts[0].path == str(settings.migration_v2_dir / "MIG-OK" / "section_plan_v1.json")
    sop = SopStore(settings.db_path, settings).get_record_by_id(5)
    assert sop["output_path"] == str(settings.output_dir / "SOP-A_v2.json") and sop["migrated_job_id"] == "MIG-OK"
    with transaction(settings.db_path) as conn:
        assert conn.execute("SELECT output_path FROM sop_records WHERE id = 5").fetchone()[0] == "output/SOP-A_v2.json"
        assert conn.execute("PRAGMA foreign_key_check").fetchall() == []

    with pytest.raises(Exception):
        import_legacy(settings)  # app.db exists: never imported twice
