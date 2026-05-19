"""Structured JSON judge clients for report quality reviews."""
from __future__ import annotations

from typing import Any

from infrastructure.structured_extraction_client import (
    AnthropicStructuredExtractionClient,
    GeminiStructuredExtractionClient,
    OpenAICompatibleStructuredExtractionClient,
    OpenAIStructuredExtractionClient,
)


class OpenAICompatibleJudgeClient(OpenAICompatibleStructuredExtractionClient):
    """OpenAI-compatible judge API with an independent configuration surface."""

    def judge_json(
        self,
        system_prompt: str,
        user_message: str,
        *,
        schema_name: str,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        return self.extract_json(
            system_prompt,
            user_message,
            schema_name=schema_name,
            temperature=temperature,
        )


class OpenAIJudgeClient(OpenAIStructuredExtractionClient):
    """Official OpenAI judge API."""

    def judge_json(
        self,
        system_prompt: str,
        user_message: str,
        *,
        schema_name: str,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        return self.extract_json(
            system_prompt,
            user_message,
            schema_name=schema_name,
            temperature=temperature,
        )


class GeminiJudgeClient(GeminiStructuredExtractionClient):
    """Gemini judge API."""

    def judge_json(
        self,
        system_prompt: str,
        user_message: str,
        *,
        schema_name: str,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        return self.extract_json(
            system_prompt,
            user_message,
            schema_name=schema_name,
            temperature=temperature,
        )


class AnthropicJudgeClient(AnthropicStructuredExtractionClient):
    """Anthropic judge API."""

    def judge_json(
        self,
        system_prompt: str,
        user_message: str,
        *,
        schema_name: str,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        return self.extract_json(
            system_prompt,
            user_message,
            schema_name=schema_name,
            temperature=temperature,
        )
