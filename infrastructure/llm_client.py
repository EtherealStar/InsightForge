"""封装多 LLM 后端调用，统一实现 LLMClientProtocol"""
import logging
from typing import Iterator

from core.retry import with_retry
from core.exceptions import LLMError, RateLimitError

logger = logging.getLogger(__name__)


class OpenAICompatibleClient:
    """OpenAI 格式自定义 API（默认后端）"""

    def __init__(self, api_key: str, base_url: str, model: str):
        import openai

        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    @with_retry(max_retries=2)
    def generate(self, system_prompt: str, user_message: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            raise LLMError(f"OpenAI 兼容 API 调用失败: {e}") from e

    def generate_stream(
        self, system_prompt: str, user_message: str
    ) -> Iterator[str]:
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                stream=True,
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            raise LLMError(f"OpenAI 兼容 API 流式调用失败: {e}") from e


class OpenAIClient:
    """GPT 官方 API"""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        import openai

        self.client = openai.OpenAI(api_key=api_key)
        self.model = model

    @with_retry(max_retries=2)
    def generate(self, system_prompt: str, user_message: str) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            raise LLMError(f"OpenAI API 调用失败: {e}") from e

    def generate_stream(
        self, system_prompt: str, user_message: str
    ) -> Iterator[str]:
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message},
                ],
                stream=True,
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            raise LLMError(f"OpenAI API 流式调用失败: {e}") from e


class GeminiClient:
    """Google Gemini 官方 API"""

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash"):
        from google import genai

        self.client = genai.Client(api_key=api_key)
        self.model = model

    @with_retry(max_retries=2)
    def generate(self, system_prompt: str, user_message: str) -> str:
        try:
            from google.genai import types

            response = self.client.models.generate_content(
                model=self.model,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                ),
            )
            return response.text or ""
        except Exception as e:
            raise LLMError(f"Gemini API 调用失败: {e}") from e

    def generate_stream(
        self, system_prompt: str, user_message: str
    ) -> Iterator[str]:
        try:
            from google.genai import types

            response = self.client.models.generate_content_stream(
                model=self.model,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                ),
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            raise LLMError(f"Gemini API 流式调用失败: {e}") from e


class AnthropicClient:
    """Claude 官方 API"""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        import anthropic

        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    @with_retry(max_retries=2)
    def generate(self, system_prompt: str, user_message: str) -> str:
        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            )
            return message.content[0].text if message.content else ""
        except Exception as e:
            raise LLMError(f"Anthropic API 调用失败: {e}") from e

    def generate_stream(
        self, system_prompt: str, user_message: str
    ) -> Iterator[str]:
        try:
            with self.client.messages.stream(
                model=self.model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                for text in stream.text_stream:
                    yield text
        except Exception as e:
            raise LLMError(f"Anthropic API 流式调用失败: {e}") from e
