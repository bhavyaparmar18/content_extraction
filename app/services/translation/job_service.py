"""Starting translation jobs: one per language of a completed migration, each with an optional glossary and an
optional language template. Every language of a request is checked before any job is created."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from app.schemas.v2 import LanguageCode
from app.services.migration_v2.export import EXPORTABLE

from .languages import get_language


class TranslationRequestError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


@dataclass
class LanguageRequest:
    language: str
    glossary_id: Optional[str] = None
    glossary_version: Optional[int] = None
    language_template_id: Optional[str] = None
    language_template_version: Optional[int] = None


@dataclass
class ResolvedLanguage:
    language: LanguageCode
    glossary: Optional[tuple[str, int]] = None
    language_template: Optional[tuple[str, int]] = None


def _resolve(store: Any, record_id: Optional[str], version: Optional[int], language: LanguageCode, *,
             usable: str, label: str, prefix: str) -> Optional[tuple[str, int]]:
    """A glossary (``usable="approved"``) or language template (``"ready"``) version a job may name.

    Without a version: the newest usable one. A named version must be usable and of the job's language.
    """
    if record_id is None:
        if version is not None:
            raise TranslationRequestError(422, f"{prefix}_ID_REQUIRED", f"A {label} version needs its {label} id")
        return None
    if store is None:
        raise TranslationRequestError(503, f"{prefix}S_UNAVAILABLE", f"The {label} store is not available")
    if version is not None:
        record = store.get_version(record_id, version)
        if record is None:
            raise TranslationRequestError(404, f"{prefix}_NOT_FOUND", f"{label.capitalize()} '{record_id}' v{version} not found")
    else:
        records = store.get_records(record_id=record_id)
        if not records:
            raise TranslationRequestError(404, f"{prefix}_NOT_FOUND", f"{label.capitalize()} '{record_id}' not found")
        ready = [r for r in records if r["status"] == usable]
        record = max(ready, key=lambda r: r["version"]) if ready else max(records, key=lambda r: r["version"])
    if record["language"] != language.value:
        raise TranslationRequestError(
            422, f"{prefix}_LANGUAGE_MISMATCH",
            f"{label.capitalize()} '{record_id}' v{record['version']} is for {record['language']}, not {language.value}")
    if record["status"] != usable:
        code = "GLOSSARY_NOT_APPROVED" if prefix == "GLOSSARY" else "LANGUAGE_TEMPLATE_NOT_READY"
        raise TranslationRequestError(
            409, code, f"{label.capitalize()} '{record_id}' v{record['version']} is {record['status']}, not {usable}")
    return record_id, record["version"]


def resolve_request(migrations: Any, glossaries: Any, language_templates: Any, migration_job_id: str,
                    languages: list[LanguageRequest]) -> list[ResolvedLanguage]:
    migration = migrations.get_job(migration_job_id)
    if migration is None:
        raise TranslationRequestError(404, "MIGRATION_NOT_FOUND", f"Migration job '{migration_job_id}' not found")
    if migration.status not in EXPORTABLE:
        raise TranslationRequestError(
            409, "MIGRATION_NOT_COMPLETED",
            f"Migration {migration_job_id} is {migration.status.value}; a translation starts from a completed migration")
    if not languages:
        raise TranslationRequestError(422, "NO_LANGUAGES", "Choose at least one language")
    out: list[ResolvedLanguage] = []
    for item in languages:
        try:
            language = LanguageCode(get_language(item.language).word_lang)
        except ValueError as exc:
            raise TranslationRequestError(422, "UNSUPPORTED_LANGUAGE", str(exc)) from exc
        if any(r.language == language for r in out):
            raise TranslationRequestError(422, "DUPLICATE_LANGUAGE", f"{language.value} is requested more than once")
        out.append(ResolvedLanguage(
            language=language,
            glossary=_resolve(glossaries, item.glossary_id, item.glossary_version, language,
                              usable="approved", label="glossary", prefix="GLOSSARY"),
            language_template=_resolve(language_templates, item.language_template_id, item.language_template_version,
                                       language, usable="ready", label="language template",
                                       prefix="LANGUAGE_TEMPLATE"),
        ))
    return out
