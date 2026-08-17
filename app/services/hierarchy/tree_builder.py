"""Hierarchy tree builder.

Transforms a flat list of extracted elements into a nested tree structure
based on heading levels. This structured tree is the input for the chunker.
"""

import uuid
from typing import Optional

from loguru import logger as _default_logger

from app.config.settings import Settings
from app.schemas.document import (
    ElementType,
    RawDocument,
    SectionNode,
    StructuredDocument,
    ExtractedHeading,
)


class TreeBuilder:
    """Builds a hierarchical section tree from a flat RawDocument."""

    def __init__(self, settings: Settings, logger=None) -> None:
        self.settings = settings
        self.logger = logger or _default_logger

    def build(self, document: RawDocument) -> StructuredDocument:
        self.logger.info(f"TreeBuilder: building hierarchy for {document.source}")

        # Create a virtual root node to hold everything.
        # This represents the document as a whole.
        root = SectionNode(
            node_id=str(uuid.uuid4()),
            heading=ExtractedHeading(
                content=document.metadata.title or "Document Root",
                page=0,
                sequence=-1,
                level=0,  # Level 0 is the absolute root
            ),
            level=0,
        )

        # Maintain a stack of active sections to figure out parent-child relations.
        # Initialize the stack with the root node.
        stack: list[SectionNode] = [root]

        # Flatten all elements from all pages into a single list
        all_elements = []
        for page in document.pages:
            all_elements.extend(page.elements)

        # Ensure elements are sorted by sequence (they should be, but just in case)
        # Sequence might restart per page, so we rely on the page order + sequence.
        # Since we just appended them page by page, they are in reading order.
        
        for element in all_elements:
            if element.element_type == ElementType.HEADING:
                # We know it's an ExtractedHeading because of the type check
                heading = element # type: ExtractedHeading
                level = heading.level

                new_section = SectionNode(
                    node_id=str(uuid.uuid4()),
                    heading=heading,
                    level=level,
                )

                # Pop from the stack until we find a parent with a STRICTLY LOWER level number
                # (Remember: Level 1 is a higher heading than Level 2)
                while stack and stack[-1].level >= level:
                    stack.pop()

                if not stack:
                    # Should never happen because root is level 0, but just in case fallback
                    stack.append(root)

                parent = stack[-1]
                parent.children.append(new_section)
                
                # Push the new section onto the active stack
                stack.append(new_section)
                
            else:
                # It's a regular element (paragraph, table, image, etc.)
                # Assign it to the current active section (top of the stack)
                current_section = stack[-1]
                current_section.elements.append(element)

        return StructuredDocument(
            source=document.source,
            metadata=document.metadata,
            root=root,
        )
