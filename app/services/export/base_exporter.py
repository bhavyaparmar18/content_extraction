"""Abstract base class for export formatters.

JSONExporter (and any future format) inherits from this class.
"""

from abc import ABC, abstractmethod
from loguru import logger as _default_logger

from app.schemas.document import DocumentOutput
from app.config.settings import Settings


class BaseExporter(ABC):
    """Contract for all export implementations."""

    def __init__(self, settings: Settings, logger=None) -> None:
        self.settings = settings
        self.logger = logger or _default_logger

    @abstractmethod
    def export(self, document: DocumentOutput, output_path: str) -> str:
        """Export the structured DocumentOutput to the given path.

        Returns:
            The absolute path of the written file.
        """
        ...
