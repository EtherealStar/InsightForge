"""Structured JSON extraction clients for fact extraction workloads."""
from __future__ import annotations

import json
import re
from typing import Any

import structlog

from core.exceptions import StructuredExtractionError
from core.retry import with_retry

logger = structlog.get_logger(__name__)


def parse_json_object_response(response: str, schema_name: str = "json_object") -> dict[str, Any]:
    """Parse a model response that must contain a single JSON object."""
    text = (response or "").strip()
    if not text:
        raise StructuredExtractionError(f"{schema_name} 返回为空")

    fence = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise StructuredExtractionError(
                f"{schema_name} 响应不是有效 JSON object"
            )
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError as exc:
            raise StructuredExtractionError(
                f"{schema_name} 响应 JSON 解析失败: {exc}"
            ) from exc

    if not isinstance(parsed, dict):
        raise StructuredExtractionError(
            f"{schema_name} 响应必须是 JSON object，实际为 {type(parsed).__name__}"
        )
    return parsed


def _with_json_instruction(system_prompt: str, schema_name: str) -> str:
    return (
        f"{system_prompt.rstrip()}\n\n"
        f"Return only one valid JSON object for schema '{schema_name}'. "
        "Do not include markdown fences or explanatory text."
    )


class _OpenAIChatStructuredExtractionClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        max_tokens: int = 2048,
        base_url: str | None = None,
        default_temperature: float = 0.0,
    ):
        import openai

        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self.client = openai.OpenAI(**kwargs)
        self.model = model
        self.max_tokens = max_tokens
        self.default_temperature = default_temperature

    @with_retry(max_retries=2)
    def extract_json(
        self,
        system_prompt: str,
        user_message: str,
        *,
        schema_name: str,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        try:
            request_temperature = (
                self.default_temperature if temperature == 0.0 else temperature
            )
            kwargs: dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": _with_json_instruction(system_prompt, schema_name),
                    },
                    {"role": "user", "content": user_message},
                ],
                "temperature": request_temperature,
            }
            if self.max_tokens > 0:
                kwargs["max_tokens"] = self.max_tokens
            response = self.client.chat.completions.create(**kwargs)
            content = response.choices[0].message.content or ""
            return parse_json_object_response(content, schema_name=schema_name)
        except StructuredExtractionError:
            raise
        except Exception as exc:
            raise StructuredExtractionError(
                f"结构化抽取调用失败 ({schema_name}): {exc}"
            ) from exc


class OpenAICompatibleStructuredExtractionClient(_OpenAIChatStructuredExtractionClient):
    """OpenAI-compatible structured extraction API."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        max_tokens: int = 2048,
        default_temperature: float = 0.0,
    ):
        super().__init__(
            api_key=api_key,
            base_url=base_url,
            model=model,
            max_tokens=max_tokens,
            default_temperature=default_temperature,
        )


class OpenAIStructuredExtractionClient(_OpenAIChatStructuredExtractionClient):
    """Official OpenAI structured extraction API."""

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        max_tokens: int = 2048,
        default_temperature: float = 0.0,
    ):
        super().__init__(
            api_key=api_key,
            model=model,
            max_tokens=max_tokens,
            default_temperature=default_temperature,
        )


class GeminiStructuredExtractionClient:
    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.0-flash",
        max_tokens: int = 2048,
        default_temperature: float = 0.0,
    ):
        from google import genai

        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.default_temperature = default_temperature

    @with_retry(max_retries=2)
    def extract_json(
        self,
        system_prompt: str,
        user_message: str,
        *,
        schema_name: str,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        try:
            from google.genai import types

            request_temperature = (
                self.default_temperature if temperature == 0.0 else temperature
            )
            response = self.client.models.generate_content(
                model=self.model,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=_with_json_instruction(
                        system_prompt, schema_name
                    ),
                    temperature=request_temperature,
                    max_output_tokens=self.max_tokens,
                    response_mime_type="application/json",
                ),
            )
            return parse_json_object_response(response.text or "", schema_name=schema_name)
        except StructuredExtractionError:
            raise
        except Exception as exc:
            raise StructuredExtractionError(
                f"Gemini 结构化抽取失败 ({schema_name}): {exc}"
            ) from exc


class AnthropicStructuredExtractionClient:
    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 2048,
        default_temperature: float = 0.0,
    ):
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens
        self.default_temperature = default_temperature

    @with_retry(max_retries=2)
    def extract_json(
        self,
        system_prompt: str,
        user_message: str,
        *,
        schema_name: str,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        try:
            request_temperature = (
                self.default_temperature if temperature == 0.0 else temperature
            )
            message = self.client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=request_temperature,
                system=_with_json_instruction(system_prompt, schema_name),
                messages=[{"role": "user", "content": user_message}],
            )
            content = "".join(
                getattr(block, "text", "") for block in (message.content or [])
            )
            return parse_json_object_response(content, schema_name=schema_name)
        except StructuredExtractionError:
            raise
        except Exception as exc:
            raise StructuredExtractionError(
                f"Anthropic 结构化抽取失败 ({schema_name}): {exc}"
            ) from exc
