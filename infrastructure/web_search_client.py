"""Web 搜索引擎客户端 — DuckDuckGo + Tavily + NewsAPI

提供统一的 WebSearchResult 数据模型和三个搜索引擎实现：
    DuckDuckGoSearchClient — 免费，无需 API Key
    TavilySearchClient     — 需要 API Key，搜索质量更高
    NewsAPISearchClient    — 需要 API Key，新闻搜索
"""

import structlog
from dataclasses import dataclass

logger = structlog.get_logger(__name__)


@dataclass
class WebSearchResult:
    """统一的搜索结果数据模型。"""

    title: str
    url: str
    snippet: str
    source_engine: str  # "duckduckgo" / "tavily" / "newsapi"
    published_date: str | None = None
    score: float | None = None  # Tavily 提供的相关性评分


class DuckDuckGoSearchClient:
    """DuckDuckGo 搜索客户端 — 免费，无需 API Key。"""

    def search(self, query: str, max_results: int = 8) -> list[WebSearchResult]:
        """执行 DuckDuckGo 文本搜索。

        Args:
            query: 搜索关键词。
            max_results: 最大返回结果数。

        Returns:
            list[WebSearchResult]: 搜索结果列表。
        """
        try:
            from ddgs import DDGS

            results: list[WebSearchResult] = []
            with DDGS() as ddgs:
                raw_results = ddgs.text(query, max_results=max_results)
                for item in raw_results:
                    results.append(
                        WebSearchResult(
                            title=item.get("title", ""),
                            url=item.get("href", ""),
                            snippet=item.get("body", ""),
                            source_engine="duckduckgo",
                        )
                    )

            logger.info(f"[DuckDuckGo] 搜索 '{query}' 返回 {len(results)} 条结果")
            return results

        except Exception as e:
            logger.error(f"[DuckDuckGo] 搜索失败: {e}")
            return []


class TavilySearchClient:
    """Tavily 搜索客户端 — 需要 API Key。"""

    def __init__(self, api_key: str):
        self._api_key = api_key

    def search(self, query: str, max_results: int = 8) -> list[WebSearchResult]:
        """执行 Tavily 搜索。

        Args:
            query: 搜索关键词。
            max_results: 最大返回结果数。

        Returns:
            list[WebSearchResult]: 搜索结果列表。
        """
        if not self._api_key:
            logger.warning("[Tavily] API Key 未配置，跳过搜索")
            return []

        try:
            from tavily import TavilyClient

            client = TavilyClient(api_key=self._api_key)
            response = client.search(query, max_results=max_results)

            results: list[WebSearchResult] = []
            for item in response.get("results", []):
                results.append(
                    WebSearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        snippet=item.get("content", ""),
                        source_engine="tavily",
                        score=item.get("score"),
                    )
                )

            logger.info(f"[Tavily] 搜索 '{query}' 返回 {len(results)} 条结果")
            return results

        except Exception as e:
            logger.error(f"[Tavily] 搜索失败: {e}")
            return []


class NewsAPISearchClient:
    """NewsAPI 搜索客户端 — 需要 API Key，新闻搜索。

    仅作为 web_search 工具的搜索引擎之一，不再暴露独立 API 页面。
    """

    def __init__(self, api_key: str):
        self._api_key = api_key

    def search(self, query: str, max_results: int = 8) -> list[WebSearchResult]:
        """执行 NewsAPI 新闻搜索。

        Args:
            query: 搜索关键词。
            max_results: 最大返回结果数。

        Returns:
            list[WebSearchResult]: 搜索结果列表。
        """
        if not self._api_key:
            return []

        try:
            from newsapi import NewsApiClient

            client = NewsApiClient(api_key=self._api_key)
            response = client.get_everything(
                q=query,
                language="en",
                sort_by="relevancy",
                page_size=min(max_results, 100),
            )

            results: list[WebSearchResult] = []
            for article in response.get("articles", [])[:max_results]:
                results.append(
                    WebSearchResult(
                        title=article.get("title", ""),
                        url=article.get("url", ""),
                        snippet=article.get("description", "") or "",
                        source_engine="newsapi",
                        published_date=article.get("publishedAt"),
                    )
                )

            logger.info(f"[NewsAPI] 搜索 '{query}' 返回 {len(results)} 条结果")
            return results

        except Exception as e:
            logger.error(f"[NewsAPI] 搜索失败: {e}")
            return []

