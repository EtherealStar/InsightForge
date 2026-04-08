"""统一异常层次"""


class NewsAssistantError(Exception):
    """基础异常"""


class CollectorError(NewsAssistantError):
    """抓取相关错误"""


class SourceUnavailableError(CollectorError):
    def __init__(self, source: str, reason: str):
        self.source = source
        super().__init__(f"来源 '{source}' 不可用: {reason}")


class StoreError(NewsAssistantError):
    """存储相关错误"""


class EmbeddingError(NewsAssistantError):
    """向量化相关错误"""


class LLMError(NewsAssistantError):
    """LLM 调用错误"""


class RateLimitError(LLMError):
    def __init__(self, retry_after: float = 60):
        self.retry_after = retry_after
        super().__init__(f"请求被限流，{retry_after}s 后重试")


class ConfigError(NewsAssistantError):
    """配置错误"""
