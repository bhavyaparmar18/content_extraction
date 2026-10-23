"""Phase 13: the backend routes the review UI needs (final preview, the job's original SOP and template files)."""

from __future__ import annotations

import io

import pytest
from docx import Document

from app.schemas.v2 import ArtifactKind, JobStatus, QualityReport
from app.services.migration_v2.export import ExportBlocked, export_word, previous_export, render_final
from app.db import transaction
from tests.test_v2_assembly import _export_env
from tests.test_v2_renderer import _texts, tpl  # noqa: F401  (fixture)


def _accept_gap(e):
    accepted = e.gap.model_copy(update={"resolved": True, "resolution_note": "reviewer-1: N/A"})
    e.writer.write(e.job.job_id, ArtifactKind.QUALITY_REPORT, QualityReport(job_id=e.job.job_id, version=2, issues=[accepted]))
    e.store.set_status(e.job.job_id, JobStatus.COMPLETED_WITH_WARNINGS, "system")
    return e.store.get_job(e.job.job_id)


def test_render_final_previews_without_saving_anything(tpl, tmp_path):  # noqa: F811
    e = _export_env(tmp_path, tpl)
    e.store.set_status(e.job.job_id, JobStatus.HUMAN_REVIEW_REQUIRED, "system")
    with pytest.raises(ExportBlocked) as blocked:
        render_final(e.store.get_job(e.job.job_id), e.store, e.writer)
    assert blocked.value.code == "EXPORT_BLOCKED"

    job = _accept_gap(e)
    artifacts_before, events_before = len(job.artifacts), len(e.store.list_events(job.job_id))
    final = render_final(job, e.store, e.writer)
    assert final.report.ok and final.data and final.accepted == ("TGT-2-GEOGRAPHY",)
    assert "Source content not found" not in _texts(Document(io.BytesIO(final.data)))
    job = e.store.get_job(job.job_id)
    assert len(job.artifacts) == artifacts_before and len(e.store.list_events(job.job_id)) == events_before
    assert e.sops.get_record_by_id(e.sop["id"]).get("migrated_path") is None
    assert not list(e.writer.job_dir(job.job_id).glob("tmp*"))  # the work directory is gone
    assert previous_export(job, e.store, e.writer) is None

    exported = export_word(job, e.store, e.writer, e.sops, "reviewer-1")
    assert previous_export(e.store.get_job(job.job_id), e.store, e.writer) == exported.docx


def _api(env):
    from fastapi.testclient import TestClient

    from app.api.auth import require_user
    from app.config.settings import get_settings
    from app.main import app

    class Api:
        def __enter__(self):
            app.dependency_overrides[get_settings] = lambda: env.settings
            app.dependency_overrides[require_user] = lambda: {"userId": "reviewer-1"}
            self.ctx = TestClient(app)
            self.client = self.ctx.__enter__()
            self.previous = app.state.migration_orchestrator
            self.orch = env.orchestrator()
            app.state.migration_orchestrator = self.orch
            return self

        def __exit__(self, *exc):
            self.client.portal.call(self.orch.stop)
            app.state.migration_orchestrator = self.previous
            self.ctx.__exit__(*exc)
            app.dependency_overrides.pop(get_settings, None)
            app.dependency_overrides.pop(require_user, None)

    return Api()


def test_api_serves_the_jobs_source_and_template_files_and_refuses_an_early_preview(tmp_path):
    from tests.test_v2_migration_jobs import Env, _wait_for

    env = Env(tmp_path)
    (env.settings.upload_dir / "SOP-1.docx").write_bytes(b"source-docx")
    original = env.settings.template_upload_dir / "TPL_v1.docx"
    normalized = tmp_path / "TPL_v1_normalized.docx"
    original.write_bytes(b"template-original")
    normalized.write_bytes(b"template-normalized")
    record = env.template_store.get_record_by_uid("TPL")
    with transaction(env.template_store.db_path) as conn:
        conn.execute("UPDATE template_records SET upload_path = ?, normalized_path = ? WHERE id = ?",
                     (str(original), str(normalized), record["id"]))

    with _api(env) as api:
        client, base = api.client, "/api/v1/migrations"
        job_id = client.post(base, json={"sop_record_id": env.sop["id"], "template_id": "TPL", "mode": "auto"}).json()["job_id"]
        _wait_for(client, job_id, {"HUMAN_REVIEW_REQUIRED"})

        source = client.get(f"{base}/{job_id}/source/file")
        assert source.status_code == 200 and source.content == b"source-docx"
        assert source.headers["content-type"].startswith("application/vnd.openxmlformats")
        assert client.get(f"{base}/{job_id}/template/file").content == b"template-normalized"
        assert client.get(f"{base}/{job_id}/template/file?variant=original").content == b"template-original"
        assert client.get(f"{base}/{job_id}/template/file?variant=../x").status_code == 422

        preview = client.get(f"{base}/{job_id}/export/preview")
        assert preview.status_code == 409 and preview.json()["error"]["code"] == "EXPORT_BLOCKED"

        (env.settings.upload_dir / "SOP-1.docx").unlink()
        missing = client.get(f"{base}/{job_id}/source/file")
        assert missing.status_code == 404 and missing.json()["error"]["code"] == "SOURCE_FILE_MISSING"
