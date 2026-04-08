from dataclasses import dataclass, field
from datetime import datetime
import os


@dataclass
class DailyBrief:
    """日报模型"""

    date: datetime
    content_markdown: str
    article_count: int = 0
    generated_at: datetime = field(default_factory=datetime.now)

    def save_to_file(self, output_dir: str) -> str:
        """保存为 Markdown 文件，返回文件路径"""
        os.makedirs(output_dir, exist_ok=True)
        filename = f"daily_brief_{self.date.strftime('%Y-%m-%d')}.md"
        path = os.path.join(output_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.content_markdown)
        return path
