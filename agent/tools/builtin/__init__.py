"""内置工具集 — 注册所有内置 Agent 工具

提供 register_builtin_tools() 函数，在应用启动时
从 ConfigManager 获取依赖，构造并注册所有内置工具。
"""

import structlog
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.config_manager import ConfigManager

logger = structlog.get_logger(__name__)


def register_builtin_tools(config_manager: "ConfigManager") -> int:
    """构造并注册所有内置工具到全局 ToolRegistry。

    Args:
        config_manager: 应用配置管理器（提供组件依赖）。

    Returns:
        int: 成功注册的工具数量。
    """
    from agent.tools.registry import get_tool_registry
    from agent.tools.builtin.query_knowledge_base import QueryKnowledgeBaseTool
    from agent.tools.builtin.get_recent_news import GetRecentNewsTool
    from agent.tools.builtin.get_news_stats import GetNewsStatsTool
    from agent.tools.builtin.generate_brief import GenerateBriefTool
    from agent.tools.builtin.web_search import WebSearchTool
    from agent.tools.builtin.read_article import ReadArticleTool

    registry = get_tool_registry()
    registered = 0

    # 获取共享组件
    article_store = config_manager.article_store
    vector_store = config_manager.vector_store
    llm_client = config_manager.llm_client
    embedding_client = config_manager.embedding_client
    rerank_client = config_manager.rerank_client
    output_path = config_manager.config.output_path

    # 逐个注册，单个失败不影响其他工具
    tools_to_register = []

    if embedding_client and vector_store:
        # 构造混合检索服务
        hybrid_search = None
        if config_manager.config.hybrid_search_enabled:
            try:
                from infrastructure.keyword_search_service import KeywordSearchService
                from infrastructure.hybrid_search_service import HybridSearchService

                keyword_search = KeywordSearchService(article_store)
                hybrid_search = HybridSearchService(
                    vector_store=vector_store,
                    embedding_client=embedding_client,
                    article_store=article_store,
                    keyword_search_service=keyword_search,
                    rrf_k=config_manager.config.hybrid_rrf_k,
                )
                logger.info("混合检索服务已构造 (向量+关键词+RRF)")
            except Exception as e:
                logger.warning(f"混合检索服务构造失败，退化为纯向量检索: {e}")

        tools_to_register.append(
            QueryKnowledgeBaseTool(
                embedding_client,
                vector_store,
                article_store,
                rerank_client=rerank_client,
                rerank_enabled=config_manager.config.rerank_enabled,
                rerank_top_k_multiplier=config_manager.config.rerank_top_k_multiplier,
                hybrid_search_service=hybrid_search,
                hybrid_search_enabled=config_manager.config.hybrid_search_enabled,
            )
        )
    else:
        logger.warning("跳过 query_knowledge_base 工具注册: Embedding 或 VectorStore 未就绪")

    tools_to_register.append(GetRecentNewsTool(article_store))
    tools_to_register.append(GetNewsStatsTool(article_store))
    tools_to_register.append(ReadArticleTool(article_store))

    if llm_client:
        tools_to_register.append(
            GenerateBriefTool(article_store, llm_client, output_path)
        )
    else:
        logger.warning("跳过 generate_brief 工具注册: LLM 客户端未就绪")

    # web_search 工具不依赖 LLM，始终注册
    tools_to_register.append(WebSearchTool(config_manager))

    for tool in tools_to_register:
        try:
            if not registry.has(tool.name):
                registry.register(tool)
                registered += 1
                logger.info(f"内置工具已注册: {tool.name}")
            else:
                logger.debug(f"工具 {tool.name} 已存在，跳过注册")
        except Exception as e:
            logger.error(f"注册内置工具 {tool.name} 失败: {e}")

    logger.info(f"内置工具注册完成: {registered} 个工具")
    return registered

