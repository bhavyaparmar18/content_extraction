"""Abstract base class for chunking strategies.

Both HierarchicalChunker and SemanticChunker inherit from this class.
"""

from abc import ABC, abstractmethod
from loguru import logger as _default_logger

from app.schemas.document import Chunk, ExtractedElement
from app.schemas.ast_nodes import DocumentNode
from app.config.settings import Settings


class BaseChunker(ABC):
    """Contract for all chunking implementations."""

    def __init__(self, settings: Settings, logger=None) -> None:
        self.settings = settings
        self.logger = logger or _default_logger

    @abstractmethod
    def chunk(self, data: DocumentNode | list[Chunk]) -> list[Chunk]:
        """Convert a document or a list of chunks into a refined list of Chunks.

        Returns:
            A list of Chunk objects with metadata populated.
        """
        ...
