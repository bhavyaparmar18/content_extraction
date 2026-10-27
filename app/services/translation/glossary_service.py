"""Glossary versions on disk and in the store: create, edit, approve, load.

The Glossary JSON at ``entries_path`` is the source of truth. A version in review
is edited in place; an approved version never changes (a translation job may use
it), so editing it creates the next version, in review again. Only approved
versions can be named by a translation job, which snapshots them.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from app.config.settings import Settings
from app.schemas.v2.translation import Glossary, GlossaryEntry
from app.services.translation.glossary import GlossaryInvalid
from app.services.translation.languages import get_language
from app.stores.glossary_store import GlossaryStore


class GlossaryLanguageMismatch(ValueError):
    pass


def entries_path(settings: Settings, glossary_id: str, version: int) -> Path:
    return Path(settings.glossary_dir) / f"{glossary_id}_v{version}_entries.json"


def build(record: dict[str, Any], entries: list[GlossaryEntry], style_notes: Optional[str]) -> Glossary:
    try:
        return Glossary(glossary_id=record["glossary_id"], version=record["version"], language=record["language"],
                        name=record["name"], entries=entries, style_notes=(style_notes or "").strip() or None)
    except ValueError as exc:  # pydantic's ValidationError is a ValueError
        errors = getattr(exc, "errors", None)
        raise GlossaryInvalid([e["msg"].removeprefix("Value error, ") for e in errors()] if errors else [str(exc)]) \
            from exc


def _write(store: GlossaryStore, settings: Settings, record: dict[str, Any], glossary: Glossary) -> dict[str, Any]:
    path = entries_path(settings, record["glossary_id"], record["version"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(glossary.to_clean_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    return store.update_fields(record["id"], entries_path=str(path), total_entries=len(glossary.entries),
                               status="in_review", name=glossary.name, error=None)


def create_version(
    store: GlossaryStore,
    settings: Settings,
    *,
    glossary_id: str,
    name: str,
    language: str,
    entries: list[GlossaryEntry],
    style_notes: Optional[str] = None,
    created_by: Optional[str] = None,
    upload: Optional[tuple[bytes, str]] = None,
) -> dict[str, Any]:
    """The next version of ``glossary_id`` (a new glossary when it has none), in review.

    The entries are checked before anything is written. ``upload`` is the original file (bytes, file name), kept.
    """
    language = get_language(language).word_lang
    latest = store.get_latest(glossary_id)
    if latest is not None and latest["language"] != language:
        raise GlossaryLanguageMismatch(
            f"glossary {glossary_id!r} is for {latest['language']}, not {language}")
    version = store.get_next_version(glossary_id)
    build({"glossary_id": glossary_id, "version": version, "language": language, "name": name},
          entries, style_notes)  # validate first
    columns: dict[str, Any] = {}
    if upload is not None:
        data, filename = upload
        suffix = Path(filename).suffix.lower()
        save_path = Path(settings.glossary_upload_dir) / f"{glossary_id}_v{version}{suffix}"
        save_path.parent.mkdir(parents=True, exist_ok=True)
        save_path.write_bytes(data)
        columns = {"file_type": suffix.lstrip("."), "file_size_bytes": len(data), "source_filename": filename,
                   "upload_path": str(save_path)}
    record = store.create_record(glossary_id, name, language, created_by=created_by, **columns)
    return _write(store, settings, record, build(record, entries, style_notes))


def load(record: dict[str, Any]) -> Glossary:
    path = record.get("entries_path")
    if not path or not Path(path).exists():
        raise FileNotFoundError(f"glossary {record['glossary_id']} v{record['version']} has no entries file")
    return Glossary.model_validate_json(Path(path).read_text(encoding="utf-8"))


def save_entries(
    store: GlossaryStore,
    settings: Settings,
    record: dict[str, Any],
    entries: list[GlossaryEntry],
    style_notes: Optional[str] = None,
    name: Optional[str] = None,
    created_by: Optional[str] = None,
) -> dict[str, Any]:
    """Save a reviewer's edit: in place while in review, as the next version once approved."""
    name = (name or "").strip() or record["name"]
    if record["status"] == "approved":
        return create_version(store, settings, glossary_id=record["glossary_id"], name=name,
                              language=record["language"], entries=entries, style_notes=style_notes,
                              created_by=created_by)
    glossary = build({**record, "name": name}, entries, style_notes)
    return _write(store, settings, record, glossary)


def approve(store: GlossaryStore, record: dict[str, Any]) -> dict[str, Any]:
    load(record)  # it must have a readable entries file
    return store.update_fields(record["id"], status="approved")
