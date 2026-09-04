"""Abstract base class for document parsers.

Every parser (PDF, DOCX, OCR) must inherit from this class and implement
the `parse` method.  Dependencies are injected through the constructor.
"""

from abc import ABC, abstractmethod
from loguru import logger as _default_logger

from app.schemas.document import RawDocument
from app.config.settings import Settings


class BaseParser(ABC):
    """Contract that every document parser must fulfill."""

    def __init__(self, settings: Settings, logger=None) -> None:
        self.settings = settings
        self.logger = logger or _default_logger

    @abstractmethod
    def parse(self, file_path: str) -> RawDocument:
        """Parse the file at *file_path* and return a RawDocument.

        Raises:
            FileNotFoundError: if the file does not exist.
            ValueError: if the file format is unsupported or corrupt.
        """
        ...

    def _validate_file(self, file_path: str) -> None:
        """Shared pre-parse validation (existence, extension)."""
        from pathlib import Path

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        if path.suffix.lower() not in self.settings.allowed_extensions:
            raise ValueError(
                f"Unsupported file extension '{path.suffix}'. "
                f"Allowed: {self.settings.allowed_extensions}"
            )

    def _next_gpdat_version(self, document_id: str | None) -> int:
        """Preview the gpdat_version this extract will receive from sop_records."""
        if not document_id:
            return 0
        try:
            from app.stores.sop_store import SopStore

            db_path = getattr(self.settings, "sop_db_path", None)
            if db_path is None:
                db_path = self.settings.project_root / "data" / "sop_records.db"
            return SopStore(db_path, self.settings).get_next_version(document_id)
        except Exception:
            return 1
