import pytest
import uuid

from app.config.settings import Settings
from app.schemas.ast_nodes import (
    DocumentNode,
    SectionNode,
    ParagraphNode,
)
from app.schemas.document import (
    DocumentMetadata,
    Chunk,
    ChunkMetadata,
    ChunkType,
)
from app.services.chunking.hierarchical import HierarchicalChunker
from app.services.chunking.semantic import SemanticChunker


@pytest.fixture
def settings():
    return Settings(similarity_threshold=0.5)


def test_hierarchical_chunker(settings):
    # Setup mock AST document node
    doc_id = str(uuid.uuid4())
    
    root = DocumentNode(
        node_id="root",
        doc_metadata=DocumentMetadata(title="Test Doc"),
        children=[
            ParagraphNode(node_id="p1", text="Intro text"),
            SectionNode(
                node_id="child1",
                level=1,
                children=[
                    ParagraphNode(node_id="p2", text="Step 1 details")
                ]
            )
        ]
    )

    chunker = HierarchicalChunker(settings=settings)
    chunks = chunker.chunk(root)

    # Root chunk + Child chunk
    assert len(chunks) == 2
    assert chunks[0].content == "Intro text"
    assert chunks[1].content == "Step 1 details"


def test_semantic_chunker(settings):
    chunk_id = str(uuid.uuid4())
    # Create a chunk with two distinct paragraphs that should be split
    base_chunk = Chunk(
        chunk_id=chunk_id,
        chunk_type=ChunkType.SECTION,
        content="This is a paragraph about cleaning the equipment. It involves wiping down surfaces and ensuring all chemicals are removed safely. All laboratory personnel must adhere strictly to these guidelines to ensure a sterile environment. Failure to comply can result in contamination.\n\nThis completely different paragraph discusses the annual budget and financial forecasts for the upcoming fiscal year. It has nothing to do with cleaning. We need to allocate funds for new marketing campaigns, hire additional staff, and expand our real estate footprint globally.",
        metadata=ChunkMetadata(chunk_id=chunk_id, section="Test Section")
    )
    
    chunker = SemanticChunker(settings=settings)
    refined = chunker.chunk([base_chunk])
    
    # Given the high semantic difference, it should be split into 2 chunks
    assert len(refined) == 2
    assert "cleaning" in refined[0].content
    assert "budget" in refined[1].content
    assert "Part 1" in refined[0].metadata.section
    assert "Part 2" in refined[1].metadata.section


def test_merge_continuation_unbalanced_parenthesis(settings):
    """Paragraphs split mid-parenthetical by PDF layout must be merged."""
    chunker = SemanticChunker(settings=settings)
    paragraphs = [
        "1. Channels deliver messages to the Gateway (WS",
        "control plane).",
        "2. The Gateway handles sessions and routing.",
    ]
    merged = chunker._merge_continuation_paragraphs(paragraphs)
    # First two should be merged because "Gateway (WS" has an unbalanced "("
    assert len(merged) == 2
    assert merged[0] == "1. Channels deliver messages to the Gateway (WS control plane)."
    assert merged[1] == "2. The Gateway handles sessions and routing."


def test_merge_continuation_lowercase_start(settings):
    """A paragraph starting with a lowercase letter is merged with the previous."""
    chunker = SemanticChunker(settings=settings)
    paragraphs = [
        "The system processes requests via the main",
        "handler module.",
        "Responses are returned to the client.",
    ]
    merged = chunker._merge_continuation_paragraphs(paragraphs)
    assert len(merged) == 2
    assert merged[0] == "The system processes requests via the main handler module."
    assert merged[1] == "Responses are returned to the client."


def test_no_merge_for_complete_sentences(settings):
    """Complete sentences should NOT be merged — paragraph boundary is preserved."""
    chunker = SemanticChunker(settings=settings)
    paragraphs = [
        "The system processes requests.",
        "Responses are returned to the client.",
    ]
    merged = chunker._merge_continuation_paragraphs(paragraphs)
    assert len(merged) == 2  # no merge; both end with "."


def test_inline_icon_image_chunking(settings):
    from app.schemas.ast_nodes import ImageNode, IconNode, CaptionNode
    from app.schemas.document import ExtractedImage, ExtractedIcon

    root = DocumentNode(
        node_id="root",
        doc_metadata=DocumentMetadata(title="Test Doc"),
        children=[
            ParagraphNode(
                node_id="p1",
                text="This is a paragraph about cleaning the equipment. It involves wiping down surfaces and ensuring all chemicals are removed safely. All laboratory personnel must adhere strictly to these guidelines to ensure a sterile environment. Failure to comply can result in contamination."
            ),
            IconNode(
                node_id="hash_123",
                semantic_meaning="warning",
                asset_path="data/extracted_icons/doc1/warn.png"
            ),
            ParagraphNode(
                node_id="p2",
                text="This completely different paragraph discusses the annual budget and financial forecasts for the upcoming fiscal year. It has nothing to do with cleaning. We need to allocate funds for new marketing campaigns, hire additional staff, and expand our real estate footprint globally."
            ),
            ImageNode(
                node_id="img1",
                asset_path="data/extracted_images/doc1/budget_chart.png",
                caption="Budget Chart"
            )
        ]
    )

    h_chunker = HierarchicalChunker(settings=settings)
    h_chunks = h_chunker.chunk(root)
    assert len(h_chunks) == 1
    content = h_chunks[0].content
    assert "[Icon: warning" in content
    assert "[Image: Budget Chart" in content
    assert len(h_chunks[0].icons) == 1
    assert len(h_chunks[0].images) == 1

    s_chunker = SemanticChunker(settings=settings)
    s_chunks = s_chunker.chunk(h_chunks)

    # Should split into two semantic sub-chunks
    assert len(s_chunks) == 2
    # First sub-chunk should contain cleaning and warning icon
    assert "cleaning" in s_chunks[0].content
    assert "[Icon: warning" in s_chunks[0].content
    assert len(s_chunks[0].icons) == 1
    assert len(s_chunks[0].images) == 0

    # Second sub-chunk should contain budget and budget chart image
    assert "budget" in s_chunks[1].content
    assert "[Image: Budget Chart" in s_chunks[1].content
    assert len(s_chunks[1].icons) == 0
    assert len(s_chunks[1].images) == 1


def test_table_cell_content_chunking(settings):
    from app.schemas.ast_nodes import TableNode, TableRowNode, TableCellNode, ParagraphNode

    root = DocumentNode(
        node_id="root",
        doc_metadata=DocumentMetadata(title="Test Doc with Table"),
        children=[
            TableNode(
                node_id="tbl1",
                rows=[
                    TableRowNode(
                        node_id="row0",
                        is_header=True,
                        cells=[
                            TableCellNode(
                                node_id="c00",
                                content=[ParagraphNode(node_id="p00", text="Header 1")],
                            ),
                            TableCellNode(
                                node_id="c01",
                                content=[ParagraphNode(node_id="p01", text="Header 2")],
                            ),
                        ],
                    ),
                    TableRowNode(
                        node_id="row1",
                        cells=[
                            TableCellNode(
                                node_id="c10",
                                content=[ParagraphNode(node_id="p10", text="Value 1")],
                            ),
                            TableCellNode(
                                node_id="c11",
                                content=[ParagraphNode(node_id="p11", text="Value 2")],
                            ),
                        ],
                    ),
                ],
            )
        ],
    )

    h_chunker = HierarchicalChunker(settings=settings)
    h_chunks = h_chunker.chunk(root)
    assert len(h_chunks) == 1
    assert len(h_chunks[0].tables) == 1
    assert [c.content_text for c in h_chunks[0].tables[0].headers] == ["Header 1", "Header 2"]
    assert [[c.content_text for c in r] for r in h_chunks[0].tables[0].rows] == [["Value 1", "Value 2"]]


def test_table_cell_icon_chunking(settings):
    from app.schemas.ast_nodes import (
        IconNode,
        TableNode,
        TableRowNode,
        TableCellNode,
        ParagraphNode,
        DocumentNode,
    )
    from app.schemas.document import DocumentMetadata

    root = DocumentNode(
        node_id="root",
        doc_metadata=DocumentMetadata(title="Test Table with Icons"),
        children=[
            TableNode(
                node_id="tbl_icon",
                rows=[
                    TableRowNode(
                        node_id="r0",
                        is_header=True,
                        cells=[
                            TableCellNode(
                                node_id="c0",
                                content=[
                                    IconNode(
                                        node_id="icon1",
                                        semantic_meaning="warning",
                                        asset_path="data/extracted_icons/warn.png",
                                    ),
                                    ParagraphNode(node_id="p0", text="Warning description"),
                                ],
                            )
                        ],
                    )
                ],
            )
        ],
    )

    h_chunker = HierarchicalChunker(settings=settings)
    h_chunks = h_chunker.chunk(root)
    assert len(h_chunks) == 1
    assert len(h_chunks[0].tables) == 1
    assert "[Icon: warning" in h_chunks[0].tables[0].headers[0].content_text
    assert "Warning description" in h_chunks[0].tables[0].headers[0].content_text


def test_list_node_chunking(settings):
    from app.schemas.ast_nodes import ListNode, ListItemNode, ListType

    root = DocumentNode(
        node_id="root",
        doc_metadata=DocumentMetadata(title="Test Doc with List"),
        children=[
            ListNode(
                node_id="list1",
                list_type=ListType.ORDERED,
                items=[
                    ListItemNode(node_id="item1", index=1, text="First step"),
                    ListItemNode(node_id="item2", index=2, text="Second step"),
                    ListItemNode(node_id="item3", index=None, text="Unordered bullet"),
                ],
            )
        ],
    )

    h_chunker = HierarchicalChunker(settings=settings)
    h_chunks = h_chunker.chunk(root)
    assert len(h_chunks) == 1
    assert "1. First step" in h_chunks[0].content
    assert "2. Second step" in h_chunks[0].content
    assert "- Unordered bullet" in h_chunks[0].content
