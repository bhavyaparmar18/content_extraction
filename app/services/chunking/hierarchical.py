"""Hierarchical chunking strategy.

Transforms a nested DocumentNode (AST root) into a linear sequence of logical Chunks,
where each SectionNode (and its direct elements) becomes a distinct Chunk.
Atomic elements like tables and images are preserved intact within the chunk.
"""

import uuid
from typing import Union

from app.schemas.document import (
    Chunk,
    ChunkMetadata,
    ChunkType,
    ExtractedTable,
    ExtractedTableCell,
    ExtractedImage,
    ExtractedIcon,
)
from app.schemas.ast_nodes import (
    DocumentNode,
    SectionNode,
    ParagraphNode,
    ListNode,
    TableNode,
    ImageNode,
    IconNode,
    CaptionNode,
)
from .base_chunker import BaseChunker


class HierarchicalChunker(BaseChunker):
    """Chunks a document strictly by its structural headings using the AST."""

    def chunk(self, data: Union[DocumentNode, list[Chunk]]) -> list[Chunk]:
        if not isinstance(data, DocumentNode):
            raise TypeError("HierarchicalChunker expects a DocumentNode.")

        self.logger.info(f"HierarchicalChunker: processing {data.doc_metadata.title or 'document'}")

        chunks: list[Chunk] = []
        
        # We perform a pre-order traversal of the AST
        self._traverse(data, chunks, parent_id=None)

        self.logger.info(f"HierarchicalChunker: produced {len(chunks)} chunks.")
        return chunks

    def _traverse(self, node: Union[DocumentNode, SectionNode], chunks_out: list[Chunk], parent_id: str | None = None) -> None:
        """Recursively convert a SectionNode/DocumentNode into a Chunk and process its children."""
        
        # If the node has children that are not just sections, it might have content
        has_content_children = any(
            child.node_type not in ("section", "heading") for child in node.children
        )
        
        heading_text = ""
        heading_node = None
        page = 0
        bboxes = []
        
        if isinstance(node, SectionNode) and node.heading:
            heading_node = node.heading
            heading_text = heading_node.text
            if heading_node.source_location:
                page = heading_node.source_location.page
                if heading_node.source_location.bbox:
                    bboxes.append(heading_node.source_location.bbox)
                    
        # Only create a chunk if there is actual content, tables, images, or a heading
        if has_content_children or heading_node:
            chunk_id = str(uuid.uuid4())
            
            content_parts = []
            tables = []
            images = []
            icons = []
            
            contains_table = False
            contains_image = False
            contains_icon = False
            
            for child in node.children:
                # Update page and bbox tracking
                if getattr(child, "source_location", None):
                    if child.source_location.page > 0 and page == 0:
                        page = child.source_location.page
                    if child.source_location.bbox:
                        bboxes.append(child.source_location.bbox)
                        
                if isinstance(child, ParagraphNode):
                    content_parts.append(child.text)
                elif isinstance(child, ListNode):
                    # Simple text serialization of a list for the chunk text body
                    for item in child.items:
                        marker_str = f"{item.index}." if getattr(item, "index", None) is not None else "-"
                        content_parts.append(f"{marker_str} {item.text}")
                elif isinstance(child, CaptionNode):
                    content_parts.append(f"Caption: {child.text}")
                elif isinstance(child, TableNode):
                    def _get_cell_text(cell) -> str:
                        if isinstance(cell, str):
                            return cell
                        if hasattr(cell, "text") and isinstance(getattr(cell, "text"), str):
                            return getattr(cell, "text")
                        parts = []
                        for node in getattr(cell, "content", []):
                            if isinstance(node, str):
                                parts.append(node)
                            elif isinstance(node, IconNode):
                                icon_id_str = getattr(node, "icon_id", getattr(node, "node_id", ""))
                                parts.append(f"[Icon: {node.semantic_meaning} | ID: {icon_id_str} | Path: {node.asset_path}]")
                            elif isinstance(node, ImageNode):
                                caption_str = str(getattr(node.caption, "text", node.caption)) if node.caption else "image"
                                parts.append(f"[Image: {caption_str} | Path: {node.asset_path}]")
                            elif hasattr(node, "text") and isinstance(getattr(node, "text"), str):
                                parts.append(getattr(node, "text"))
                        return " ".join(parts).strip()

                    def _to_extracted_table_cell(cell) -> ExtractedTableCell:
                        if isinstance(cell, ExtractedTableCell):
                            return cell
                        if isinstance(cell, str):
                            return ExtractedTableCell(content_text=cell)
                        text_str = _get_cell_text(cell)
                        return ExtractedTableCell(
                            content_text=text_str,
                            row_span=getattr(cell, "row_span", 1),
                            col_span=getattr(cell, "col_span", 1),
                            is_merge_origin=getattr(cell, "is_merge_origin", True),
                            merge_origin_ref=getattr(cell, "merge_origin_ref", None),
                        )

                    # Convert TableNode back to ExtractedTable for the Chunk schema
                    tables.append(
                        ExtractedTable(
                            content="[Table]",
                            headers=[_to_extracted_table_cell(c) for c in child.rows[0].cells] if child.rows else [],
                            rows=[[_to_extracted_table_cell(c) for c in r.cells] for r in child.rows[1:]] if len(child.rows) > 1 else [],
                        )
                    )
                    contains_table = True
                elif isinstance(child, ImageNode):
                    caption_str = str(getattr(child.caption, "text", child.caption)) if child.caption else "image"
                    marker_str = f"[Image: {caption_str} | Path: {child.asset_path}]"
                    content_parts.append(marker_str)
                    images.append(
                        ExtractedImage(
                            content=marker_str,
                            image_path=child.asset_path,
                            caption=caption_str,
                        )
                    )
                    contains_image = True
                elif isinstance(child, IconNode):
                    icon_id_str = getattr(child, "icon_id", getattr(child, "node_id", ""))
                    marker_str = f"[Icon: {child.semantic_meaning} | ID: {icon_id_str} | Path: {child.asset_path}]"
                    content_parts.append(marker_str)
                    icons.append(
                        ExtractedIcon(
                            content=marker_str,
                            icon_id=icon_id_str,
                            semantic_meaning=child.semantic_meaning,
                            image_path=child.asset_path,
                        )
                    )
                    contains_icon = True

            if heading_text:
                content_parts.insert(0, f"# {heading_text}")
                
            full_content = "\n\n".join(content_parts).strip()
            
            chunk_type = ChunkType.SECTION
            heading_lower = heading_text.lower()
            if "procedure" in heading_lower or "step" in heading_lower:
                chunk_type = ChunkType.PROCEDURE
            elif "reference" in heading_lower:
                chunk_type = ChunkType.REFERENCE
            elif "appendix" in heading_lower:
                chunk_type = ChunkType.APPENDIX
                
            if tables and not full_content.replace(f"# {heading_text}", "").strip():
                chunk_type = ChunkType.TABLE
            
            if full_content or tables or images or icons:
                metadata = ChunkMetadata(
                    chunk_id=chunk_id,
                    parent_id=parent_id,
                    section=heading_text,
                    heading=heading_text,
                    page=page,
                    sequence=len(chunks_out),
                    chunk_type=chunk_type,
                    contains_table=contains_table,
                    contains_image=contains_image,
                    contains_icon=contains_icon,
                    source_coordinates=bboxes,
                )
                
                chunk = Chunk(
                    chunk_id=chunk_id,
                    chunk_type=chunk_type,
                    heading=heading_text,
                    content=full_content,
                    tables=tables,
                    images=images,
                    icons=icons,
                    metadata=metadata,
                )
                chunks_out.append(chunk)
        else:
            chunk_id = parent_id

        # Recurse into children that are SectionNodes
        for child in node.children:
            if isinstance(child, SectionNode):
                self._traverse(child, chunks_out, parent_id=chunk_id)
