"""Abstract base class for element extractors.

Each extractor (headings, tables, images, icons, captions, paragraphs)
inherits from this class and implements the `extract` method.
"""

from abc import ABC, abstractmethod
from loguru import logger as _default_logger

from app.schemas.document import RawDocument, ExtractedElement
from app.config.settings import Settings


class BaseExtractor(ABC):
    """Contract for all element extraction classes."""

    def __init__(self, settings: Settings, logger=None) -> None:
        self.settings = settings
        self.logger = logger or _default_logger

    @abstractmethod
    def extract(self, document: RawDocument) -> RawDocument:
        """Process the document to extract or refine specific elements.

        Returns:
            The mutated or enriched RawDocument.
        """
        ...
