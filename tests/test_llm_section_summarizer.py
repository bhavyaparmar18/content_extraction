"""Unit tests for Mode B LLMSectionSummarizer with mocked LLM."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.schemas.migration import (
    DocxMigrationOutput,
    MigrationMetadata,
    MigrationSection,
    MigrationElement,
)
from app.services.llm.chain_factory import ChainFactory
from app.services.llm.rate_limiter import LLMRateLimiter
from app.services.migration.llm_section_summarizer import LLMSectionSummarizer
from app.services.migration.schemas import LLMSectionProfile, LLMElementDescriptor


@pytest.fixture
def mock_chain_factory():
    factory = MagicMock(spec=ChainFactory)

    profile = LLMSectionProfile(
        semantic_purpose="Defines core language and writing standards for SOP authors.",
        taxonomy_category="Technical Guidelines",
        key_topics=["Active Voice", "Brevity", "Simplified Writing"],
        element_descriptors=[
            LLMElementDescriptor(
                element_index=0,
                semantic_role="section_heading",
                summary="Subsection heading for Language and Wording",
            ),
            LLMElementDescriptor(
                element_index=1,
                semantic_role="callout_box",
                summary="Executive Summary callout box with writing tips",
                callout_candidate_type="executive_summary",
            ),
        ],
    )

    mock_structured_summarizer = MagicMock()
    mock_structured_summarizer.ainvoke = AsyncMock(return_value=profile)
    factory.create_structured_summarizer.return_value = mock_structured_summarizer

    return factory


@pytest.mark.asyncio
async def test_llm_section_summarizer_enrichment(mock_chain_factory):
    rate_limiter = LLMRateLimiter(max_concurrent=2, min_delay_seconds=0.01)
    summarizer = LLMSectionSummarizer(mock_chain_factory, rate_limiter)

    extracted = DocxMigrationOutput(
        document_id="test_doc_mode_b",
        sections=[
            MigrationSection(
                title="6 PRINCIPLES FOR DOCUMENT WRITING",
                section_number="6",
                elements=[
                    MigrationElement(element_type="heading", level=2, text="6.1 LANGUAGE"),
                    MigrationElement(element_type="paragraph", text="Executive Summary: Active voice is key."),
                ],
            )
        ],
    )

    summary = await summarizer.summarize(extracted, skip_preamble=True)

    assert summary.summarizer_mode == "llm_semantic"
    assert len(summary.sections) == 1
    sec = summary.sections[0]

    assert sec.semantic_purpose == "Defines core language and writing standards for SOP authors."
    assert sec.taxonomy_category == "Technical Guidelines"
    assert "Active Voice" in sec.key_topics

    # Verify element-level descriptors were enriched
    assert sec.elements[0].semantic_role == "section_heading"
    assert sec.elements[1].semantic_role == "callout_box"
    assert sec.elements[1].callout_candidate_type == "executive_summary"
