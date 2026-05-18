"""评估配置管理 — 支持 OpenAI 兼容的自定义 LLM 端点

从 eval_config.json 加载评判 LLM 和 Embedding 配置，
创建 RAGAs 所需的 LLM / Embedding 包装器。

配置优先级：
    1. api_key 字段直接指定密钥
    2. api_key_env 字段指定环境变量名，运行时从环境变量读取
"""

import json
import os
import structlog

logger = structlog.get_logger(__name__)

_DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "eval_config.json"
)


def load_eval_config(config_path: str | None = None) -> dict:
    """加载评估配置文件。

    Args:
        config_path: 配置文件路径。默认读取 evals/eval_config.json。

    Returns:
        dict: 配置字典。
    """
    path = config_path or _DEFAULT_CONFIG_PATH
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"评估配置文件不存在: {path}\n"
            f"请复制 eval_config.json 模板并填写 API Key。"
        )

    with open(path, "r", encoding="utf-8") as f:
        config = json.load(f)

    logger.info("eval.config_loaded", path=path)
    return config


def _resolve_api_key(section: dict) -> str:
    """从配置段解析 API Key。

    优先使用 api_key 字段；若为空则从 api_key_env 指定的环境变量读取。
    """
    key = section.get("api_key", "")
    if key:
        return key

    env_var = section.get("api_key_env", "OPENAI_API_KEY")
    key = os.environ.get(env_var, "")
    if not key:
        raise ValueError(
            f"评估配置缺少 API Key：api_key 字段为空，"
            f"环境变量 {env_var} 也未设置。"
        )
    return key


def create_judge_llm(config: dict | None = None):
    """创建 RAGAs 评判 LLM 包装器。

    Args:
        config: 已加载的配置字典。如果为 None，则自动加载默认配置。

    Returns:
        LangchainLLMWrapper: RAGAs 兼容的 LLM 包装器。
    """
    if config is None:
        config = load_eval_config()

    llm_config = config.get("judge_llm", {})
    model = llm_config.get("model", "gpt-4o-mini")
    base_url = llm_config.get("base_url", "https://api.openai.com/v1")
    api_key = _resolve_api_key(llm_config)

    from langchain_openai import ChatOpenAI
    from ragas.llms import LangchainLLMWrapper

    llm = ChatOpenAI(
        model=model,
        base_url=base_url,
        api_key=api_key,
    )

    logger.info(
        "eval.judge_llm_created",
        model=model,
        base_url=base_url,
    )
    return LangchainLLMWrapper(llm)


def create_judge_embeddings(config: dict | None = None):
    """创建 RAGAs 评判 Embedding 包装器。

    Args:
        config: 已加载的配置字典。如果为 None，则自动加载默认配置。

    Returns:
        LangchainEmbeddingsWrapper: RAGAs 兼容的 Embedding 包装器。
    """
    if config is None:
        config = load_eval_config()

    emb_config = config.get("judge_embedding", {})
    model = emb_config.get("model", "text-embedding-3-small")
    base_url = emb_config.get("base_url", "https://api.openai.com/v1")
    api_key = _resolve_api_key(emb_config)

    from langchain_openai import OpenAIEmbeddings
    from ragas.embeddings import LangchainEmbeddingsWrapper

    embeddings = OpenAIEmbeddings(
        model=model,
        base_url=base_url,
        api_key=api_key,
    )

    logger.info(
        "eval.judge_embeddings_created",
        model=model,
        base_url=base_url,
    )
    return LangchainEmbeddingsWrapper(embeddings)
