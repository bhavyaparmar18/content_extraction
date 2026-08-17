"""Validation utilities for ensuring chunk quality."""

from loguru import logger as _default_logger
from app.schemas.document import Chunk, DocumentOutput
from app.config.settings import Settings


class ChunkValidator:
    """Validates the generated chunks before final export."""

    def __init__(self, settings: Settings, logger=None):
        self.settings = settings
        self.logger = logger or _default_logger

    def validate(self, chunks: list[Chunk]) -> tuple[bool, list[str]]:
        """Run validation rules on the chunks.
        
        Returns (is_valid, warnings), where warnings is a list of violation messages.
        """
        self.logger.info(f"ChunkValidator: Validating {len(chunks)} chunks.")
        
        is_valid = True
        warnings = []
        for chunk in chunks:
            # Rule 1: No completely empty chunks unless they contain a visual element
            if not chunk.content and not chunk.tables and not chunk.images and not chunk.icons:
                msg = f"Chunk {chunk.chunk_id} is completely empty."
                self.logger.warning(msg)
                warnings.append(msg)
                is_valid = False

            # Rule 2: Warn if content is excessively long (might indicate a semantic chunking failure)
            word_count = len(chunk.content.split())
            if word_count > 1500:
                msg = f"Chunk {chunk.chunk_id} is very large ({word_count} words)."
                self.logger.warning(msg)
                warnings.append(msg)
                is_valid = False
                
        if is_valid:
            self.logger.info("ChunkValidator: All chunks passed validation.")
            
        return is_valid, warnings
