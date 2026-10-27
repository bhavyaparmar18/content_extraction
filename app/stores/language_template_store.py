"""Language template records: one row per uploaded template version of one language.

Only the template's first page, headers and footers are used; they are extracted
to ``front_matter_path``. A translation job names the version it uses (optional:
without one the English first page, headers and footers are kept).
"""

from app.stores.versioned_store import VersionedRecordStore

# Must match the CHECK constraint in app/db/migrations/0002_translation.sql.
LANGUAGE_TEMPLATE_STATUSES = ("uploaded", "extracted", "ready", "failed")


class LanguageTemplateStore(VersionedRecordStore):
    TABLE = "language_templates"
    ID_COLUMN = "template_id"
    LABEL = "Language template"
    STATUSES = LANGUAGE_TEMPLATE_STATUSES
    PATH_COLUMNS = ("upload_path", "front_matter_path", "preview_path", "report_path")
    UPDATABLE = frozenset({"name", "front_matter_path", "preview_path", "report_path", "status", "error"})
    INSERTABLE = UPDATABLE | {"file_size_bytes", "source_filename", "upload_path"}
    JOB_COLUMNS = ("language_template_id", "language_template_version")
