"""Phase T4: translation jobs. The orchestrator (PREPARING, cancel, retry, resume) and the job API
(create one job per language with optional glossary and language template, list, get, audit, segments)."""

from __future__ import annotations

import io
import re
import time
from types import SimpleNamespace

import pytest
from docx import Document
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import translations
from app.api.auth import require_user
from app.config.settings import Settings, get_settings
from app.core.exception_handlers import register_exception_handlers
from app.db import RecordInUseError
from app.schemas.v2 import ArtifactKind, GlossaryEntry, JobStatus, SegmentKind, SegmentSet, TranslationStatus
from app.services.migration_v2.artifacts import ArtifactWriter
from app.services.migration_v2.orchestrator import JobStateError
from app.services.translation import glossary_service
from app.services.translation.orchestrator import TranslationOrchestrator
from app.services.translation.translator import TranslatedSegment, TranslatorOutput
from app.stores.glossary_store import GlossaryStore
from app.stores.language_template_store import LanguageTemplateStore
from app.stores.translation_store import TranslationStore
from tests.db_helpers import seed_users
from tests.test_v2_api_ui import _accept_gap
from tests.test_v2_assembly import _export_env
from tests.test_v2_drafter import FakeChain, FakeFactory
from tests.test_v2_renderer import tpl  # noqa: F401  (fixture)


def _env(tmp_path, tpl, factory=None):  # noqa: F811
    """A completed fixture migration and a translation orchestrator. Without a chain *factory* only PREPARING
    runs (jobs wait at TRANSLATING, as in T4); with one, TRANSLATING, CHECKING and REPAIRING run too."""
    e = _export_env(tmp_path, tpl)
    migration = _accept_gap(e)  # COMPLETED_WITH_WARNINGS, the gap accepted as N/A
    settings = Settings(project_root=tmp_path)
    settings.resolve_paths(tmp_path)
    settings.ensure_directories()
    store = TranslationStore(e.store.db_path, settings)
    glossaries = GlossaryStore(e.store.db_path, settings)
    templates = LanguageTemplateStore(e.store.db_path, settings)
    orch = TranslationOrchestrator(store, ArtifactWriter(tmp_path / "translations", store), e.store, e.writer,
                                   glossaries, templates, settings, chain_factory=factory)
    if factory is None:
        for status in (TranslationStatus.TRANSLATING, TranslationStatus.CHECKING, TranslationStatus.REPAIRING):
            orch.stages.pop(status)
    return SimpleNamespace(e=e, migration=migration, settings=settings, store=store, glossaries=glossaries,
                           templates=templates, orch=orch)


def _glossary(env, language="de-DE", glossary_id="g-de", approve=True) -> dict:
    record = glossary_service.create_version(
        env.glossaries, env.settings, glossary_id=glossary_id, name="Terms", language=language,
        entries=[GlossaryEntry(source_term="deviation", target_term="Abweichung")])
    return glossary_service.approve(env.glossaries, record) if approve else record


def _template(env, tmp_path, language="de-DE", template_id="t-de", status="ready") -> dict:
    path = tmp_path / f"{template_id}_front_matter.docx"
    Document().save(str(path))
    return env.templates.create_record(template_id, "Template", language, front_matter_path=str(path), status=status)


# ── A fake translator (also used by test_translation_translator) ──────

_LINE = re.compile(r'^\[(SEG-\d+)\] \(([^)]*)\)(?: \(in: ".*"\))? (.*)$')


def asked(prompt: str) -> list[tuple[str, str]]:
    """(segment id, English text) of each segment a prompt asks for."""
    body = prompt.split("SEGMENTS\n", 1)[1].split("\n\nREPAIR:", 1)[0]
    return [(m.group(1), m.group(3)) for line in body.splitlines() if (m := _LINE.match(line))]


def translating(transform=lambda key, text, repair: f"FR {text}"):
    """A translator fake: every asked segment, passed through ``transform(key, text, is_repair)``."""
    def respond(prompt: str, n: int) -> TranslatorOutput:
        repair = "REPAIR:" in prompt
        return TranslatorOutput(translations=[TranslatedSegment(segment_id=k, translation=transform(k, t, repair))
                                              for k, t in asked(prompt)])
    return respond


# ── Orchestrator ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_preparing_snapshots_the_english_final_and_waits_at_translating(tpl, tmp_path):  # noqa: F811
    env = _env(tmp_path, tpl)
    job = env.orch.create(env.migration.job_id, "de-DE")
    job = await env.orch.wait(job.job_id)
    assert job.status == TranslationStatus.TRANSLATING and job.job_id.startswith("TRN-")

    kinds = {(a.kind, a.scope) for a in job.artifacts}
    for kind in (ArtifactKind.SOURCE_MODEL, ArtifactKind.TEMPLATE_MODEL, ArtifactKind.SLOT_PLAN,
                 ArtifactKind.ASSEMBLED_DRAFT, ArtifactKind.NUMBER_MAP, ArtifactKind.SEGMENTS):
        assert (kind, None) in kinds
    assert (ArtifactKind.DOCX, "english") in kinds and (ArtifactKind.RENDER_REPORT, "english") in kinds
    assert {s for k, s in kinds if k == ArtifactKind.SECTION_DRAFT} == {f"TGT-{n}" for n in range(1, 7)}
    assert not {k for k, _ in kinds} & {ArtifactKind.GLOSSARY, ArtifactKind.FRONT_MATTER}

    segments = env.orch.artifacts.latest(job, ArtifactKind.SEGMENTS, SegmentSet)
    assert segments.migration_job_id == env.migration.job_id and segments.accepted_gaps == ["TGT-2-GEOGRAPHY"]
    assert set(segments.counts) == {k.value for k in SegmentKind}
    assert len(segments.notes) == 2 and "no language template" in segments.notes[1]
    english = job.latest_artifact(ArtifactKind.DOCX, "english")
    assert segments.english_docx_sha256 == english.sha256
    Document(io.BytesIO(env.orch.artifacts.read_bytes(english)))  # a Word file

    events = [e["event"] for e in env.store.list_events(job.job_id)]
    assert {"no_glossary", "no_language_template", "segments"} <= set(events)
    assert "failed" not in events and "resumed" not in events


@pytest.mark.asyncio
async def test_the_glossary_and_front_matter_are_snapshotted_when_named(tpl, tmp_path):  # noqa: F811
    env = _env(tmp_path, tpl)
    glossary, template = _glossary(env), _template(env, tmp_path)
    job = env.orch.create(env.migration.job_id, "de-DE", ("g-de", glossary["version"]), ("t-de", template["version"]))
    job = await env.orch.wait(job.job_id)
    assert job.status == TranslationStatus.TRANSLATING
    snapshot = job.latest_artifact(ArtifactKind.FRONT_MATTER)
    assert env.orch.artifacts.read_bytes(snapshot) == (tmp_path / "t-de_front_matter.docx").read_bytes()
    assert job.latest_artifact(ArtifactKind.GLOSSARY) is not None
    assert env.orch.artifacts.latest(job, ArtifactKind.SEGMENTS, SegmentSet).notes == []

    # A version a job uses cannot be deleted.
    with pytest.raises(RecordInUseError):
        env.glossaries.delete_record(glossary["id"])
    with pytest.raises(RecordInUseError):
        env.templates.delete_record(template["id"])


@pytest.mark.asyncio
async def test_a_migration_that_is_not_completed_fails_and_a_retry_runs_again(tpl, tmp_path):  # noqa: F811
    env = _env(tmp_path, tpl)
    env.e.store.set_status(env.migration.job_id, JobStatus.HUMAN_REVIEW_REQUIRED, "system")
    job = await env.orch.wait(env.orch.create(env.migration.job_id, "fr-FR").job_id)
    assert job.status == TranslationStatus.FAILED_TECHNICAL and "HUMAN_REVIEW_REQUIRED" in job.error
    assert env.store.get_job_row(job.job_id)["failed_stage"] == "PREPARING"

    with pytest.raises(JobStateError) as refused:
        env.orch.retry(job.job_id, TranslationStatus.TRANSLATING, "reviewer")
    assert refused.value.code == "MISSING_ARTIFACTS"

    env.e.store.set_status(env.migration.job_id, JobStatus.COMPLETED_WITH_WARNINGS, "system")
    env.orch.retry(job.job_id, None, None)
    job = await env.orch.wait(job.job_id)
    assert job.status == TranslationStatus.TRANSLATING and job.error is None


@pytest.mark.asyncio
async def test_cancel_resume_and_retry(tpl, tmp_path):  # noqa: F811
    env = _env(tmp_path, tpl)
    waiting = env.orch.create(env.migration.job_id, "fr-FR", submit=False)
    cancelled = env.orch.cancel(waiting.job_id, None)
    assert cancelled.status == TranslationStatus.CANCELLED
    with pytest.raises(JobStateError):
        env.orch.cancel(waiting.job_id, None)

    pending = env.orch.create(env.migration.job_id, "it-IT", submit=False)
    assert env.orch.resume_incomplete() == [pending.job_id]  # PENDING resumes; CANCELLED does not
    assert (await env.orch.wait(pending.job_id)).status == TranslationStatus.TRANSLATING
    assert env.orch.resume_incomplete() == []  # TRANSLATING has no stage here: nothing to resume

    env.orch.retry(cancelled.job_id, None, None)
    assert (await env.orch.wait(cancelled.job_id)).status == TranslationStatus.TRANSLATING


# ── API ───────────────────────────────────────────────────────────────


@pytest.fixture
def api(tpl, tmp_path, request):  # noqa: F811
    env = _env(tmp_path, tpl, getattr(request, "param", None))
    seed_users(env.e.store.db_path, "reviewer-1")
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(translations.router)
    app.dependency_overrides[get_settings] = lambda: env.settings
    app.dependency_overrides[require_user] = lambda: {"userId": "reviewer-1"}
    app.state.translation_orchestrator = env.orch
    app.state.glossary_store = env.glossaries
    app.state.language_template_store = env.templates
    with TestClient(app) as client:
        env.client = client
        yield env
        client.portal.call(env.orch.stop)


def _wait_status(client, job_id: str, status: str, timeout: float = 60) -> dict:
    deadline = time.monotonic() + timeout
    while True:
        job = client.get(f"/api/v1/translations/{job_id}").json()
        if job["status"] == status or time.monotonic() > deadline:
            return job
        time.sleep(0.1)


def test_api_starts_one_job_per_language_and_serves_its_segments(api, tmp_path):
    client, base = api.client, "/api/v1/translations"
    _glossary(api)
    _template(api, tmp_path, "fr-FR", "t-fr")
    created = client.post(base, json={"migration_job_id": api.migration.job_id, "languages": [
        {"language": "de-DE", "glossary_id": "g-de"},
        {"language": "fr-FR", "language_template_id": "t-fr"},
    ]})
    assert created.status_code == 200, created.text
    de, fr = created.json()
    assert (de["language"], de["glossary_id"], de["glossary_version"]) == ("de-DE", "g-de", 1)
    assert (fr["language"], fr["language_template_id"], fr.get("glossary_id")) == ("fr-FR", "t-fr", None)
    assert de["created_by"] == "reviewer-1"

    for job in (de, fr):
        assert _wait_status(client, job["job_id"], "TRANSLATING")["status"] == "TRANSLATING"
    listed = client.get(base, params={"migration_job_id": api.migration.job_id}).json()
    assert {j["job_id"] for j in listed} == {de["job_id"], fr["job_id"]}
    assert [j["job_id"] for j in client.get(base, params={"language": "fr-FR"}).json()] == [fr["job_id"]]

    every = client.get(f"{base}/{de['job_id']}/segments").json()
    assert every["counts"]["claim"] > 0 and "template" in every["scopes"]
    template = client.get(f"{base}/{de['job_id']}/segments", params={"section": "template"}).json()["segments"]
    assert template and {s["kind"] for s in template} == {"template_text"}
    section = client.get(f"{base}/{de['job_id']}/segments", params={"section": "TGT-3"}).json()["segments"]
    assert {s["kind"] for s in section} == {"table_header", "table_cell"}
    assert all("target_text" not in s for s in every["segments"])  # not translated yet
    unchecked = client.get(f"{base}/{de['job_id']}/validation")
    assert unchecked.status_code == 404 and unchecked.json()["error"]["code"] == "NO_VALIDATION"
    audit = [e["event"] for e in client.get(f"{base}/{de['job_id']}/audit").json()]
    assert audit[0] == "created" and "segments" in audit and "glossary" in audit

    # The resources a job uses cannot be deleted; the static routes still match before /{job_id}.
    blocked = client.delete(f"{base}/glossaries/g-de")
    assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "RECORD_IN_USE"
    assert client.get(f"{base}/languages").status_code == 200
    assert client.get(f"{base}/glossaries").status_code == 200
    assert client.get(f"{base}/language-templates").status_code == 200

    retried = client.post(f"{base}/{fr['job_id']}/retry")
    assert retried.status_code == 409 and retried.json()["error"]["code"] == "NOT_RETRYABLE"
    cancelled = client.post(f"{base}/{fr['job_id']}/cancel")
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"


def _fake_translator():
    return FakeFactory(TranslatorOutput=FakeChain(translating(lambda key, text, repair: f"DE {text}")))


@pytest.mark.parametrize("api", [_fake_translator()], indirect=True)
def test_api_serves_the_translations_and_their_checks(api):
    client, base = api.client, "/api/v1/translations"
    created = client.post(base, json={"migration_job_id": api.migration.job_id, "languages": [{"language": "de-DE"}]})
    job = created.json()[0]
    assert _wait_status(client, job["job_id"], "REVIEW_PENDING")["status"] == "REVIEW_PENDING"

    segments = client.get(f"{base}/{job['job_id']}/segments", params={"section": "TGT-3"}).json()["segments"]
    assert segments and all(s["target_text"] in (f"DE {s['source_text']}", s["source_text"]) for s in segments)
    assert {s["origin"] for s in segments} <= {"llm", "copied"}
    report = client.get(f"{base}/{job['job_id']}/validation")
    assert report.status_code == 200 and report.json()["version"] == 1 and report.json()["unit_coverage"] == 1.0


def test_api_refuses_a_request_it_cannot_start(api, tmp_path):
    client, base = api.client, "/api/v1/translations"
    mig = api.migration.job_id
    _glossary(api, glossary_id="draft-de", approve=False)
    _template(api, tmp_path, "fr-FR", "t-fr")

    def code(body: dict) -> tuple[int, str]:
        response = client.post(base, json=body)
        return response.status_code, response.json()["error"]["code"]

    assert code({"migration_job_id": "MIG-NOPE", "languages": [{"language": "de-DE"}]}) == (404, "MIGRATION_NOT_FOUND")
    assert code({"migration_job_id": mig, "languages": []}) == (422, "NO_LANGUAGES")
    assert code({"migration_job_id": mig, "languages": [{"language": "xx"}]}) == (422, "UNSUPPORTED_LANGUAGE")
    assert code({"migration_job_id": mig, "languages": [{"language": "de-DE"}, {"language": "de-DE"}]}) == (
        422, "DUPLICATE_LANGUAGE")
    assert code({"migration_job_id": mig, "languages": [{"language": "de-DE", "glossary_id": "draft-de"}]}) == (
        409, "GLOSSARY_NOT_APPROVED")
    assert code({"migration_job_id": mig, "languages": [{"language": "de-DE", "glossary_id": "nope"}]}) == (
        404, "GLOSSARY_NOT_FOUND")
    assert code({"migration_job_id": mig, "languages": [{"language": "de-DE", "language_template_id": "t-fr"}]}) == (
        422, "LANGUAGE_TEMPLATE_LANGUAGE_MISMATCH")
    assert code({"migration_job_id": mig, "languages": [{"language": "de-DE", "glossary_version": 1}]}) == (
        422, "GLOSSARY_ID_REQUIRED")
    # A refused language refuses the whole request: no job was created.
    assert code({"migration_job_id": mig, "languages": [{"language": "fr-FR"}, {"language": "de-DE",
                                                                               "glossary_id": "draft-de"}]}) == (
        409, "GLOSSARY_NOT_APPROVED")
    assert client.get(base).json() == []

    api.e.store.set_status(mig, JobStatus.HUMAN_REVIEW_REQUIRED, "system")
    assert code({"migration_job_id": mig, "languages": [{"language": "de-DE"}]}) == (409, "MIGRATION_NOT_COMPLETED")
    missing = client.get(f"{base}/TRN-20260101-NOPE")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "TRANSLATION_NOT_FOUND"
