import pytest
import uuid

from app.config.settings import Settings
from app.schemas.document import Chunk, ChunkType
from app.services.chunking.validator import ChunkValidator


@pytest.fixture
def settings():
    return Settings()


def test_validator_passes_valid_chunk(settings):
    validator = ChunkValidator(settings=settings)
    chunk = Chunk(
        chunk_id=str(uuid.uuid4()),
        chunk_type=ChunkType.SECTION,
        content="This is a perfectly valid chunk."
    )
    is_valid, warnings = validator.validate([chunk])
    assert is_valid is True
    assert len(warnings) == 0


def test_validator_fails_empty_chunk(settings):
    validator = ChunkValidator(settings=settings)
    chunk = Chunk(
        chunk_id=str(uuid.uuid4()),
        chunk_type=ChunkType.SECTION,
        content=""
    )
    is_valid, warnings = validator.validate([chunk])
    assert is_valid is False
    assert len(warnings) == 1
    assert "is completely empty" in warnings[0]


def test_validator_passes_empty_chunk_with_image(settings):
    # An empty chunk is valid if it contains an image or table
    validator = ChunkValidator(settings=settings)
    chunk = Chunk(
        chunk_id=str(uuid.uuid4()),
        chunk_type=ChunkType.SECTION,
        content="",
        images=[{"element_type": "image", "image_path": "test.png", "caption": "", "width": 100, "height": 100}]
    )
    is_valid, warnings = validator.validate([chunk])
    assert is_valid is True
    assert len(warnings) == 0


def test_validator_fails_oversized_chunk(settings):
    validator = ChunkValidator(settings=settings)
    # Generate 1600 words
    long_content = " ".join(["word"] * 1600)
    chunk = Chunk(
        chunk_id=str(uuid.uuid4()),
        chunk_type=ChunkType.SECTION,
        content=long_content
    )
    is_valid, warnings = validator.validate([chunk])
    assert is_valid is False
    assert len(warnings) == 1
    assert "is very large (1600 words)" in warnings[0]
