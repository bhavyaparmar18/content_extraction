"""LangChain model factory for SOP Content Migration.

Supports four provider paths — all controlled entirely through .env / Settings:

  Provider           | use_azure_openai | llm_planner_model (prefix)
  -------------------|------------------|---------------------------
  Google Gemini      | false            | "gemini/..."
  OpenAI             | false            | "openai/..."
  Anthropic          | false            | "anthropic/..."
  Azure OpenAI       | true             | (ignored — uses deployment names)

Azure routing:
  Set SOP_USE_AZURE_OPENAI=true and supply:
    AZURE_OPENAI_API_KEY        (read from env directly — no SOP_ prefix)
    SOP_AZURE_OPENAI_ENDPOINT   e.g. "https://<your-resource>.openai.azure.com/"
    SOP_AZURE_OPENAI_API_VERSION
    SOP_AZURE_OPENAI_PLANNER_DEPLOYMENT
    SOP_AZURE_OPENAI_SUMMARIZER_DEPLOYMENT
"""

from __future__ import annotations

import os
from typing import Any, Type
from pydantic import BaseModel
from langchain.chat_models import init_chat_model
from app.config.settings import Settings


class ChainFactory:
    """Creates configured LangChain chat models from application settings."""

    def __init__(self, settings: Settings):
        self.settings = settings

    # ── Public model constructors ─────────────────────────────────────────

    def create_planner_model(self) -> Any:
        """ChatModel for the global migration planner (Phase 2)."""
        if self.settings.use_azure_openai:
            return self._create_azure_model(
                deployment=self.settings.azure_openai_planner_deployment,
                max_tokens=self.settings.llm_planner_max_tokens,
            )
        return init_chat_model(
            model=self.settings.llm_planner_model,
            temperature=self.settings.llm_temperature,
            max_tokens=self.settings.llm_planner_max_tokens,
        )

    def create_summarizer_model(self) -> Any:
        """ChatModel for the per-section semantic summarizer (Mode B)."""
        if self.settings.use_azure_openai:
            return self._create_azure_model(
                deployment=self.settings.azure_openai_summarizer_deployment,
                max_tokens=self.settings.llm_summarizer_max_tokens,
            )
        return init_chat_model(
            model=self.settings.llm_summarizer_model,
            temperature=self.settings.llm_temperature,
            max_tokens=self.settings.llm_summarizer_max_tokens,
        )

    def create_structured_planner(self, output_schema: Type[BaseModel]) -> Any:
        """Planner with structured JSON output bound to a Pydantic schema."""
        return self.create_planner_model().with_structured_output(output_schema)

    def create_structured_summarizer(self, output_schema: Type[BaseModel]) -> Any:
        """Summarizer with structured JSON output bound to a Pydantic schema."""
        return self.create_summarizer_model().with_structured_output(output_schema)

    # ── Private helpers ───────────────────────────────────────────────────

    def _create_azure_model(self, deployment: str, max_tokens: int) -> Any:
        """Build an AzureChatOpenAI instance from settings and env variables."""
        from langchain_openai import AzureChatOpenAI

        api_key = self.settings.azure_openai_api_key or os.environ.get("AZURE_OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "AZURE_OPENAI_API_KEY environment variable is not set. "
                "Add it to your .env file without any SOP_ prefix."
            )

        endpoint = self.settings.azure_openai_endpoint
        if not endpoint:
            raise EnvironmentError(
                "SOP_AZURE_OPENAI_ENDPOINT is not configured. "
                "Set it to your Azure resource URL, e.g. "
                "'https://<your-resource>.openai.azure.com/'"
            )

        return AzureChatOpenAI(
            azure_endpoint=endpoint,
            azure_deployment=deployment,
            openai_api_version=self.settings.azure_openai_api_version,
            api_key=api_key,
            temperature=self.settings.llm_temperature,
            max_tokens=max_tokens,
        )
