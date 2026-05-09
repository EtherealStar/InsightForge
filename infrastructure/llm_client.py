"""封装多 LLM 后端调用，统一实现 LLMClientProtocol"""
import structlog
from typing import Iterator

from core.retry import with_retry
from core.exceptions import LLMError, RateLimitError

logger = structlog.get_logger(__name__)


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

    @with_retry(max_retries=2)
    def generate_with_history(self, messages: list[dict]) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            raise LLMError(f"OpenAI 兼容 API 多轮对话失败: {e}") from e

    def generate_with_history_stream(
        self, messages: list[dict]
    ) -> Iterator[str]:
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            raise LLMError(f"OpenAI 兼容 API 多轮流式失败: {e}") from e


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

    @with_retry(max_retries=2)
    def generate_with_history(self, messages: list[dict]) -> str:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            raise LLMError(f"OpenAI API 多轮对话失败: {e}") from e

    def generate_with_history_stream(
        self, messages: list[dict]
    ) -> Iterator[str]:
        try:
            stream = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                stream=True,
            )
            for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            raise LLMError(f"OpenAI API 多轮流式失败: {e}") from e


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

    @staticmethod
    def _convert_messages_for_gemini(messages: list[dict]):
        """将 OpenAI 格式消息转换为 Gemini 格式。"""
        from google.genai import types

        system_instruction = None
        contents = []

        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                system_instruction = content
            elif role == "user":
                contents.append(types.Content(
                    role="user",
                    parts=[types.Part(text=content)],
                ))
            elif role == "assistant":
                contents.append(types.Content(
                    role="model",
                    parts=[types.Part(text=content)],
                ))

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
        ) if system_instruction else None

        return contents, config

    @with_retry(max_retries=2)
    def generate_with_history(self, messages: list[dict]) -> str:
        try:
            contents, config = self._convert_messages_for_gemini(messages)
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
            )
            return response.text or ""
        except Exception as e:
            raise LLMError(f"Gemini API 多轮对话失败: {e}") from e

    def generate_with_history_stream(
        self, messages: list[dict]
    ) -> Iterator[str]:
        try:
            contents, config = self._convert_messages_for_gemini(messages)
            response = self.client.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=config,
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            raise LLMError(f"Gemini API 多轮流式失败: {e}") from e


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

    @staticmethod
    def _convert_messages_for_anthropic(messages: list[dict]):
        """将 OpenAI 格式消息转换为 Anthropic 格式。"""
        system = None
        conversation = []

        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            if role == "system":
                system = content
            else:
                conversation.append({"role": role, "content": content})

        return system, conversation

    @with_retry(max_retries=2)
    def generate_with_history(self, messages: list[dict]) -> str:
        try:
            system, conversation = self._convert_messages_for_anthropic(messages)
            kwargs = {
                "model": self.model,
                "max_tokens": 4096,
                "messages": conversation,
            }
            if system:
                kwargs["system"] = system
            message = self.client.messages.create(**kwargs)
            return message.content[0].text if message.content else ""
        except Exception as e:
            raise LLMError(f"Anthropic API 多轮对话失败: {e}") from e

    def generate_with_history_stream(
        self, messages: list[dict]
    ) -> Iterator[str]:
        try:
            system, conversation = self._convert_messages_for_anthropic(messages)
            kwargs = {
                "model": self.model,
                "max_tokens": 4096,
                "messages": conversation,
            }
            if system:
                kwargs["system"] = system
            with self.client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    yield text
        except Exception as e:
            raise LLMError(f"Anthropic API 多轮流式失败: {e}") from e
