"""Unit tests for SOP metadata extraction and ID generation."""

import pytest

from app.services.extraction.metadata_extractor import SOPMetadataExtractor


def test_sanitize_string():
    assert SOPMetadataExtractor.sanitize_string("SOP-101/A") == "SOP-101_A"
    assert SOPMetadataExtractor.sanitize_string("  Safety & Hazard  ") == "Safety_Hazard"
    assert SOPMetadataExtractor.sanitize_string("v2.1.0") == "v2.1.0"


def test_generate_document_id():
    doc_id = SOPMetadataExtractor.generate_document_id(
        doc_name="Chemical Handling Procedure",
        doc_number="SOP-CH-001",
        doc_version="2.0",
    )
    assert doc_id == "SOP-CH-001_Chemical_Handling_Procedure_v2.0"

    # Test fallback when fields are missing
    doc_id_fallback = SOPMetadataExtractor.generate_document_id(
        doc_name="",
        doc_number="",
        doc_version="",
        fallback_filename="safety_guidelines.pdf",
    )
    assert doc_id_fallback == "DOC_safety_guidelines_v1.0"


def test_clean_cell_value_strips_watermark_fragments():
    dirty = "o\nBI-VQD-24416"
    assert SOPMetadataExtractor._clean_cell_value(dirty) == "BI-VQD-24416"
    assert SOPMetadataExtractor._clean_cell_value("y\np\nBI-VQD-24416-G") == "BI-VQD-24416-G"
    assert SOPMetadataExtractor._clean_cell_value("3.0") == "3.0"


def test_matches_uses_word_boundaries():
    assert SOPMetadataExtractor._matches("version", SOPMetadataExtractor._VERSION_KEYS)
    assert not SOPMetadataExtractor._matches("reviewer", SOPMetadataExtractor._VERSION_KEYS)
    assert SOPMetadataExtractor._matches("document id", SOPMetadataExtractor._NUMBER_KEYS)
    assert SOPMetadataExtractor._matches("title", SOPMetadataExtractor._TITLE_KEYS)
    assert not SOPMetadataExtractor._matches("title", SOPMetadataExtractor._NAME_KEYS)


def test_classify_row_splits_title_and_name():
    values = {"title": "", "name": "", "number": "", "version": "", "type": ""}
    SOPMetadataExtractor._classify_row(["Title", "Good Writing Practice"], values)
    SOPMetadataExtractor._classify_row(["Document Name", "BI-VQD-24416-G"], values)
    SOPMetadataExtractor._classify_row(["Document Number", "o\nBI-VQD-24416"], values)
    SOPMetadataExtractor._classify_row(["Version", "3.0"], values)
    assert values["title"] == "Good Writing Practice"
    assert values["name"] == "BI-VQD-24416-G"
    assert values["number"] == "BI-VQD-24416"
    assert values["version"] == "3.0"


def test_classify_row_document_id_fills_number():
    values = {"title": "", "name": "", "number": "", "version": "", "type": ""}
    SOPMetadataExtractor._classify_row(["Document ID", "028-OCS-00443"], values)
    assert values["number"] == "028-OCS-00443"


def test_row_pairs_splits_packed_label_value():
    pairs = SOPMetadataExtractor._row_pairs(
        ["Document ID", "SOP-1", "Version: 2.0"]
    )
    assert pairs == [("Document ID", "SOP-1"), ("Version", "2.0")]
