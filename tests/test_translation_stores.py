"""Translation stores on the shared app.db: glossary and language template versions,
translation jobs with their artifacts and events, enforced links and blocked deletes."""

import sqlite3
import threading

import pytest

from app.config.settings import Settings
from app.db import RecordInUseError, transaction
from app.schemas.v2 import ArtifactKind, MigrationJob, TranslationJob, TranslationStatus
from app.services.migration_v2.artifacts import ArtifactWriter
from app.stores.glossary_store import GlossaryStore
from app.stores.language_template_store import LanguageTemplateStore
from app.stores.migration_store import MigrationStore
from app.stores.translation_store import TranslationStore
from tests.db_helpers import seed_job_inputs, seed_users


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("SOP_DB_PATH", str(tmp_path / "data" / "app.db"))
    s = Settings(project_root=tmp_path)
    s.resolve_paths(tmp_path)
    s.ensure_directories()
    return s


@pytest.fixture
def migration(settings) -> str:
    """A migration job to translate."""
    sop_id = seed_job_inputs(settings.db_path, settings)
    MigrationStore(settings.db_path, settings).create_job(
        MigrationJob(job_id="MIG-1", sop_record_id=sop_id, template_id="tpl", template_version=1))
    return "MIG-1"


def _job(store: TranslationStore, job_id: str = "TRN-1", **kwargs) -> TranslationJob:
    return store.create_job(TranslationJob(job_id=job_id, migration_job_id="MIG-1", language="fr-FR", **kwargs))


# ── Versioned records ────────────────────────────────────────────────


@pytest.mark.parametrize("store_class", [GlossaryStore, LanguageTemplateStore])
def test_versions_count_up_per_record_and_filter_by_language(settings, store_class):
    store = store_class(settings.db_path, settings)
    assert store.get_next_version("R") == 1
    first = store.create_record("R", "Record", "de-DE")
    second = store.create_record("R", "Record", "de-DE")
    store.create_record("Other", "Other", "ja-JP")
    assert (first["version"], second["version"], first["status"]) == (1, 2, "uploaded")
    assert store.get_latest("R")["id"] == second["id"]
    assert store.get_version("R", 1)["id"] == first["id"]
    assert [r["version"] for r in store.get_records(language="de-DE")] == [2, 1]
    assert [r[store.ID_COLUMN] for r in store.get_records(language="ja-JP")] == ["Other"]


def test_records_take_only_supported_languages(settings):
    with pytest.raises(ValueError, match="unsupported language"):
        GlossaryStore(settings.db_path, settings).create_record("G", "G", "pt-PT")


def test_concurrent_uploads_never_share_a_version(settings):
    store = GlossaryStore(settings.db_path, settings)
    versions, errors = [], []

    def upload():
        try:
            versions.append(store.create_record("G", "G", "fr-FR")["version"])
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)

    threads = [threading.Thread(target=upload) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors and sorted(versions) == list(range(1, 9))


def test_paths_are_stored_relative_to_the_data_folder(settings):
    store = GlossaryStore(settings.db_path, settings)
    entries = settings.glossary_dir / "G_v1_entries.json"
    record = store.create_record("G", "G", "fr-FR", upload_path=str(settings.glossary_upload_dir / "G_v1.csv"))
    record = store.update_fields(record["id"], entries_path=str(entries), status="in_review", total_entries=3)
    assert record["entries_path"] == str(entries) and record["total_entries"] == 3
    with transaction(settings.db_path) as conn:
        raw = conn.execute("SELECT upload_path, entries_path FROM glossaries").fetchone()
    assert (raw["upload_path"], raw["entries_path"]) == ("glossaries/uploads/G_v1.csv", "glossaries/G_v1_entries.json")


def test_unknown_columns_and_statuses_are_refused(settings):
    store = LanguageTemplateStore(settings.db_path, settings)
    record = store.create_record("L", "L", "it-IT")
    with pytest.raises(ValueError, match="cannot update"):
        store.update_fields(record["id"], language="fr-FR")
    with pytest.raises(ValueError, match="invalid"):
        store.update_fields(record["id"], status="approved")  # glossaries are approved; templates become ready
    with pytest.raises(ValueError, match="cannot insert"):
        store.create_record("L", "L", "it-IT", entries_path="x")


# ── Translation jobs ─────────────────────────────────────────────────


def test_a_job_needs_no_glossary_or_language_template(settings, migration):
    job = _job(TranslationStore(settings.db_path, settings))
    assert (job.status, job.glossary_id, job.language_template_id) == (TranslationStatus.PENDING, None, None)


def test_a_job_must_name_existing_records(settings, migration):
    store = TranslationStore(settings.db_path, settings)
    with pytest.raises(sqlite3.IntegrityError):
        store.create_job(TranslationJob(job_id="TRN-X", migration_job_id="MIG-404", language="fr-FR"))
    with pytest.raises(sqlite3.IntegrityError):
        _job(store, glossary_id="G", glossary_version=1)
    with pytest.raises(sqlite3.IntegrityError):
        _job(store, language_template_id="L", language_template_version=1)
    with pytest.raises(sqlite3.IntegrityError):
        _job(store, created_by="ghost")

    seed_users(settings.db_path, "alice")
    GlossaryStore(settings.db_path, settings).create_record("G", "G", "fr-FR")
    LanguageTemplateStore(settings.db_path, settings).create_record("L", "L", "fr-FR")
    job = _job(store, glossary_id="G", glossary_version=1, language_template_id="L", language_template_version=1,
               created_by="alice")
    assert (job.glossary_version, job.language_template_version, job.created_by) == (1, 1, "alice")


def test_status_changes_are_compare_and_swap_and_logged(settings, migration):
    store = TranslationStore(settings.db_path, settings)
    _job(store)
    assert store.set_status("TRN-1", TranslationStatus.PREPARING, expected=TranslationStatus.PENDING)
    assert not store.set_status("TRN-1", TranslationStatus.TRANSLATING, expected=TranslationStatus.PENDING)
    assert store.job_ids_with_status([TranslationStatus.PREPARING]) == ["TRN-1"]
    events = [(e["event"], e["from_status"], e["to_status"]) for e in store.list_events("TRN-1")]
    assert events == [("created", None, "PENDING"), ("status", "PENDING", "PREPARING")]
    with pytest.raises(KeyError):
        store.set_status("TRN-404", TranslationStatus.PREPARING)


def test_approval_only_from_review_and_records_who(settings, migration):
    seed_users(settings.db_path, "bob")
    store = TranslationStore(settings.db_path, settings)
    _job(store)
    assert not store.approve("TRN-1", "bob")
    store.set_status("TRN-1", TranslationStatus.REVIEW_PENDING)
    assert store.approve("TRN-1", "bob")
    job = store.get_job("TRN-1")
    assert (job.status, job.approved_by, job.approved_at is not None, job.is_terminal) == (
        TranslationStatus.APPROVED, "bob", True, True)


def test_list_jobs_by_migration_and_language(settings, migration):
    store = TranslationStore(settings.db_path, settings)
    _job(store, "TRN-1")
    store.create_job(TranslationJob(job_id="TRN-2", migration_job_id="MIG-1", language="ja-JP"))
    assert {r["job_id"] for r in store.list_jobs(migration_job_id="MIG-1")} == {"TRN-1", "TRN-2"}
    assert [r["job_id"] for r in store.list_jobs(language="ja-JP")] == ["TRN-2"]
    store.update_job("TRN-1", error="boom", failed_stage="TRANSLATING")
    assert store.get_job_row("TRN-1")["failed_stage"] == "TRANSLATING"
    with pytest.raises(ValueError):
        store.update_job("TRN-1", status="APPROVED")


def test_artifacts_are_versioned_per_scope_through_the_shared_writer(settings, migration):
    store = TranslationStore(settings.db_path, settings)
    _job(store)
    writer = ArtifactWriter(settings.translation_dir, store)
    first = writer.write("TRN-1", ArtifactKind.TRANSLATION, {"a": 1}, scope="TGT-3")
    second = writer.write("TRN-1", ArtifactKind.TRANSLATION, {"a": 2}, scope="TGT-3")
    other = writer.write("TRN-1", ArtifactKind.TRANSLATION, {"a": 3}, scope="template")
    assert (first.version, second.version, other.version) == (1, 2, 1)
    assert first.path.endswith("translation_TGT-3_v1.json")
    job = store.get_job("TRN-1")
    assert writer.read(job.latest_artifact(ArtifactKind.TRANSLATION, "TGT-3")) == {"a": 2}
    assert store.next_artifact_version("TRN-1", ArtifactKind.TRANSLATION, "TGT-3") == 3
    assert sum(e["event"] == "artifact" for e in store.list_events("TRN-1")) == 3


def test_deleting_a_job_removes_its_artifacts_and_events(settings, migration):
    store = TranslationStore(settings.db_path, settings)
    _job(store)
    ArtifactWriter(settings.translation_dir, store).write("TRN-1", ArtifactKind.SEGMENTS, {"a": 1})
    with transaction(settings.db_path) as conn:
        conn.execute("DELETE FROM translation_jobs WHERE job_id = 'TRN-1'")
        for table in ("translation_artifacts", "translation_events"):
            assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table


def test_a_translated_migration_cannot_be_deleted(settings, migration):
    _job(TranslationStore(settings.db_path, settings))
    with pytest.raises(sqlite3.IntegrityError):
        with transaction(settings.db_path) as conn:
            conn.execute("DELETE FROM migration_jobs WHERE job_id = 'MIG-1'")


# ── Blocked deletes ──────────────────────────────────────────────────


@pytest.mark.parametrize("store_class, job_fields", [
    (GlossaryStore, {"glossary_id": "R", "glossary_version": 1}),
    (LanguageTemplateStore, {"language_template_id": "R", "language_template_version": 1}),
])
def test_a_version_in_use_cannot_be_deleted_and_keeps_its_file(settings, migration, store_class, job_fields):
    store = store_class(settings.db_path, settings)
    upload = settings.translation_dir / "R_v1.bin"
    upload.write_bytes(b"x")
    used = store.create_record("R", "R", "fr-FR", upload_path=str(upload))
    unused = store.create_record("R", "R", "fr-FR")
    _job(TranslationStore(settings.db_path, settings), **job_fields)

    with pytest.raises(RecordInUseError) as err:
        store.delete_record(used["id"])
    assert err.value.job_ids == ["TRN-1"] and "translation job(s) TRN-1" in err.value.message
    assert upload.exists() and store.get_record_by_id(used["id"])
    assert store.delete_record(unused["id"]) and store.get_record_by_id(unused["id"]) is None
    assert store.delete_record(unused["id"]) is False
