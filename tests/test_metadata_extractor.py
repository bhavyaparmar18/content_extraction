"""Unit tests for SOP metadata extraction, ID generation, and upload counter."""

import os
from pathlib import Path
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


def test_record_upload_and_counter(tmp_path, monkeypatch):
    test_reg = tmp_path / "upload_counters.json"
    monkeypatch.setattr(SOPMetadataExtractor, "REGISTRY_PATH", test_reg)

    doc_id = "SOP-001_Test_Doc_v1.0"
    assert SOPMetadataExtractor.get_upload_count(doc_id) == 0

    already, count = SOPMetadataExtractor.record_upload(doc_id)
    assert already is False
    assert count == 1
    assert SOPMetadataExtractor.get_upload_count(doc_id) == 1

    already2, count2 = SOPMetadataExtractor.record_upload(doc_id)
    assert already2 is True
    assert count2 == 2
    assert SOPMetadataExtractor.get_upload_count(doc_id) == 2
