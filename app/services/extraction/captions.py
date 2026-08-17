"""Caption extractor using proximity and heuristics.

Identifies paragraphs that are actually captions for adjacent images or tables,
associates the text with the visual element, and removes the standalone paragraph.
"""

import re

from app.schemas.document import (
    ElementType,
    RawDocument,
)
from .base_extractor import BaseExtractor


class CaptionExtractor(BaseExtractor):
    """Associates caption paragraphs with their corresponding images or tables."""

    # Regex to match typical caption starters like "Figure 1:", "Table 2.1 -", "Example 1:", etc.
    CAPTION_PATTERN = re.compile(r"^(figure|fig\.|table|example|ex\.)\s*\d+[\.:\s-]", re.IGNORECASE)

    def extract(self, document: RawDocument) -> RawDocument:
        self.logger.info(f"CaptionExtractor: processing {document.source}")

        for page in document.pages:
            new_elements = []
            skip_next = False
            
            # We need to look at elements in pairs (or triads) to find adjacencies.
            elements = page.elements
            
            for i, element in enumerate(elements):
                if skip_next:
                    skip_next = False
                    continue

                if element.element_type in (ElementType.IMAGE, ElementType.TABLE):
                    # Check the NEXT element to see if it's a caption
                    if i + 1 < len(elements):
                        next_el = elements[i + 1]
                        if next_el.element_type in (
                            ElementType.PARAGRAPH,
                            ElementType.NUMBERED_STEP,
                            ElementType.LIST_ITEM,
                        ):
                            if self._is_likely_caption(next_el.content):
                                # It's a caption. Associate it and skip adding the paragraph.
                                element.caption = next_el.content
                                skip_next = True
                            else:
                                cap_match = re.search(
                                    r"^((?:figure|fig\.|table|example|ex\.)\s*\d+[\.:\s-][^\n\.]*(?:\.|\n|$))",
                                    next_el.content,
                                    re.IGNORECASE,
                                )
                                if cap_match:
                                    element.caption = cap_match.group(1).strip()
                                    next_el.content = next_el.content[cap_match.end(1):].strip()

                    # If we didn't find one after, check `new_elements[-1]`.
                    if not skip_next and not element.caption and new_elements:
                        prev_el = new_elements[-1]
                        if prev_el.element_type in (
                            ElementType.PARAGRAPH,
                            ElementType.NUMBERED_STEP,
                            ElementType.LIST_ITEM,
                        ):
                            if self._is_likely_caption(prev_el.content):
                                element.caption = prev_el.content
                                # Remove the paragraph we already added
                                new_elements.pop()
                            else:
                                cap_match = re.search(
                                    r"(?:^|\n|\.\s+)((?:figure|fig\.|table|example|ex\.)\s*\d+[\.:\s-].*)$",
                                    prev_el.content,
                                    re.IGNORECASE,
                                )
                                if cap_match:
                                    element.caption = cap_match.group(1).strip()
                                    prev_el.content = prev_el.content[:cap_match.start(1)].strip()

                new_elements.append(element)

            page.elements = new_elements

        return document

    def _is_likely_caption(self, text: str) -> bool:
        """Heuristic to determine if a string of text is a caption."""
        if not text:
            return False
        
        # Exact regex match
        if self.CAPTION_PATTERN.match(text):
            return True
            
        # Fallback heuristic: very short paragraph starting with Fig, Table, or Example
        lower_text = text.lower()
        if (
            lower_text.startswith("fig")
            or lower_text.startswith("table")
            or lower_text.startswith("example")
        ) and len(text) < 150:
            return True
            
        return False
