"""The extraction job writes the v2 SourceDocument next to the v3.1 output (Phase 2b)."""

import json

import pytest
from docx import Document

from app.config.settings import Settings
from app.schemas.jobs import JobStatus
from app.schemas.v2 import SourceDocument
from app.services.job_manager import JobManager
from app.stores.sop_store import SopStore


@pytest.fixture
def settings(tmp_path):
    s = Settings(project_root=tmp_path)
    s.resolve_paths(tmp_path)
    s.ensure_directories()
    return s


@pytest.mark.asyncio
async def test_job_writes_versioned_units_and_records_path(settings, tmp_path):
    doc = Document()
    doc.add_heading("1 PURPOSE", level=1)
    doc.add_paragraph("This SOP describes sample handling.")
    doc.add_heading("2 PROCESS", level=1)
    doc.add_paragraph("Submit the record as described in chapter 1.")
    doc.save(settings.upload_dir / "units_job_doc.docx")

    store = SopStore(tmp_path / "sop_records.db", settings)
    manager = JobManager(settings, concurrency=1, sop_store=store)
    job = manager.create_batch_job(["units_job_doc"])
    await manager._process_document(job.job_id, "units_job_doc")

    assert job.documents[0].status == JobStatus.COMPLETED, job.documents[0].error
    (record,) = store.get_records()
    assert record["units_path"]
    units_file = settings.output_dir / f"units_job_doc_v{record['gpdat_version']}_units.json"
    assert record["units_path"] == str(units_file)
    source = SourceDocument.model_validate(json.loads(units_file.read_text(encoding="utf-8")))
    assert [s.heading for s in source.sections] == ["PURPOSE", "PROCESS"]
    assert source.cross_references[0].target == "SRC-1"
    assert (settings.output_dir / "units_job_doc_v2.json").exists()  # v3.1 output unchanged

