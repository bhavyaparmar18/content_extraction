"""Tests for Template Management System — Parser, Store, Extractor, and API Endpoints."""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.main import app
from app.services.parser.template_parser import TemplateDocxParser
from app.services.extraction.template_extractor import TemplateExtractionService
from app.stores.template_store import TemplateStore


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_template_path():
    path = Path("data/templates/upload_Template Main GP Docs.docx")
    if not path.exists():
        pytest.skip("Sample template not found at data/templates/upload_Template Main GP Docs.docx")
    return path


def test_template_parser_parsing(sample_template_path):
    settings = Settings()
    parser = TemplateDocxParser(settings=settings)
    raw_doc = parser.parse(str(sample_template_path), template_id="test_tpl")

    assert raw_doc is not None
    assert len(raw_doc.pages) > 0

    all_elements = [el for page in raw_doc.pages for el in page.elements]
    assert len(all_elements) > 0

    # Verify that some elements are tagged as instructions if blue font exists
    instructions = [
        el for el in all_elements
        if getattr(el, "metadata", {}).get("is_instruction") or getattr(el, "highlight_color", None)
    ]
    assert len(instructions) > 0, "Expected to detect blue instruction elements in sample template"


@pytest.mark.asyncio
async def test_template_extractor_service(sample_template_path):
    settings = Settings()
    service = TemplateExtractionService(settings=settings)
    output = await service.extract("test_tpl", sample_template_path, template_name="Template Main GP Docs")

    assert output is not None
    assert output.template_id == "test_tpl"
    assert len(output.sections) == 11, f"Expected 11 sections, got {len(output.sections)}"
    assert len(output.global_rules.instructions) == 13, f"Expected 13 global rules, got {len(output.global_rules.instructions)}"
    assert output.total_instructions == 106
    assert output.total_icons == 14

    # Ensure sections have elements and section-wise instructions with icons
    sec_map = {s.title: s for s in output.sections}
    assert "PURPOSE" in sec_map
    assert sec_map["PURPOSE"].section_number == "1"
    assert len(sec_map["PURPOSE"].instructions) == 3
    assert sec_map["PURPOSE"].instructions[0].section_context == "PURPOSE"
    purpose_icon_instructions = [i for i in sec_map["PURPOSE"].instructions if i.icons]
    assert len(purpose_icon_instructions) == 2
    # Verify instruction text is not duplicated within itself
    assert "Brief description of what the document is about? What process is described in the document? Brief description" not in purpose_icon_instructions[0].text
    # Verify layout container unwrapped into paragraphs, no table
    purpose_tables = [e for e in sec_map["PURPOSE"].elements if e.element_type == "table"]
    assert len(purpose_tables) == 0, "PURPOSE layout container should be unwrapped, 0 tables expected"

    assert "APPLICABILITY" in sec_map
    assert sec_map["APPLICABILITY"].section_number == "2"
    assert len(sec_map["APPLICABILITY"].instructions) == 8
    applicability_icon_instructions = [i for i in sec_map["APPLICABILITY"].instructions if i.icons]
    assert len(applicability_icon_instructions) == 4
    # Verify layout container unwrapped into paragraphs, no table
    applicability_tables = [e for e in sec_map["APPLICABILITY"].elements if e.element_type == "table"]
    assert len(applicability_tables) == 0, "APPLICABILITY layout container should be unwrapped, 0 tables expected"

    assert "PROCESS" in sec_map
    assert sec_map["PROCESS"].section_number == "6"
    assert len(sec_map["PROCESS"].instructions) == 26
    process_icon_instructions = [i for i in sec_map["PROCESS"].instructions if i.icons]
    assert len(process_icon_instructions) == 4
    # Verify callout tables unwrapped
    process_tables = [e for e in sec_map["PROCESS"].elements if e.element_type == "table"]
    assert len(process_tables) == 0, "PROCESS callout tables should be unwrapped, 0 tables expected"

    assert "REFERENCES" in sec_map
    assert sec_map["REFERENCES"].section_number == "8"
    assert len(sec_map["REFERENCES"].instructions) == 9

    assert "DOCUMENT HISTORY" in sec_map
    doc_history = sec_map["DOCUMENT HISTORY"]
    assert sum(len(elem.icons) for elem in doc_history.elements) == 0
    assert sum(len(inst.icons) for inst in doc_history.instructions) == 0

    # Ensure clean dictionary serializes correctly
    clean_dict = output.to_clean_dict()
    assert "sections" in clean_dict
    assert "global_rules" in clean_dict
    assert len(clean_dict["sections"]) == 11
    assert len(clean_dict["global_rules"]["instructions"]) == 13


def test_template_store(tmp_path):
    settings = Settings()
    db_path = tmp_path / "test_tpl_store.db"
    store = TemplateStore(db_path, settings)

    # Test version 1
    rec1 = store.upsert_record(
        template_uid="my_tpl",
        template_name="My Template",
        file_size_bytes=1024,
        source_filename="my_tpl.docx",
        upload_path="/tmp/my_tpl_v1.docx",
    )
    assert rec1["template_uid"] == "my_tpl"
    assert rec1["template_version"] == 1
    assert rec1["status"] == "uploaded"

    # Test version 2
    rec2 = store.upsert_record(
        template_uid="my_tpl",
        template_name="My Template",
        file_size_bytes=2048,
        source_filename="my_tpl.docx",
        upload_path="/tmp/my_tpl_v2.docx",
    )
    assert rec2["template_version"] == 2

    # Test get_records
    records = store.get_records()
    assert len(records) == 2

    # Test update_extraction_results
    updated = store.update_extraction_results(
        record_id=rec2["id"],
        output_path="/tmp/my_tpl_v2.json",
        total_sections=5,
        total_elements=25,
        total_instructions=8,
        total_icons=3,
        global_rules_json=json.dumps({"instructions": []}),
        status="ready",
    )
    assert updated["status"] == "ready"
    assert updated["total_sections"] == 5
    assert updated["total_instructions"] == 8

    # Test get_all_ready_templates
    ready = store.get_all_ready_templates()
    assert len(ready) == 1
    assert ready[0]["id"] == rec2["id"]

    # Test delete
    deleted = store.delete_record(rec1["id"])
    assert deleted is True
    assert len(store.get_records()) == 1


def test_template_api_endpoints(client, sample_template_path):
    # 1. Upload
    with open(sample_template_path, "rb") as f:
        response = client.post(
            "/templates/upload",
            files={"file": ("test_api_template.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={"template_name": "API Test Template"},
        )
    assert response.status_code == 200
    upload_data = response.json()
    assert upload_data["template_id"] == "test_api_template"
    assert upload_data["template_version"] >= 1

    # 2. Extract
    extract_resp = client.post(f"/templates/{upload_data['template_id']}/extract")
    assert extract_resp.status_code == 200
    ext_data = extract_resp.json()
    assert ext_data["status"] == "ready"
    assert ext_data["total_sections"] > 0
    assert ext_data["total_instructions"] > 0

    # 3. List
    list_resp = client.get("/templates")
    assert list_resp.status_code == 200
    templates = list_resp.json()
    assert any(t["template_uid"] == "test_api_template" for t in templates)

    # 4. Get Content
    content_resp = client.get(f"/templates/{upload_data['template_id']}/content")
    assert content_resp.status_code == 200
    content_data = content_resp.json()
    assert "sections" in content_data
    assert "global_rules" in content_data

    # 5. Get Global Rules
    rules_resp = client.get(f"/templates/{upload_data['template_id']}/global-rules")
    assert rules_resp.status_code == 200
    rules_data = rules_resp.json()
    assert "instructions" in rules_data

    # 6. Delete
    del_resp = client.delete(f"/templates/{upload_data['template_id']}")
    assert del_resp.status_code == 200
    assert del_resp.json()["deleted"] is True
