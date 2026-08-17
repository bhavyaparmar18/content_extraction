"""Icon extractor using perceptual hashing and heuristics.

Detects if extracted images are actually semantic icons (e.g., Warning, PPE)
and converts them from generic images to ExtractedIcon elements.
"""

import json
import shutil
from pathlib import Path

import imagehash
from PIL import Image

from app.schemas.document import (
    ElementType,
    ExtractedIcon,
    RawDocument,
)
from app.schemas.ast_nodes import IconCategory
from app.config.settings import Settings
from .base_extractor import BaseExtractor


class IconExtractor(BaseExtractor):
    """Converts images into icons if they match known heuristics or hashes."""

    # Hamming distance threshold for matching perceptual hashes.
    HASH_THRESHOLD = 5

    def __init__(self, settings: Settings, logger=None):
        super().__init__(settings, logger)
        self._reference_library = self._load_reference_library()

    def _load_reference_library(self) -> dict[str, list[imagehash.ImageHash]]:
        """Load icon reference hashes from data/config/icon_library.json"""
        library_path = Path("data/config/icon_library.json")
        if not library_path.exists():
            # Create a default empty template
            library_path.parent.mkdir(parents=True, exist_ok=True)
            default_data = {
                "warning": [],
                "ppe": [],
                "info": []
            }
            library_path.write_text(json.dumps(default_data, indent=2))
            return {}

        try:
            data = json.loads(library_path.read_text())
            return {
                meaning: [imagehash.hex_to_hash(h) for h in hashes]
                for meaning, hashes in data.items()
            }
        except Exception as e:
            self.logger.warning(f"Failed to load icon library: {e}")
            return {}

    def extract(self, document: RawDocument, document_id: str | None = None) -> RawDocument:
        self.logger.info(f"IconExtractor: processing {document.source}")

        for page in document.pages:
            new_elements = []
            
            for element in page.elements:
                if element.element_type != ElementType.IMAGE:
                    new_elements.append(element)
                    continue

                # It's an image. Let's see if it's an icon.
                img_path = Path(element.image_path)
                if not img_path.exists():
                    new_elements.append(element)
                    continue

                try:
                    with Image.open(img_path) as img:
                        # 1. Size heuristic check
                        width, height = img.size
                        is_icon_candidate = width <= 128 and height <= 128
                        
                        if not is_icon_candidate:
                            # Not an icon
                            new_elements.append(element)
                            continue

                        # Use average hash for speed/simplicity
                        current_hash = imagehash.average_hash(img)
                except Exception as e:
                    self.logger.warning(f"IconExtractor: Failed to process {img_path}: {e}")
                    new_elements.append(element)
                    continue

                # 2. Check against known dictionary
                matched_meaning = None
                for meaning, hashes in self._reference_library.items():
                    for known_hash in hashes:
                        if current_hash - known_hash <= self.HASH_THRESHOLD:
                            matched_meaning = meaning
                            break
                    if matched_meaning:
                        break

                if matched_meaning or is_icon_candidate:
                    # Move icon file to document's icon directory if document_id is provided
                    final_path = img_path
                    if document_id:
                        icon_dir = self.settings.get_document_icon_dir(document_id)
                        new_path = icon_dir / img_path.name
                        try:
                            if img_path.exists() and img_path != new_path:
                                shutil.move(str(img_path), str(new_path))
                                final_path = new_path
                        except Exception as e:
                            self.logger.warning(f"IconExtractor: Failed to move icon to {new_path}: {e}")

                    # Convert to icon
                    icon_el = ExtractedIcon(
                        content=f"[Icon: {matched_meaning or 'unknown'}]",
                        page=element.page,
                        sequence=element.sequence,
                        bbox=element.bbox,
                        icon_id=str(current_hash),
                        semantic_meaning=matched_meaning or "unknown",
                        image_path=str(final_path),
                    )
                    new_elements.append(icon_el)
                    self.logger.debug(f"Identified icon: {matched_meaning or 'unknown'}")
                else:
                    # Keep as regular image
                    new_elements.append(element)

            page.elements = new_elements

        return document
