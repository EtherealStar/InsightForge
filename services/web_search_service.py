"""Web 搜索聚合服务 — 多引擎并发 + 程序化去重

多搜索引擎并发查询 → URL 标准化去重 → 关键信息提取 → 格式化输出。
不使用 LLM，纯程序化实现。
"""

import structlog
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from infrastructure.web_search_client import (
    DuckDuckGoSearchClient,
    TavilySearchClient,
    NewsAPISearchClient,
    WebSearchResult,
)

logger = structlog.get_logger(__name__)

# URL 中常见的追踪参数，去重时应忽略
_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "msclkid", "ref", "source",
}


class WebSearchService:
    """Web 搜索聚合服务 — 多引擎并发 + 程序化去重。

    工作流程：
        1. ThreadPoolExecutor 并发向所有可用引擎发起搜索
        2. 合并结果 + URL 标准化去重
        3. 格式化为 Agent 可读的结构化文本
    """

    def __init__(self, tavily_api_key: str = "", newsapi_api_key: str = ""):
        self._ddg_client = DuckDuckGoSearchClient()
        self._tavily_client = (
            TavilySearchClient(tavily_api_key) if tavily_api_key else None
        )
        self._newsapi_client = (
            NewsAPISearchClient(newsapi_api_key) if newsapi_api_key else None
        )

    def search_and_aggregate(
        self, query: str, max_results: int = 8
    ) -> str:
        """执行多引擎并发搜索，去重后返回格式化结果文本。

        Args:
            query: 搜索关键词。
            max_results: 每个搜索引擎的返回结果数量上限。

        Returns:
            str: 格式化的聚合搜索结果文本。
        """
        # 1. 并发搜索
        raw_results = self._concurrent_search(query, max_results)

        if not raw_results:
            return f"未找到与 \"{query}\" 相关的搜索结果。"

        # 2. 去重
        total_before = len(raw_results)
        deduplicated = self._deduplicate(raw_results)

        # 3. 统计引擎来源
        engines_used = set(r.source_engine for r in deduplicated)

        # 4. 格式化输出
        return self._format_results(
            query, deduplicated, engines_used, total_before
        )

    def _concurrent_search(
        self, query: str, max_results: int
    ) -> list[WebSearchResult]:
        """使用 ThreadPoolExecutor 并发向所有可用引擎发起搜索。"""
        all_results: list[WebSearchResult] = []
        futures = {}

        with ThreadPoolExecutor(max_workers=4) as executor:
            # DuckDuckGo — 始终参与
            futures[
                executor.submit(self._ddg_client.search, query, max_results)
            ] = "duckduckgo"

            # Tavily — 有 Key 时参与
            if self._tavily_client:
                futures[
                    executor.submit(
                        self._tavily_client.search, query, max_results
                    )
                ] = "tavily"

            # NewsAPI — 有 Key 时参与
            if self._newsapi_client:
                futures[
                    executor.submit(
                        self._newsapi_client.search, query, max_results
                    )
                ] = "newsapi"

            for future in as_completed(futures):
                engine_name = futures[future]
                try:
                    results = future.result(timeout=30)
                    all_results.extend(results)
                    logger.info(
                        f"[WebSearch] {engine_name} 返回 {len(results)} 条结果"
                    )
                except Exception as e:
                    logger.error(
                        f"[WebSearch] {engine_name} 搜索异常: {e}"
                    )

        logger.info(
            f"[WebSearch] 并发搜索完成，共 {len(all_results)} 条原始结果"
        )
        return all_results

    def _deduplicate(
        self, results: list[WebSearchResult]
    ) -> list[WebSearchResult]:
        """URL 标准化后去重，保留信息最丰富的条目。

        去重策略：
            1. URL 标准化（去除 tracking params、www. 前缀、trailing slash）
            2. 按 normalized URL 分组
            3. 同 URL 多条目时，优先保留有评分的、snippet 更长的条目
        """
        seen: dict[str, WebSearchResult] = {}

        for result in results:
            normalized = self._normalize_url(result.url)

            if normalized not in seen:
                seen[normalized] = result
            else:
                existing = seen[normalized]
                # 保留信息更丰富的条目
                if self._result_quality(result) > self._result_quality(
                    existing
                ):
                    seen[normalized] = result

        deduplicated = list(seen.values())
        removed_count = len(results) - len(deduplicated)
        if removed_count > 0:
            logger.info(
                f"[WebSearch] 去重: {len(results)} → {len(deduplicated)} "
                f"(移除 {removed_count} 条重复)"
            )
        return deduplicated

    @staticmethod
    def _normalize_url(url: str) -> str:
        """URL 标准化用于去重比较。

        处理：
            - 统一小写 scheme 和 host
            - 移除 www. 前缀
            - 移除 trailing slash
            - 移除常见 tracking 参数
        """
        try:
            parsed = urlparse(url)
            # 小写 scheme 和 host，移除 www.
            scheme = parsed.scheme.lower()
            netloc = parsed.netloc.lower().removeprefix("www.")
            # 移除 trailing slash
            path = parsed.path.rstrip("/")
            # 移除 tracking params
            clean_params = {
                k: v
                for k, v in parse_qs(parsed.query).items()
                if k.lower() not in _TRACKING_PARAMS
            }
            query_str = urlencode(clean_params, doseq=True) if clean_params else ""
            return urlunparse((scheme, netloc, path, "", query_str, ""))
        except Exception:
            return url

    @staticmethod
    def _result_quality(result: WebSearchResult) -> float:
        """计算搜索结果的"信息质量"分数，用于去重时选择保留哪条。"""
        score = 0.0
        # 有相关性评分的优先（Tavily 提供）
        if result.score is not None:
            score += result.score * 10
        # snippet 越长信息越丰富
        score += min(len(result.snippet), 500) / 100
        # 有发布日期的优先
        if result.published_date:
            score += 1.0
        # 有标题的优先
        if result.title:
            score += 0.5
        return score

    @staticmethod
    def _format_results(
        query: str,
        results: list[WebSearchResult],
        engines_used: set[str],
        total_before_dedup: int,
    ) -> str:
        """格式化为 Agent 可读的结构化文本。"""
        engines_str = ", ".join(sorted(engines_used))
        header = (
            f"搜索 \"{query}\" 共找到 {total_before_dedup} 条结果"
            f"（来自 {len(engines_used)} 个搜索引擎: {engines_str}，"
            f"去重后 {len(results)} 条）:\n"
        )

        parts = [header]
        for i, result in enumerate(results, 1):
            entry = f"\n{i}. {result.title}\n   URL: {result.url}"
            entry += f"\n   来源引擎: {result.source_engine}"
            if result.score is not None:
                entry += f" | 相关度: {result.score:.2f}"
            if result.published_date:
                entry += f" | 发布日期: {result.published_date}"
            if result.snippet:
                # 限制 snippet 长度
                snippet = result.snippet
                if len(snippet) > 300:
                    snippet = snippet[:300] + "..."
                entry += f"\n   摘要: {snippet}"
            parts.append(entry)

        return "\n".join(parts)
