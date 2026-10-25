"""Language template versions on disk and in the store: upload with extraction, report, ready.

An upload is the next version of ``template_id``. Its first page, headers and
footers are extracted at once (``front_matter``) into a package, a preview and a
report. The version is ``extracted`` (or ``failed`` when no package could be
made), and an admin marks it ``ready`` after checking the preview. Only ready
versions can be named by a translation job, which snapshots the package.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from loguru import logger

from app.config.settings import Settings
from app.schemas.v2.translation import FrontMatterReport
from app.services.translation.front_matter import FrontMatterError, extract_front_matter, save_report
from app.services.translation.languages import get_language
from app.stores.language_template_store import LanguageTemplateStore


class LanguageTemplateLanguageMismatch(ValueError):
    pass


class LanguageTemplateNotReady(ValueError):
    def __init__(self, reasons: list[str]):
        super().__init__("; ".join(reasons))
        self.reasons = reasons


def output_paths(settings: Settings, template_id: str, version: int) -> dict[str, Path]:
    stem = Path(settings.language_template_dir) / f"{template_id}_v{version}"
    return {"front_matter_path": Path(f"{stem}_front_matter.docx"), "preview_path": Path(f"{stem}_preview.docx"),
            "report_path": Path(f"{stem}_report.json")}


def create_version(
    store: LanguageTemplateStore,
    settings: Settings,
    *,
    template_id: str,
    name: str,
    language: str,
    data: bytes,
    filename: str,
    created_by: Optional[str] = None,
) -> dict[str, Any]:
    """Save the upload as the next version of ``template_id`` and extract its front matter."""
    language = get_language(language).word_lang
    latest = store.get_latest(template_id)
    if latest is not None and latest["language"] != language:
        raise LanguageTemplateLanguageMismatch(
            f"language template {template_id!r} is for {latest['language']}, not {language}")
    version = store.get_next_version(template_id)
    upload = Path(settings.language_template_upload_dir) / f"{template_id}_v{version}.docx"
    upload.parent.mkdir(parents=True, exist_ok=True)
    upload.write_bytes(data)
    record = store.create_record(template_id, name, language, created_by=created_by, file_size_bytes=len(data),
                                 source_filename=filename, upload_path=str(upload))
    return extract(store, settings, record)


def extract(store: LanguageTemplateStore, settings: Settings, record: dict[str, Any]) -> dict[str, Any]:
    paths = output_paths(settings, record["template_id"], record["version"])
    try:
        report = extract_front_matter(
            record["upload_path"], paths["front_matter_path"], paths["preview_path"],
            template_id=record["template_id"], version=record["version"], language=record["language"],
            source_filename=record.get("source_filename"))
    except FrontMatterError as exc:
        return store.update_fields(record["id"], status="failed", error=str(exc))
    except Exception as exc:  # a file python-docx reads but cannot handle
        logger.exception(f"language template {record['template_id']} v{record['version']}: extraction failed")
        return store.update_fields(record["id"], status="failed", error=f"the first page could not be extracted: {exc}")
    save_report(report, paths["report_path"])
    fields: dict[str, Any] = {"report_path": str(paths["report_path"])}
    if paths["front_matter_path"].exists():
        fields.update(status="extracted", error=None, front_matter_path=str(paths["front_matter_path"]),
                      preview_path=str(paths["preview_path"]))
    else:
        fields.update(status="failed", error=report.problems[0] if report.problems else "no front matter")
    return store.update_fields(record["id"], **fields)


def load_report(record: dict[str, Any]) -> FrontMatterReport:
    path = record.get("report_path")
    if not path or not Path(path).exists():
        raise FileNotFoundError(f"language template {record['template_id']} v{record['version']} has no report")
    return FrontMatterReport.model_validate_json(Path(path).read_text(encoding="utf-8"))


def mark_ready(store: LanguageTemplateStore, record: dict[str, Any]) -> dict[str, Any]:
    """An extracted version without problems becomes ready for translation jobs."""
    if record["status"] == "ready":
        return record
    if record["status"] != "extracted":
        raise LanguageTemplateNotReady([f"the version is {record['status']}, not extracted"
                                        + (f": {record['error']}" if record.get("error") else "")])
    if not record.get("front_matter_path") or not Path(record["front_matter_path"]).exists():
        raise LanguageTemplateNotReady(["the extracted front matter file is missing"])
    problems = load_report(record).problems
    if problems:
        raise LanguageTemplateNotReady(problems)
    return store.update_fields(record["id"], status="ready", error=None)
