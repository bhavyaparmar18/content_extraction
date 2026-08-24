"""SOP Metadata Extractor.

Extracts Document Name, Document Number, and Version from the first page table
(or header text) of an SOP document before full pipeline extraction.
Generates a deterministic document_id and tracks duplicate upload counts.
"""

import json
import re
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF
import pdfplumber
import docx
from loguru import logger

from app.config.settings import Settings


class SOPMetadataExtractor:
    """Service to extract SOP identification metadata from first page tables."""

    REGISTRY_PATH = Path("data/config/upload_counters.json")

    @classmethod
    def _ensure_registry_dir(cls) -> None:
        cls.REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not cls.REGISTRY_PATH.exists():
            cls.REGISTRY_PATH.write_text("{}", encoding="utf-8")

    @classmethod
    def get_upload_count(cls, document_id: str) -> int:
        """Return the number of times this document_id has been uploaded."""
        cls._ensure_registry_dir()
        try:
            data = json.loads(cls.REGISTRY_PATH.read_text(encoding="utf-8"))
            return int(data.get(document_id, 0))
        except Exception as e:  # noqa: BLE001
            logger.debug("Upload counter read failed ({e}); assuming 0.", e=e)
            return 0

    @classmethod
    def record_upload(cls, document_id: str) -> tuple[bool, int]:
        """Record an upload attempt for a document_id.

        Returns:
            (already_uploaded, duplicate_upload_count)
        """
        cls._ensure_registry_dir()
        try:
            data = json.loads(cls.REGISTRY_PATH.read_text(encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            logger.debug("Upload counter read failed ({e}); starting fresh.", e=e)
            data = {}

        prev_count = int(data.get(document_id, 0))
        already_uploaded = prev_count > 0
        new_count = prev_count + 1
        data[document_id] = new_count

        try:
            cls.REGISTRY_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as e:  # noqa: BLE001
            logger.warning("Failed to persist upload counter for '{d}': {e}", d=document_id, e=e)

        return already_uploaded, new_count

    @classmethod
    def sanitize_string(cls, val: str) -> str:
        """Sanitize a string to alphanumeric, hyphen, underscore, or dot."""
        if not val:
            return ""
        clean = re.sub(r"[^A-Za-z0-9_\-.]", "_", val.strip())
        clean = re.sub(r"_+", "_", clean)
        return clean.strip("_")

    @classmethod
    def generate_document_id(
        cls,
        doc_name: str,
        doc_number: str,
        doc_version: str,
        fallback_filename: str = "",
    ) -> str:
        """Generate a deterministic document ID from SOP metadata fields."""
        clean_num = cls.sanitize_string(doc_number)
        clean_name = cls.sanitize_string(doc_name)
        clean_ver = cls.sanitize_string(doc_version)

        if not clean_name and fallback_filename:
            stem = Path(fallback_filename).stem
            clean_name = cls.sanitize_string(stem)

        if not clean_num:
            clean_num = "DOC"
        if not clean_name:
            clean_name = "UNKNOWN"
        if not clean_ver:
            clean_ver = "1.0"

        doc_id = f"{clean_num}_{clean_name}_v{clean_ver}"
        return doc_id

    @classmethod
    def extract_from_file(
        cls,
        file_path: str,
        fallback_filename: str = "",
    ) -> tuple[str, str, str, str]:
        """Extract (document_name, document_number, document_version, document_type) from file.

        Args:
            file_path: Absolute path to the PDF or DOCX file.
            fallback_filename: Original filename if file_path is temporary.

        Returns:
            Tuple of (document_name, document_number, document_version, document_type).
            ``document_type`` is the Type/Subtype value from the preamble table
            (e.g. "Governance and Procedure > Guidance").
        """
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext == ".pdf":
            return cls._extract_from_pdf(path)
        elif ext == ".docx":
            return cls._extract_from_docx(path)
        else:
            return "", "", "", ""

    @classmethod
    def _extract_from_pdf(cls, file_path: Path) -> tuple[str, str, str, str]:
        doc_name = ""
        doc_number = ""
        doc_version = ""
        doc_type = ""

        # 1. Try checking first-page tables via pdfplumber
        try:
            with pdfplumber.open(file_path) as pdf:
                if len(pdf.pages) > 0:
                    page0 = pdf.pages[0]
                    tables = page0.extract_tables()
                    for table in tables:
                        for row in table:
                            if not row or len(row) < 2:
                                continue
                            key = str(row[0] or "").strip().lower()
                            val = str(row[1] or "").strip()

                            if not doc_name and any(
                                k in key
                                for k in [
                                    "document name",
                                    "doc name",
                                    "document title",
                                    "title",
                                ]
                            ):
                                doc_name = val
                            elif not doc_number and any(
                                k in key
                                for k in [
                                    "document number",
                                    "doc number",
                                    "doc no",
                                    "sop number",
                                    "document id",
                                ]
                            ):
                                doc_number = val
                            elif not doc_version and any(
                                k in key
                                for k in [
                                    "version",
                                    "ver",
                                    "rev",
                                    "revision",
                                ]
                            ):
                                doc_version = val
                            elif not doc_type and any(
                                k in key
                                for k in [
                                    "type/subtype",
                                    "type",
                                    "subtype",
                                    "document type",
                                    "doc type",
                                ]
                            ):
                                doc_type = val
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "PDF table metadata extraction failed for '{f}': {e}", f=file_path.name, e=e
            )

        # 2. Try regex fallback on first page text if any is missing
        if not (doc_name and doc_number and doc_version):
            try:
                doc = fitz.open(file_path)
                if len(doc) > 0:
                    text = doc[0].get_text("text")
                    if not doc_number:
                        m = re.search(
                            r"(?i)(?:Document\s*Number|Number):\s*([A-Za-z0-9\-_.]{3,})",
                            text,
                        )
                        if m:
                            doc_number = m.group(1).strip()
                    if not doc_version:
                        m = re.search(
                            r"(?i)(?:Version|Ver|Rev|Revision):\s*([0-9.]+)",
                            text,
                        )
                        if m:
                            doc_version = m.group(1).strip()
                    if not doc_name:
                        m = re.search(
                            r"(?i)(?:Document\s*Name|Title):\s*([^\r\n]+)",
                            text,
                        )
                        if m:
                            doc_name = m.group(1).strip()
                doc.close()
            except Exception as e:  # noqa: BLE001
                logger.warning(
                    "PDF text metadata fallback failed for '{f}': {e}", f=file_path.name, e=e
                )

        return doc_name, doc_number, doc_version, doc_type

    @classmethod
    def _extract_from_docx(cls, file_path: Path) -> tuple[str, str, str, str]:
        doc_name = ""
        doc_number = ""
        doc_version = ""
        doc_type = ""

        try:
            doc = docx.Document(file_path)
            # 1. Scan tables on the document
            for table in doc.tables[:3]:  # Check first few tables
                for row in table.rows:
                    if len(row.cells) >= 2:
                        key = row.cells[0].text.strip().lower()
                        val = row.cells[1].text.strip()
                        if not doc_name and any(
                            k in key
                            for k in [
                                "document name",
                                "doc name",
                                "document title",
                                "title",
                            ]
                        ):
                            doc_name = val
                        elif not doc_number and any(
                            k in key
                            for k in [
                                "document number",
                                "doc number",
                                "doc no",
                                "sop number",
                                "document id",
                            ]
                        ):
                            doc_number = val
                        elif not doc_version and any(
                            k in key
                            for k in [
                                "version",
                                "ver",
                                "rev",
                                "revision",
                            ]
                        ):
                            doc_version = val
                        elif not doc_type and any(
                            k in key
                            for k in [
                                "type/subtype",
                                "type",
                                "subtype",
                                "document type",
                                "doc type",
                            ]
                        ):
                            doc_type = val

            # 2. Regex fallback on first paragraphs
            if not (doc_name and doc_number and doc_version):
                full_text = "\n".join(p.text for p in doc.paragraphs[:20])
                if not doc_number:
                    m = re.search(
                        r"(?i)(?:Document\s*Number|Number):\s*([A-Za-z0-9\-_.]{3,})",
                        full_text,
                    )
                    if m:
                        doc_number = m.group(1).strip()
                if not doc_version:
                    m = re.search(
                        r"(?i)(?:Version|Ver|Rev|Revision):\s*([0-9.]+)",
                        full_text,
                    )
                    if m:
                        doc_version = m.group(1).strip()
                if not doc_name:
                    m = re.search(
                        r"(?i)(?:Document\s*Name|Title):\s*([^\r\n]+)",
                        full_text,
                    )
                    if m:
                        doc_name = m.group(1).strip()
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "DOCX metadata extraction failed for '{f}': {e}", f=file_path.name, e=e
            )

        return doc_name, doc_number, doc_version, doc_type
