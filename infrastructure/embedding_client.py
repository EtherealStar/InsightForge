"""Embedding 向量生成，使用 OpenAI 格式自定义 API"""
import logging

from core.protocols import EmbeddingClientProtocol
from core.retry import with_retry
from core.exceptions import EmbeddingError

logger = logging.getLogger(__name__)

_BATCH_SIZE = 50


class OpenAICompatibleEmbeddingClient:
    """实现 EmbeddingClientProtocol，调用 OpenAI 格式自定义 Embedding API"""

    def __init__(self, api_key: str, base_url: str, model: str):
        import openai

        self.client = openai.OpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    @with_retry(max_retries=2)
    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        批量生成向量。
        每次最多 50 条文本，超出自动分批。
        返回与 texts 顺序对应的向量列表。
        """
        if not texts:
            return []

        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), _BATCH_SIZE):
            batch = texts[i : i + _BATCH_SIZE]
            try:
                response = self.client.embeddings.create(
                    model=self.model, input=batch
                )
                # 按 index 排序确保顺序一致
                sorted_data = sorted(response.data, key=lambda x: x.index)
                batch_embeddings = [item.embedding for item in sorted_data]
                all_embeddings.extend(batch_embeddings)
            except Exception as e:
                raise EmbeddingError(
                    f"Embedding API 调用失败（批次 {i}）: {e}"
                ) from e

        logger.info(f"Embedding: 生成 {len(all_embeddings)} 个向量")
        return all_embeddings
