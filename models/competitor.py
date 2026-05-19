"""竞品核心数据模型

定义竞品公司和产品线的领域实体与 DTO。
"""
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Competitor:
    """竞品公司实体"""

    name: str                         # 公司/产品名称（如 "Cursor"）
    website: str = ""                 # 官网 URL
    industry: str = ""                # 所属行业（如 "AI 编程工具"）
    description: str = ""             # 一句话描述
    aliases: list[str] = field(default_factory=list)   # 别名/简称（用于自动关联）
    logo_url: str = ""
    tags: list[str] = field(default_factory=list)      # 标签
    status: str = "active"            # active / archived

    # 数据库相关
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def matches_name(self, text: str) -> bool:
        """检查文本中是否包含此竞品的名称或别名（用于自动关联）。"""
        text_lower = text.lower()
        if self.name.lower() in text_lower:
            return True
        return any(alias.lower() in text_lower for alias in self.aliases)


@dataclass
class CompetitorProduct:
    """竞品产品线"""

    competitor_id: int
    name: str
    description: str = ""
    category: str = ""                # 产品类别（如 "IDE 插件"、"独立 IDE"）
    url: str = ""
    pricing_info: str = ""            # 定价信息摘要

    # 数据库相关
    id: int | None = None
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
