"""Mode B: Parallel LLM semantic section profiler."""

from __future__ import annotations

import asyncio
from typing import Optional
from loguru import logger
from langchain_core.messages import SystemMessage, HumanMessage

from app.schemas.migration import DocxMigrationOutput, MigrationSection
from app.services.llm.chain_factory import ChainFactory
from app.services.llm.rate_limiter import LLMRateLimiter
from app.services.llm.prompts.section_summarizer import SECTION_SUMMARIZER_SYSTEM_PROMPT
from app.services.migration.content_summarizer import ContentSummarizer
from app.services.migration.schemas import (
    ContentSummary,
    ContentSectionSummary,
    LLMSectionProfile,
)


class LLMSectionSummarizer:
    """Mode B — Parallel LLM semantic section profiler with rate-limiting and fallback."""

    def __init__(self, chain_factory: ChainFactory, rate_limiter: LLMRateLimiter):
        self._chain_factory = chain_factory
        self._rate_limiter = rate_limiter
        self._base_summarizer = ContentSummarizer()

    async def summarize(
        self,
        extracted: DocxMigrationOutput,
        skip_preamble: bool = True,
    ) -> ContentSummary:
        """Run parallel LLM section summarization across all sections."""
        logger.info(f"Summarizing extracted document '{extracted.document_id}' (Mode B: LLM semantic)")

        model = self._chain_factory.create_structured_summarizer(LLMSectionProfile)

        source_sections: list[MigrationSection] = []
        tasks = []

        for sec in extracted.sections:
            if skip_preamble and sec.title.strip().startswith("0 "):
                logger.debug(f"Skipping preamble section '{sec.title}' per configuration")
                continue

            source_sections.append(sec)
            tasks.append(
                self._rate_limiter.execute(
                    coro_factory=lambda s=sec: self._invoke_summarizer(model, s),
                    task_name=f"summarize:{sec.title[:30]}",
                )
            )

        logger.info(f"Dispatching {len(tasks)} parallel LLM section summarization tasks...")
        profiles: list[LLMSectionProfile | Exception] = await asyncio.gather(
            *tasks, return_exceptions=True
        )

        merged_sections: list[ContentSectionSummary] = []

        for sec, profile in zip(source_sections, profiles):
            base_summary = self._base_summarizer._summarize_section(sec)

            if isinstance(profile, Exception):
                logger.warning(
                    f"LLM summarization failed for section '{sec.title}': {profile}. "
                    f"Falling back to Mode A truncation summary for this section."
                )
            elif isinstance(profile, LLMSectionProfile):
                # Enrich with Mode B semantic intelligence
                base_summary.semantic_purpose = profile.semantic_purpose
                base_summary.taxonomy_category = profile.taxonomy_category
                base_summary.key_topics = profile.key_topics

                # Match element descriptors
                for desc in profile.element_descriptors:
                    if 0 <= desc.element_index < len(base_summary.elements):
                        base_summary.elements[desc.element_index].semantic_role = desc.semantic_role
                        base_summary.elements[desc.element_index].callout_candidate_type = desc.callout_candidate_type

            merged_sections.append(base_summary)

        doc_type = extracted.metadata.document_type if extracted.metadata else None

        return ContentSummary(
            document_id=extracted.document_id,
            document_type=doc_type,
            total_sections=len(merged_sections),
            summarizer_mode="llm_semantic",
            sections=merged_sections,
        )

    async def _invoke_summarizer(self, model, section: MigrationSection) -> LLMSectionProfile:
        """Call LLM with full section content JSON."""
        system_msg = SystemMessage(content=SECTION_SUMMARIZER_SYSTEM_PROMPT)
        human_msg = HumanMessage(content=section.model_dump_json(indent=2))
        return await model.ainvoke([system_msg, human_msg])
