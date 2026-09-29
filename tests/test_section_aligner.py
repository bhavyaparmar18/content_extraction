"""Unit tests for SectionAligner and Migration API."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.services.llm.chain_factory import ChainFactory
from app.services.llm.rate_limiter import LLMRateLimiter
from app.services.migration.section_aligner import SectionAligner
from app.services.migration.schemas import (
    TemplateRawProfile,
    ContentSummary,
    MigrationPlan,
    SectionPlan,
)


@pytest.fixture
def mock_chain_factory():
    factory = MagicMock(spec=ChainFactory)
    plan = MigrationPlan(
        template_name="test.docx",
        section_plans=[
            SectionPlan(
                template_section_heading="1 PURPOSE",
                template_paragraph_indices_to_delete=[1],
            )
        ],
        overall_confidence=0.9,
    )
    mock_structured = MagicMock()
    mock_structured.ainvoke = AsyncMock(return_value=plan)
    factory.create_structured_planner.return_value = mock_structured
    return factory


@pytest.mark.asyncio
async def test_section_aligner(mock_chain_factory):
    rate_limiter = LLMRateLimiter(max_concurrent=1, min_delay_seconds=0.01)
    aligner = SectionAligner(mock_chain_factory, rate_limiter)

    t_prof = TemplateRawProfile(
        filename="test.docx",
        total_paragraphs=5,
        total_tables=1,
    )
    c_sum = ContentSummary(
        document_id="doc_1",
        total_sections=1,
    )

    plan = await aligner.create_migration_plan(t_prof, c_sum)
    assert plan.overall_confidence == 0.9
    assert len(plan.section_plans) == 1
    assert plan.section_plans[0].template_section_heading == "1 PURPOSE"

    # Verify messages passed to LLM
    mock_structured = mock_chain_factory.create_structured_planner.return_value
    assert mock_structured.ainvoke.call_count == 1
    messages = mock_structured.ainvoke.call_args[0][0]
    assert len(messages) == 2
    system_msg, human_msg = messages
    assert "You are a document migration planning engine" in system_msg.content
    assert "### 1. TARGET TEMPLATE INSTRUCTIONS & RULES:" in human_msg.content
    assert "### 2. TARGET TEMPLATE PROFILE:" in human_msg.content
    assert "test.docx" in human_msg.content
    assert "### 3. SOURCE CONTENT SUMMARY:" in human_msg.content
    assert "doc_1" in human_msg.content


def test_api_health():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
