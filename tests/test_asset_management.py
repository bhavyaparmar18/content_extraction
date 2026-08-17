"""Unit tests for per-document asset management and icon asset movement."""

from pathlib import Path
from PIL import Image
import pytest

from app.config.settings import Settings
from app.schemas.document import (
    ElementType,
    ExtractedImage,
    PageContent,
    RawDocument,
    DocumentMetadata,
)
from app.services.extraction.icons import IconExtractor


def test_settings_per_document_asset_dirs(tmp_path):
    settings = Settings(project_root=tmp_path)
    doc_id = "SOP_101_v1.0"

    img_dir = settings.get_document_image_dir(doc_id)
    icon_dir = settings.get_document_icon_dir(doc_id)

    assert img_dir.exists()
    assert icon_dir.exists()
    assert img_dir == Path("data/extracted_images") / doc_id
    assert icon_dir == Path("data/extracted_icons") / doc_id


def test_icon_extractor_moves_icon(tmp_path):
    settings = Settings(project_root=tmp_path)
    doc_id = "SOP_ICON_TEST_v1"

    img_dir = settings.get_document_image_dir(doc_id)
    icon_dir = settings.get_document_icon_dir(doc_id)

    # Create a dummy small image file in img_dir (64x64 candidate icon)
    test_img_path = img_dir / "candidate_icon.png"
    img = Image.new("RGB", (32, 32), color="red")
    img.save(test_img_path)

    raw_doc = RawDocument(
        source="test.pdf",
        metadata=DocumentMetadata(
            title="Test Doc",
            document_name="Test Doc",
            document_number="SOP-001",
            document_version="1.0",
            duplicate_upload_count=0,
        ),
        pages=[
            PageContent(
                page_number=1,
                elements=[
                    ExtractedImage(
                        content="[Image: candidate_icon.png]",
                        page=1,
                        sequence=1,
                        image_path=str(test_img_path),
                    )
                ],
            )
        ],
    )

    extractor = IconExtractor(settings=settings)
    processed_doc = extractor.extract(raw_doc, document_id=doc_id)

    el = processed_doc.pages[0].elements[0]
    assert el.element_type == ElementType.ICON
    assert Path(el.image_path).parent == icon_dir
    assert Path(el.image_path).name == "candidate_icon.png"
    assert not test_img_path.exists()
    assert Path(el.image_path).exists()
