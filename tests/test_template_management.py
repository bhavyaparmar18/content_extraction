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
        if getattr(el, "metadata", {}).get("is_instruction")
        or getattr(el, "color_detection_method", None)
    ]
    assert len(instructions) > 0, "Expected to detect blue instruction elements in sample template"


@pytest.mark.asyncio
async def test_template_extractor_service(sample_template_path):
    settings = Settings()
    service = TemplateExtractionService(settings=settings)
    output = await service.extract("test_tpl", sample_template_path, template_name="Template Main GP Docs")

    assert output is not None
    assert output.version == "2.0"
    assert output.template_id == "test_tpl"
    assert len(output.sections) == 11, f"Expected 11 sections, got {len(output.sections)}"
    assert len(output.global_rules.instructions) == 13, f"Expected 13 global rules, got {len(output.global_rules.instructions)}"

    # Every blue instruction lands in exactly one bucket: global rules or a section
    assert output.totals.instructions == 106
    assert output.totals.instructions == len(output.global_rules.instructions) + sum(
        len(s.authoring_instructions) for s in output.sections
    )

    # The icon library is deduplicated; the 14 occurrences collapse into fewer entries
    icon_keys = [entry.icon_key for entry in output.icon_library]
    assert len(icon_keys) == len(set(icon_keys)), "icon_library must be deduplicated"
    assert output.totals.icons == len(output.icon_library)
    assert sum(entry.occurrences for entry in output.icon_library) == 14
    assert any(entry.occurrences > 1 for entry in output.icon_library), "expected reused icons"

    # Ensure sections have elements and section-wise instructions with icons
    sec_map = {s.title: s for s in output.sections}
    assert "PURPOSE" in sec_map
    assert sec_map["PURPOSE"].section_number == "1"
    assert len(sec_map["PURPOSE"].authoring_instructions) == 3
    assert sec_map["PURPOSE"].authoring_instructions[0].section_context == "PURPOSE"
    assert all(i.scope == "section" for i in sec_map["PURPOSE"].authoring_instructions)
    purpose_icon_instructions = [i for i in sec_map["PURPOSE"].authoring_instructions if i.icons]
    assert len(purpose_icon_instructions) == 2
    # Verify instruction text is not duplicated within itself
    assert "Brief description of what the document is about? What process is described in the document? Brief description" not in purpose_icon_instructions[0].text
    # Verify unshaded layout container unwrapped into paragraphs, no table
    purpose_tables = [e for e in sec_map["PURPOSE"].skeleton_elements if e.element_type == "table"]
    assert len(purpose_tables) == 0, "PURPOSE layout container should be unwrapped, 0 tables expected"

    assert "APPLICABILITY" in sec_map
    assert sec_map["APPLICABILITY"].section_number == "2"
    assert len(sec_map["APPLICABILITY"].authoring_instructions) == 8
    applicability_icon_instructions = [i for i in sec_map["APPLICABILITY"].authoring_instructions if i.icons]
    assert len(applicability_icon_instructions) == 4
    # Verify unshaded layout container unwrapped into paragraphs, no table
    applicability_tables = [e for e in sec_map["APPLICABILITY"].skeleton_elements if e.element_type == "table"]
    assert len(applicability_tables) == 0, "APPLICABILITY layout container should be unwrapped, 0 tables expected"

    assert "PROCESS" in sec_map
    assert sec_map["PROCESS"].section_number == "6"
    assert len(sec_map["PROCESS"].authoring_instructions) == 26
    process_icon_instructions = [i for i in sec_map["PROCESS"].authoring_instructions if i.icons]
    assert len(process_icon_instructions) == 4
    # Shaded infographic boxes survive as callouts rather than being flattened away
    process_tables = [e for e in sec_map["PROCESS"].skeleton_elements if e.element_type == "table"]
    assert len(process_tables) == 0, "PROCESS layout containers should be unwrapped, 0 tables expected"

    assert "REFERENCES" in sec_map
    assert sec_map["REFERENCES"].section_number == "8"
    assert len(sec_map["REFERENCES"].authoring_instructions) == 9

    assert "DOCUMENT HISTORY" in sec_map
    doc_history = sec_map["DOCUMENT HISTORY"]
    assert sum(len(elem.icons) for elem in doc_history.skeleton_elements) == 0
    assert sum(len(inst.icons) for inst in doc_history.authoring_instructions) == 0

    # Callout registry is populated from the template's own colours
    assert output.totals.callouts == sum(
        1
        for s in output.sections
        for e in s.skeleton_elements
        if e.element_type == "callout"
    )
    for style in output.callout_styles:
        assert style.background_color_hex, "callout colours must come from the template"
        assert style.icon_key is None or style.icon_key in set(icon_keys)

    # Ensure clean dictionary serializes correctly
    clean_dict = output.to_clean_dict()
    assert "sections" in clean_dict
    assert "global_rules" in clean_dict
    assert len(clean_dict["sections"]) == 11
    assert len(clean_dict["global_rules"]["instructions"]) == 13

    # Output must be portable and free of the old sentinel
    blob = json.dumps(clean_dict)
    assert "STYLE_INSTRUCTION" not in blob
    for entry in clean_dict["icon_library"]:
        assert not Path(entry["asset_path"]).is_absolute()


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
        total_callouts=4,
        global_rules_json=json.dumps({"instructions": []}),
        status="ready",
    )
    assert updated["status"] == "ready"
    assert updated["total_sections"] == 5
    assert updated["total_instructions"] == 8
    assert updated["total_callouts"] == 4

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
    assert ext_data["total_callouts"] >= 0

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
