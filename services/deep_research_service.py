"""研究报告文件服务。

负责研究报告的持久化与文件 CRUD：
- 保存报告
- 列出报告
- 读取单份报告
- 删除报告
"""

import glob
import os
from datetime import datetime

# 默认研究报告输出目录
_DEFAULT_RESEARCH_DIR = os.path.join("output", "research")


class DeepResearchService:
    """研究报告持久化服务。"""

    def __init__(
        self,
        output_dir: str = _DEFAULT_RESEARCH_DIR,
    ):
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def save_report(self, topic: str, content: str) -> str:
        """将研究报告保存到文件系统。

        Args:
            topic: 研究主题（用于文件名）。
            content: 报告 Markdown 内容。

        Returns:
            str: 保存的文件路径。
        """
        # 生成安全文件名
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        safe_topic = "".join(
            c if c.isalnum() or c in " _-" else "_" for c in topic[:30]
        ).strip().replace(" ", "_")

        filename = f"research_{timestamp}_{safe_topic}.md"
        filepath = os.path.join(self.output_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)

        return filepath

    def list_reports(self) -> list[dict]:
        """列出所有研究报告文件。

        Returns:
            list[dict]: 报告列表，包含 filename, date, size_bytes 等。
        """
        if not os.path.exists(self.output_dir):
            return []

        report_files = sorted(
            glob.glob(os.path.join(self.output_dir, "research_*.md")),
            reverse=True,
        )

        reports = []
        for filepath in report_files:
            filename = os.path.basename(filepath)
            mod_time = datetime.fromtimestamp(os.path.getmtime(filepath))
            reports.append({
                "filename": filename,
                "generated_at": mod_time.isoformat(),
                "size_bytes": os.path.getsize(filepath),
            })

        return reports

    def get_report(self, filename: str) -> dict | None:
        """获取单份研究报告内容。

        Args:
            filename: 报告文件名。

        Returns:
            dict: {filename, content, generated_at} 或 None。
        """
        filepath = os.path.join(self.output_dir, filename)
        if not os.path.exists(filepath):
            return None

        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()

        mod_time = datetime.fromtimestamp(os.path.getmtime(filepath))
        return {
            "filename": filename,
            "content": content,
            "generated_at": mod_time.isoformat(),
        }

    def delete_report(self, filename: str) -> bool:
        """删除一份研究报告。

        Returns:
            bool: 是否成功删除。
        """
        filepath = os.path.join(self.output_dir, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False
