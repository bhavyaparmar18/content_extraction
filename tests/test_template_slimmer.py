"""Tests for TemplateSlimmer service and slim migration profile generation."""

import json
from pathlib import Path
import pytest

from app.services.migration.schemas import SlimTemplateProfile
from app.services.migration.template_slimmer import (
    get_slim_profile_path,
    save_slim_template_profile,
    slim_template_profile,
)


@pytest.fixture
def sample_full_template_dict():
    """Synthetic full extraction JSON with bloated fields that should be stripped."""
    return {
        "version": "2.0",
        "template_id": "TPL_TEST_001",
        "template_name": "Test Template",
        "metadata": {
            "template_id": "TPL_TEST_001",
            "template_name": "Test Template",
            "author": "Alice",
            "creation_date": "2026-01-01T00:00:00Z",
            "file_size_bytes": 50000,
        },
        "icon_library": [
            {
                "icon_key": "icon_1",
                "asset_path": "data/icons/icon_1.png",
                "allowed_sections": ["PURPOSE"],
            }
        ],
        "callout_styles": [
            {"style_name": "Note", "fill_hex": "E6F0FA", "border_hex": "0075FF"}
        ],
        "global_rules": {
            "instructions": [
                {
                    "instruction_id": "gr_001",
                    "text": "Follow blue text.",
                    "scope": "global",
                    "directive_type": "requirement",
                    "paragraph_index": 1,
                    "is_global": True,
                    "font_color_hex": "0075FF",
                    "color_detection_method": "run_color",
                },
                {
                    "instruction_id": "gr_002",
                    "text": "Do not alter styles.",
                    "scope": "global",
                    "directive_type": "prohibition",
                },
            ]
        },
        "sections": [
            {
                "section_number": "1",
                "title": "PURPOSE",
                "required": True,
                "skeleton_elements": [
                    {
                        "type": "heading",
                        "text": "1. PURPOSE",
                        "font_color_hex": "000000",
                    }
                ],
                "authoring_instructions": [
                    {
                        "instruction_id": "s1_i001",
                        "text": "Describe the scope and objective.",
                        "scope": "section",
                        "directive_type": "guidance",
                        "paragraph_index": 5,
                        "font_color_hex": "0075FF",
                    }
                ],
            },
            {
                "section_number": "2",
                "title": "OPTIONAL APPENDIX",
                "required": False,
                "skeleton_elements": [],
                "authoring_instructions": [],
            },
        ],
        "totals": {
            "sections": 2,
            "elements": 1,
            "instructions": 3,
            "icons": 1,
            "callouts": 1,
        },
    }


def test_get_slim_profile_path():
    path = Path("data/template_output/Template_Main_GP_Docs_v1.json")
    slim_path = get_slim_profile_path(path)
    assert slim_path == Path("data/template_output/Template_Main_GP_Docs_v1_migration.json")

    str_path = "data/output/some_template.json"
    assert get_slim_profile_path(str_path) == Path("data/output/some_template_migration.json")


def test_slim_template_profile_dict(sample_full_template_dict):
    slim = slim_template_profile(sample_full_template_dict)

    # Top level checks
    assert slim["template_id"] == "TPL_TEST_001"
    assert slim["template_name"] == "Test Template"
    assert "metadata" not in slim
    assert "icon_library" not in slim
    assert "callout_styles" not in slim
    assert "totals" not in slim

    # Global instructions
    assert len(slim["global_instructions"]) == 2
    assert slim["global_instructions"][0] == {
        "text": "Follow blue text.",
        "directive_type": "requirement",
    }
    assert slim["global_instructions"][1] == {
        "text": "Do not alter styles.",
        "directive_type": "prohibition",
    }
    # Check no extra keys in instructions
    for gi in slim["global_instructions"]:
        assert set(gi.keys()) == {"text", "directive_type"}

    # Sections
    assert len(slim["sections"]) == 2
    s1 = slim["sections"][0]
    assert s1["section_number"] == "1"
    assert s1["section_name"] == "PURPOSE"
    assert s1["required"] is True
    assert "skeleton_elements" not in s1
    assert len(s1["instructions"]) == 1
    assert s1["instructions"][0] == {
        "text": "Describe the scope and objective.",
        "directive_type": "guidance",
    }
    assert set(s1.keys()) == {"section_number", "section_name", "required", "instructions"}

    # Section 2 (optional, empty instructions)
    s2 = slim["sections"][1]
    assert s2["section_number"] == "2"
    assert s2["section_name"] == "OPTIONAL APPENDIX"
    assert s2["required"] is False
    assert s2["instructions"] == []

    # Validates with Pydantic model
    validated = SlimTemplateProfile.model_validate(slim)
    assert validated.template_id == "TPL_TEST_001"


def test_slim_template_profile_from_file(tmp_path, sample_full_template_dict):
    src_file = tmp_path / "test_template_v1.json"
    with open(src_file, "w", encoding="utf-8") as f:
        json.dump(sample_full_template_dict, f)

    slim = slim_template_profile(src_file)
    assert slim["template_id"] == "TPL_TEST_001"
    assert len(slim["sections"]) == 2


def test_save_slim_template_profile_auto_path(tmp_path, sample_full_template_dict):
    src_file = tmp_path / "test_tpl_v2.json"
    with open(src_file, "w", encoding="utf-8") as f:
        json.dump(sample_full_template_dict, f)

    saved_path = save_slim_template_profile(src_file)
    expected_path = tmp_path / "test_tpl_v2_migration.json"
    assert saved_path == expected_path
    assert saved_path.exists()

    with open(saved_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["template_id"] == "TPL_TEST_001"
    assert len(data["global_instructions"]) == 2


def test_save_slim_template_profile_explicit_path(tmp_path, sample_full_template_dict):
    dst_file = tmp_path / "custom" / "target_migration.json"
    saved = save_slim_template_profile(sample_full_template_dict, output_path=dst_file)

    assert saved == dst_file
    assert dst_file.exists()


def test_slim_template_profile_invalid_input():
    with pytest.raises(FileNotFoundError):
        slim_template_profile("non_existent_file_path_12345.json")

    with pytest.raises(TypeError):
        slim_template_profile(12345)


def test_real_template_main_gp_docs():
    """Verify on real data/template_output/Template_Main_GP_Docs_v1.json if it exists."""
    real_path = Path("data/template_output/Template_Main_GP_Docs_v1.json")
    if not real_path.exists():
        pytest.skip("Template_Main_GP_Docs_v1.json not present in repository")

    slim = slim_template_profile(real_path)

    assert slim["template_id"] == "Template_Main_GP_Docs"
    assert slim["template_name"] == "Template Main GP Docs"
    assert len(slim["global_instructions"]) == 13
    assert len(slim["sections"]) == 11

    # Check section numbers & names match
    titles = [s["section_name"] for s in slim["sections"]]
    assert "PURPOSE" in titles
    assert "APPLICABILITY" in titles
    assert "DOCUMENT HISTORY" in titles

    # Check the migration output file exists and is valid
    migration_path = Path("data/template_output/Template_Main_GP_Docs_v1_migration.json")
    assert migration_path.exists()

    with open(migration_path, "r", encoding="utf-8") as f:
        mig_data = json.load(f)

    profile = SlimTemplateProfile.model_validate(mig_data)
    assert profile.template_id == "Template_Main_GP_Docs"
    assert len(profile.sections) == 11
