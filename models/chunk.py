"""分块领域模型：子 Chunk 和父 ParentChunk

子 chunk 按 Markdown 章节结构切分 (≤512 token)，用于向量检索。
父 chunk (~1024 token) 完整包含若干子 chunk，用于 LLM 召回上下文。
"""
from dataclasses import dataclass, field


@dataclass
class Chunk:
    """子分块：按 Markdown 章节结构切分的语义单元

    每个子 chunk 最大 512 token，存入向量数据库用于语义检索。
    通过 parent_chunk_id 指向所属的父 chunk。

    Attributes:
        chunk_id: 唯一 ID, 格式 "{article_id}_c{index}"
        article_id: 所属文章 ID
        parent_chunk_id: 所属父 chunk ID
        content: 子 chunk 文本内容 (含标题上下文前缀)
        token_count: token 数
        doc_name: 文档名 (article.title)
        heading_path: 标题层级路径, 如 ["主标题", "第二节", "2.1 子节"]
        chunk_index: 在文章内的序号
        source: 新闻来源
        url: 文章 URL
    """

    chunk_id: str
    article_id: int
    parent_chunk_id: str
    content: str
    token_count: int

    # Metadata
    doc_name: str
    heading_path: list[str] = field(default_factory=list)
    chunk_index: int = 0
    source: str = ""
    url: str = ""


@dataclass
class ParentChunk:
    """父分块：包含若干连续子 chunk 的上下文窗口

    约 1024 token，完整包含若干子 chunk，不存在子 chunk 跨越边界的情况。
    父 chunk 之间通过共享尾部子 chunk 实现 ~100 token 的 overlap。
    存储在 PostgreSQL 中，检索时通过 parent_chunk_id 召回。

    Attributes:
        parent_chunk_id: 唯一 ID, 格式 "{article_id}_p{index}"
        article_id: 所属文章 ID
        content: 父 chunk 完整文本
        token_count: token 数
        child_chunk_ids: 包含的子 chunk ID 列表
        doc_name: 文档名
        source: 新闻来源
        url: 文章 URL
    """

    parent_chunk_id: str
    article_id: int
    content: str
    token_count: int
    child_chunk_ids: list[str] = field(default_factory=list)

    # 来源信息
    doc_name: str = ""
    source: str = ""
    url: str = ""
