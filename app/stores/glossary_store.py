"""Glossary records: one row per uploaded or edited glossary version of one language.

The terms live in the Glossary JSON at ``entries_path``, which is the source of
truth after review. A translation job names the version it uses (glossaries are optional).
"""

from app.stores.versioned_store import VersionedRecordStore

# Must match the CHECK constraint in app/db/migrations/0002_translation.sql.
GLOSSARY_STATUSES = ("uploaded", "in_review", "approved", "failed")


class GlossaryStore(VersionedRecordStore):
    TABLE = "glossaries"
    ID_COLUMN = "glossary_id"
    LABEL = "Glossary"
    STATUSES = GLOSSARY_STATUSES
    PATH_COLUMNS = ("upload_path", "entries_path")
    UPDATABLE = frozenset({"name", "entries_path", "total_entries", "status", "error"})
    INSERTABLE = UPDATABLE | {"file_type", "file_size_bytes", "source_filename", "upload_path"}
    JOB_COLUMNS = ("glossary_id", "glossary_version")
