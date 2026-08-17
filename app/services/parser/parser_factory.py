"""Parser factory — selects the correct parser based on file extension.

This is the single entry point the API layer uses.  It never needs to
know which concrete parser is being invoked.
"""

from __future__ import annotations

from pathlib import Path
from loguru import logger as _default_logger

from app.config.settings import Settings
from .base_parser import BaseParser
from .pdf_parser import PDFParser
from .docx_parser import DocxParser


class ParserFactory:
    """Construct and return the appropriate parser for a given file."""

    _REGISTRY: dict[str, type[BaseParser]] = {
        ".pdf": PDFParser,
        ".docx": DocxParser,
    }

    def __init__(self, settings: Settings, logger=None) -> None:
        self.settings = settings
        self.logger = logger or _default_logger

    def get_parser(self, file_path: str) -> BaseParser:
        """Return a parser instance suitable for *file_path*.

        Raises:
            ValueError: if the file extension is not supported.
        """
        ext = Path(file_path).suffix.lower()
        parser_cls = self._REGISTRY.get(ext)

        if parser_cls is None:
            raise ValueError(
                f"No parser registered for extension '{ext}'. "
                f"Supported: {list(self._REGISTRY.keys())}"
            )

        self.logger.info(f"ParserFactory: selected {parser_cls.__name__} for '{ext}'")
        return parser_cls(settings=self.settings, logger=self.logger)
