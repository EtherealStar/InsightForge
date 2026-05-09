"""Rerank 重排序客户端，调用 Jina / SiliconFlow / Cohere 等 Cross-Encoder API

使用 Jina Reranker 兼容格式：POST {base_url}/rerank
请求体: {"model": "...", "query": "...", "documents": [...], "top_n": N}
响应体: {"results": [{"index": 0, "relevance_score": 0.95}, ...]}
"""

import structlog
from typing import Any

import requests

from core.retry import with_retry
from core.exceptions import RerankError

logger = structlog.get_logger(__name__)


class OpenAICompatibleRerankClient:
    """实现 RerankClientProtocol，调用 Jina/SiliconFlow 等 Rerank API。

    兼容以下 API 格式：
    - Jina Reranker: https://api.jina.ai/v1/rerank
    - SiliconFlow: https://api.siliconflow.cn/v1/rerank
    - Cohere: https://api.cohere.com/v2/rerank (需适配)
    """

    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        logger.info(f"RerankClient 已初始化: model={model}, base_url={self.base_url}")

    @with_retry(max_retries=2)
    def rerank(
        self, query: str, documents: list[str], top_n: int | None = None
    ) -> list[dict]:
        """对文档列表按与 query 的相关性重新排序。

        Args:
            query: 查询文本。
            documents: 待排序的文档文本列表。
            top_n: 返回前 N 条结果，None 则返回全部。

        Returns:
            [{"index": int, "relevance_score": float}, ...]
            按 relevance_score 降序排列。

        Raises:
            RerankError: API 调用失败。
        """
        if not documents:
            return []

        # 构建请求
        url = f"{self.base_url}/rerank"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "query": query,
            "documents": documents,
        }
        if top_n is not None:
            payload["top_n"] = top_n

        try:
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            raise RerankError(f"Rerank API 调用失败: {e}") from e

        # 解析响应
        raw_results = data.get("results", [])
        results = []
        for item in raw_results:
            results.append({
                "index": item["index"],
                "relevance_score": item.get("relevance_score", item.get("score", 0.0)),
            })

        # 按 relevance_score 降序排列
        results.sort(key=lambda x: x["relevance_score"], reverse=True)

        logger.info(
            f"Rerank 完成: {len(documents)} 篇文档 → "
            f"返回 {len(results)} 条结果"
        )
        return results
