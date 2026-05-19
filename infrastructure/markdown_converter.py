"""HTML → Markdown 新闻转换器

使用 markdownify 将 HTML 内容转为 Markdown 格式，
同时提取作者等元数据，组装 YAML Front Matter。
"""
import json
import structlog
import os
import re
import hashlib
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import yaml
from bs4 import BeautifulSoup, Tag
from markdownify import markdownify as md

from models.article import Article

logger = structlog.get_logger(__name__)

# 需要被 decompose（标签 + 内容一起删除）的标签
_TAGS_TO_REMOVE = [
    "script", "style", "nav", "footer", "header",
    "aside", "noscript", "iframe", "svg", "form",
]

# 匹配常见的非正文 class / id 名（导航、社交、广告等）
_NOISE_CLASS_RE = re.compile(
    r"nav|menu|sidebar|share|social|comment|related|recommend|"
    r"footer|cookie|banner|ads|popup|modal|subscribe|signup|"
    r"newsletter|pagination|breadcrumb|sider|download|app|qrcode|"
    r"beian|copyright|matrix|feedback|report|hot|rank|common_sider",
    re.I,
)

_THEPAPER_CONTENT_SELECTORS = [
    "div.news_txt",
    "div.index_cententWrap__Jv8jK",
    "div[class*='news_txt']",
    "div[class*='cententWrap']",
    "main",
]

_THEPAPER_NOISE_SELECTORS = [
    ".common_sider",
    "[class*='common_sider']",
    "[class*='download']",
    "[class*='app']",
    "[class*='footer']",
    "[class*='matrix']",
    "[class*='feedback']",
    "[class*='report']",
    "[class*='hot']",
    "[class*='rank']",
]

_THEPAPER_FOOTER_START_RE = re.compile(
    r"(?m)^(?:#{1,6}\s*)?(?:\*\*)?扫码下载(?:\*\*)?(?:\*\*)?澎湃新闻客户端(?:\*\*)?.*$"
)

_THEPAPER_NOISE_LINE_RE = re.compile(
    r"Android版|iPhone版|iPad版|关于澎湃|加入澎湃|联系我们|广告合作|法律声明|隐私政策|"
    r"澎湃矩阵|澎湃新闻微博|澎湃新闻公众号|澎湃新闻抖音号|新闻报料|报料热线|报料邮箱|"
    r"沪ICP备|沪公网安备|互联网新闻信息服务许可证|增值电信业务经营许可证|"
    r"上海东方报业有限公司|beian\.miit\.gov\.cn|beian\.gov\.cn|yunaq\.com|反馈",
    re.I,
)


class NewsMarkdownConverter:
    """将新闻文章的 HTML 内容转换为结构化的 Markdown 格式"""

    def convert_article(self, article: Article) -> Article:
        """
        将文章的 HTML/纯文本内容转为 Markdown 格式，提取元数据。

        流程：
        1. 从 HTML 中提取元数据（作者、发布时间、标签）—— 必须在清理前
        2. 清理 HTML（移除 script/style/nav 等非正文元素）
        3. 定位正文容器 → markdownify 转换
        4. 回退到 content（纯文本）

        转换完成后：
        - article.content = Markdown 格式正文
        - article.html_content = ""（清空，不再保留）
        - article.author / published_at / tags 补充元数据

        Args:
            article: 原始 Article 对象

        Returns:
            更新后的 Article 对象（原地修改）
        """
        html = article.html_content
        plain = article.content

        # Step 1: 从原始 HTML 提取元数据（在清理 HTML 之前！）
        if html:
            metadata = self._extract_metadata_from_html(html)
            if metadata.get("author") and not article.author:
                article.author = metadata["author"]
            if metadata.get("published_at") and not article.published_at:
                article.published_at = metadata["published_at"]
            if metadata.get("tags") and not article.tags:
                article.tags = metadata["tags"]

        # Step 2: 转换内容为 Markdown
        if html and html.strip():
            markdown_content = self._html_to_markdown(
                html,
                source=article.source,
                url=article.url,
                content_selector=getattr(article, "content_selector", None),
                noise_selectors=getattr(article, "noise_selectors", None),
            )
        elif plain and plain.strip():
            # 纯文本本身就可视为 Markdown，但做基本清理
            markdown_content = self._sanitize_markdown(plain)
        else:
            markdown_content = ""

        # 更新文章字段
        article.content = markdown_content
        article.html_content = ""  # 不再保留 HTML

        return article

    def convert_batch(self, articles: list[Article]) -> list[Article]:
        """
        批量转换文章为 Markdown 格式。

        每篇文章独立 try/except，单篇失败不影响整批。
        """
        converted = 0
        for article in articles:
            try:
                self.convert_article(article)
                converted += 1
            except Exception as e:
                logger.warning(
                    f"Markdown 转换失败: '{article.title[:50]}' — {e}"
                )
        logger.info(f"Markdown 转换完成: {converted}/{len(articles)} 篇")
        return articles

    def save_as_file(self, article: Article, base_dir: str) -> Path | None:
        """
        将文章保存为带 YAML Front Matter 的 .md 文件。

        目录结构: base_dir/YYYY-MM-DD/{source}_{title_slug}_{hash}.md

        Args:
            article: 已转换为 Markdown 的 Article
            base_dir: 输出根目录

        Returns:
            生成的文件路径，失败返回 None
        """
        try:
            # 按日期建子目录
            date_str = (
                article.published_at.strftime("%Y-%m-%d")
                if article.published_at
                else datetime.now().strftime("%Y-%m-%d")
            )
            dir_path = Path(base_dir) / date_str
            dir_path.mkdir(parents=True, exist_ok=True)

            # 生成文件名
            filename = self._generate_filename(article)
            file_path = dir_path / filename

            # 组装 Front Matter
            front_matter = self._build_front_matter(article)
            yaml_str = yaml.dump(
                front_matter,
                allow_unicode=True,
                default_flow_style=False,
                sort_keys=False,
            )

            # 写入文件
            full_content = f"---\n{yaml_str}---\n\n{article.content}"
            file_path.write_text(full_content, encoding="utf-8")

            logger.debug(f"Markdown 文件已保存: {file_path}")
            return file_path

        except Exception as e:
            logger.warning(
                f"Markdown 文件保存失败: '{article.title[:50]}' — {e}"
            )
            return None

    def save_batch_as_files(
        self, articles: list[Article], base_dir: str
    ) -> list[Path]:
        """批量保存为 Markdown 文件，返回成功保存的路径列表"""
        paths = []
        for article in articles:
            path = self.save_as_file(article, base_dir)
            if path:
                paths.append(path)
        logger.info(
            f"Markdown 文件保存完成: {len(paths)}/{len(articles)} 篇"
        )
        return paths

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _html_to_markdown(
        self,
        html: str,
        source: str = "",
        url: str = "",
        content_selector: str | None = None,
        noise_selectors: list[str] | None = None,
    ) -> str:
        """
        将 HTML 转为 Markdown，包含正文提取和预清理。

        流程：
        1. BeautifulSoup 解析
        2. 定位正文容器（article / main / 常见 class）
        3. decompose 非正文标签（script/style/nav 等及其内容）
        4. markdownify 转换
        """
        try:
            soup = BeautifulSoup(html, "html.parser")
            site_key = _detect_site_key(source, url)

            # 1. 尝试定位正文容器，缩小转换范围
            body = self._find_content_root(
                soup,
                site_key=site_key,
                content_selector=content_selector,
            )

            # 2. 彻底移除非正文标签（标签 + 内容一起删除）
            self._remove_noise_elements(
                body,
                site_key=site_key,
                noise_selectors=noise_selectors,
            )

            # 3. 转换清理后的 HTML
            cleaned_html = str(body)
            markdown_text = md(
                cleaned_html,
                heading_style="ATX",
                wrap=False,
            )
            return self._sanitize_markdown(markdown_text, site_key=site_key)

        except Exception as e:
            logger.warning(f"markdownify 转换异常，回退到纯文本提取: {e}")
            # 回退：用 BeautifulSoup 提取纯文本
            try:
                soup = BeautifulSoup(html, "html.parser")
                site_key = _detect_site_key(source, url)
                self._remove_noise_elements(
                    soup,
                    site_key=site_key,
                    noise_selectors=noise_selectors,
                )
                return self._sanitize_markdown(
                    soup.get_text(separator="\n"),
                    site_key=site_key,
                )
            except Exception:
                return ""

    @staticmethod
    def _find_content_root(
        soup: BeautifulSoup,
        site_key: str = "",
        content_selector: str | None = None,
    ) -> BeautifulSoup | Tag:
        """
        尝试定位 HTML 中的正文容器。

        搜索优先级：
        1. <article> 标签
        2. <main> 标签
        3. 常见正文 class（post-content, article-body, entry-content 等）
        4. 回退到整个 soup
        """
        selectors = []
        if content_selector:
            selectors.append(content_selector)
        if site_key == "thepaper":
            selectors.extend(_THEPAPER_CONTENT_SELECTORS)

        for selector in selectors:
            try:
                content = soup.select_one(selector)
            except Exception:
                continue
            if content and content.get_text(strip=True):
                return content

        # 优先 <article>
        article_tag = soup.find("article")
        if article_tag:
            return article_tag

        # 其次 <main>
        main_tag = soup.find("main")
        if main_tag:
            return main_tag

        # 常见 CMS 正文 class
        content_class_re = re.compile(
            r"post-content|article-body|entry-content|"
            r"gh-content|post-body|article-content|"
            r"content-body|story-body|news-content",
            re.I,
        )
        content_div = soup.find(class_=content_class_re)
        if content_div:
            return content_div

        # 回退到整个 soup
        return soup

    @staticmethod
    def _remove_noise_elements(
        soup: BeautifulSoup | Tag,
        site_key: str = "",
        noise_selectors: list[str] | None = None,
    ) -> None:
        """
        从 soup 中彻底移除非正文元素（decompose = 标签 + 内容一起删除）。

        移除对象：
        - script / style / nav / footer / header 等标签
        - JSON-LD <script type="application/ld+json">
        - 包含导航/社交/广告等 class 的 div
        """
        # 移除指定标签（含内容）
        for tag in soup.find_all(_TAGS_TO_REMOVE):
            tag.decompose()

        selectors = list(noise_selectors or [])
        if site_key == "thepaper":
            selectors.extend(_THEPAPER_NOISE_SELECTORS)

        for selector in selectors:
            try:
                tags = list(soup.select(selector))
            except Exception:
                continue
            for tag in tags:
                tag.decompose()

        # 移除包含噪音 class 的元素
        for tag in soup.find_all(class_=_NOISE_CLASS_RE):
            tag.decompose()

        # 移除包含噪音 id 的元素
        for tag in soup.find_all(id=_NOISE_CLASS_RE):
            tag.decompose()

    def _extract_metadata_from_html(self, html: str) -> dict:
        """
        从原始 HTML 中提取元数据（在清理 HTML 之前调用）。

        提取来源（按优先级）：
        1. JSON-LD (<script type="application/ld+json">)
        2. <meta> 标签 (Open Graph / article / Dublin Core)
        3. HTML 元素 (<a rel="author">, <span class="author"> 等)

        Returns:
            {
                "author": str | None,
                "published_at": datetime | None,
                "tags": list[str],
            }
        """
        result: dict = {"author": None, "published_at": None, "tags": []}

        try:
            soup = BeautifulSoup(html, "html.parser")

            # 1. 从 JSON-LD 提取（最丰富的元数据源）
            self._extract_from_jsonld(soup, result)

            # 2. 从 <meta> 标签补充
            self._extract_from_meta_tags(soup, result)

            # 3. 从 HTML 元素补充作者
            if not result["author"]:
                result["author"] = self._extract_author_from_elements(soup)

        except Exception as e:
            logger.debug(f"元数据提取失败: {e}")

        return result

    @staticmethod
    def _extract_from_jsonld(soup: BeautifulSoup, result: dict) -> None:
        """从 JSON-LD <script type="application/ld+json"> 提取元数据"""
        for script_tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script_tag.string or "")
            except (json.JSONDecodeError, TypeError):
                continue

            # 支持 @graph 数组格式
            items = data if isinstance(data, list) else [data]
            if isinstance(data, dict) and "@graph" in data:
                items = data["@graph"]

            for item in items:
                if not isinstance(item, dict):
                    continue

                # 作者
                if not result["author"]:
                    author_obj = item.get("author")
                    if isinstance(author_obj, dict):
                        result["author"] = author_obj.get("name", "")
                    elif isinstance(author_obj, str):
                        result["author"] = author_obj
                    elif isinstance(author_obj, list) and author_obj:
                        first = author_obj[0]
                        if isinstance(first, dict):
                            result["author"] = first.get("name", "")
                        elif isinstance(first, str):
                            result["author"] = first

                # 发布时间
                if not result["published_at"]:
                    date_str = item.get("datePublished") or item.get("dateCreated")
                    if date_str:
                        result["published_at"] = _parse_datetime(date_str)

                # 标签 / 关键词
                if not result["tags"]:
                    keywords = item.get("keywords")
                    if isinstance(keywords, str):
                        result["tags"] = [
                            k.strip() for k in keywords.split(",") if k.strip()
                        ]
                    elif isinstance(keywords, list):
                        result["tags"] = [
                            str(k).strip() for k in keywords if str(k).strip()
                        ]

    @staticmethod
    def _extract_from_meta_tags(soup: BeautifulSoup, result: dict) -> None:
        """从 <meta> 标签提取元数据"""
        # 作者
        if not result["author"]:
            author_metas = [
                ("meta", {"name": "author"}),
                ("meta", {"property": "article:author"}),
                ("meta", {"property": "og:article:author"}),
                ("meta", {"name": "dc.creator"}),
            ]
            for tag_name, attrs in author_metas:
                tag = soup.find(tag_name, attrs)
                if tag and tag.get("content"):
                    result["author"] = tag["content"].strip()
                    break

        # 发布时间
        if not result["published_at"]:
            date_metas = [
                ("meta", {"property": "article:published_time"}),
                ("meta", {"name": "publishdate"}),
                ("meta", {"name": "publish_date"}),
                ("meta", {"property": "og:article:published_time"}),
            ]
            for tag_name, attrs in date_metas:
                tag = soup.find(tag_name, attrs)
                if tag and tag.get("content"):
                    dt = _parse_datetime(tag["content"].strip())
                    if dt:
                        result["published_at"] = dt
                        break

        # 标签
        if not result["tags"]:
            # article:tag 可能出现多次
            tag_metas = soup.find_all("meta", property="article:tag")
            if tag_metas:
                result["tags"] = [
                    t["content"].strip()
                    for t in tag_metas
                    if t.get("content")
                ]

            # 回退到 <meta name="keywords">
            if not result["tags"]:
                kw_meta = soup.find("meta", {"name": "keywords"})
                if kw_meta and kw_meta.get("content"):
                    result["tags"] = [
                        k.strip()
                        for k in kw_meta["content"].split(",")
                        if k.strip()
                    ]

    @staticmethod
    def _extract_author_from_elements(soup: BeautifulSoup) -> str:
        """从 HTML 元素中提取作者信息（最后的回退手段）"""
        # <a rel="author">
        author_link = soup.find("a", rel="author")
        if author_link:
            text = author_link.get_text(strip=True)
            if text:
                return text

        # <span class="author"> 或类似
        for class_name in ["author", "byline", "author-name"]:
            author_el = soup.find(class_=re.compile(class_name, re.I))
            if author_el:
                text = author_el.get_text(strip=True)
                if text and len(text) < 100:  # 避免误提取大段文本
                    return text

        return ""

    @staticmethod
    def _sanitize_markdown(text: str, site_key: str = "") -> str:
        """
        清理 Markdown 文本：
        - 确保标题前后有空行，以便正确渲染
        - 去除超过 2 个的连续空行
        - 去除行尾多余空格
        - 去除开头和结尾空行
        """
        if not text:
            return ""

        if site_key == "thepaper":
            text = _sanitize_thepaper_markdown(text)

        # 去除行尾空格
        lines = [line.rstrip() for line in text.splitlines()]
        text = "\n".join(lines)

        # 确保标题前后有换行符
        # 使用正则拆分代码块，仅在非代码块中处理标题
        parts = re.split(r'(```.*?```)', text, flags=re.DOTALL)
        for i in range(len(parts)):
            if i % 2 == 0:  # 非代码块部分
                parts[i] = re.sub(r'(?m)^#{1,6}\s+.*$', r'\n\n\g<0>\n\n', parts[i])
            else:
                parts[i] = f"\n\n{parts[i].strip()}\n\n"
        text = "".join(parts)

        # 将 3 个及以上连续空行缩减为 2 个
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text.strip()

    @staticmethod
    def _generate_filename(article: Article) -> str:
        """
        生成安全的文件名：{source}_{title_slug}_{hash}.md

        - source: 来源名，清理非法字符
        - title_slug: 标题前30字符，清理非法字符
        - hash: URL SHA256 前6位，确保唯一性
        """
        # 清理 source
        source_slug = re.sub(r"[^\w\u4e00-\u9fff-]", "", article.source or "unknown")
        source_slug = source_slug[:20]

        # 清理 title
        title_slug = re.sub(r"[^\w\u4e00-\u9fff-]", "", article.title or "untitled")
        title_slug = title_slug[:30]

        # URL hash
        url_hash = hashlib.sha256(
            article.url.encode("utf-8")
        ).hexdigest()[:6]

        return f"{source_slug}_{title_slug}_{url_hash}.md"

    @staticmethod
    def _build_front_matter(article: Article) -> dict:
        """构建 YAML Front Matter 字典"""
        return {
            "title": article.title,
            "url": article.url,
            "source": article.source or "",
            "author": article.author or "",
            "published_at": (
                article.published_at.strftime("%Y-%m-%d %H:%M:%S")
                if article.published_at
                else ""
            ),
            "created_at": article.created_at.strftime("%Y-%m-%d %H:%M:%S"),
            "language": article.language.value,
            "tags": article.tags,
            "article_id": article.id,
        }


def _parse_datetime(date_str: str) -> datetime | None:
    """解析多种格式的日期字符串"""
    if not date_str:
        return None
    try:
        # ISO 8601 (含 Z 后缀)
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        pass
    # 常见格式
    for fmt in ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
        try:
            return datetime.strptime(date_str, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _detect_site_key(source: str = "", url: str = "") -> str:
    """Detect known sites for built-in extraction/cleanup rules."""
    host = urlparse(url).netloc.lower()
    source_lower = (source or "").lower()
    if "thepaper.cn" in host or "澎湃" in source_lower or "thepaper" in source_lower:
        return "thepaper"
    return ""


def _sanitize_thepaper_markdown(text: str) -> str:
    """Remove The Paper site chrome that can leak through HTML conversion."""
    footer_match = _THEPAPER_FOOTER_START_RE.search(text)
    if footer_match:
        text = text[:footer_match.start()]

    lines = []
    for line in text.splitlines():
        if _THEPAPER_NOISE_LINE_RE.search(line):
            continue
        lines.append(line)
    return "\n".join(lines)
