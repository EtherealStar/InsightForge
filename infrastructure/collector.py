"""新闻抓取：feedparser + trafilatura"""
import logging
from datetime import datetime
import calendar

import feedparser
import trafilatura

from models.article import Article, Language
from core.config import AppConfig
from core.exceptions import CollectorError, SourceUnavailableError
from core.retry import with_retry

logger = logging.getLogger(__name__)


class NewsCollector:
    """从 RSS 源抓取新闻文章"""

    def __init__(self, config: AppConfig):
        self.config = config

    def fetch_all(self) -> list[Article]:
        """
        从所有 RSS 源抓取文章。
        每个源独立 try/except，单源失败不影响整体。
        每源最多返回 config.max_articles_per_fetch 条。
        """
        all_articles: list[Article] = []
        for feed_info in self.config.rss_feeds:
            name = feed_info["name"]
            url = feed_info["url"]
            try:
                articles = self.fetch_source(name, url)
                all_articles.extend(articles)
                logger.info(f"✅ {name}: 抓取到 {len(articles)} 篇文章")
            except Exception as e:
                logger.error(f"❌ {name}: 抓取失败 — {e}")
        logger.info(f"总计抓取 {len(all_articles)} 篇文章")
        return all_articles

    def fetch_source(self, name: str, url: str) -> list[Article]:
        """抓取单个 RSS 源"""
        feed = feedparser.parse(url)

        if feed.bozo and not feed.entries:
            raise SourceUnavailableError(name, str(feed.bozo_exception))

        articles: list[Article] = []
        entries = feed.entries[: self.config.max_articles_per_fetch]

        for entry in entries:
            try:
                article = self._parse_entry(entry, name)
                if article:
                    articles.append(article)
            except Exception as e:
                logger.warning(f"跳过条目 '{entry.get('title', '?')}': {e}")

        return articles

    def _parse_entry(self, entry, source_name: str) -> Article | None:
        """将 feedparser entry 转为 Article"""
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        if not title or not link:
            return None

        # feedparser 通常将 <description> 映射为 summary，也有部分情况在 description 属性中
        summary_text = entry.get("summary", "")
        if not summary_text and hasattr(entry, "description"):
            summary_text = entry.description
            
        summary_clean = summary_text.strip() if summary_text else ""

        # 获取可能存在的全量 HTML 原文 (<content:encoded>)
        rss_html = ""
        if "content" in entry and entry.content:
            rss_html = entry.content[0].get("value", "")

        html_content = rss_html
        full_text = None
        
        # 1. 如果有原文 (content:encoded)，首先尝试从中提取纯文本
        if rss_html:
            full_text = trafilatura.extract(rss_html)
            
        # 2. 如果缺少原文，或者未能提取文本，检查 summary/description 以及是否需要爬取网页
        if not full_text:
            is_wechat = "mp.weixin.qq.com" in link
            
            # 判断 summary_clean 是否有实用的 HTML 或者足够长可以作为全文回退
            if summary_clean and ("<p>" in summary_clean or "<img " in summary_clean or len(summary_clean) > 200 or is_wechat):
                # 将 summary 当作网页内容提取
                full_text = trafilatura.extract(summary_clean) or summary_clean
                if not html_content:
                    html_content = summary_clean
                    
            # 3. 如果依然没有足够正文内容，且不是微信公众号链接（微信严格防爬，跳过）
            if not full_text and not is_wechat:
                web_text, web_html = self._extract_full_text(link)
                # 过滤明显被拦截的反爬网页（防御性）
                if web_text and ("完成验证后即可继续访问" in web_text or "环境异常" in web_text):
                    logger.debug(f"跳过反爬验证页面: {link}")
                    web_text, web_html = None, None

                full_text = web_text
                # 补充 html
                if not html_content:
                    html_content = web_html or summary_clean

        content = full_text or summary_clean or ""

        # 解析发布时间 (由于 feedparser 的 published_parsed 均为 UTC时间，需特殊处理回本地时间)
        published_at = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                # timegm 会将 UTC 的 struct_time 转为等效的秒数纪元戳
                # 然后 fromtimestamp 将这个纪元戳视为绝对时间戳转换回本地 datetime，这样能完全保留和本地时钟一致的小时数
                ts = calendar.timegm(entry.published_parsed)
                published_at = datetime.fromtimestamp(ts)
            except (ValueError, OverflowError):
                pass
        if published_at is None:
            published_at = datetime.now()

        # 简单语言检测
        language = self._detect_language(title + content)

        return Article(
            title=title,
            url=link,
            content=content,
            html_content=html_content or "",
            summary=summary_clean[:500] if summary_clean else "",
            source=source_name,
            language=language,
            published_at=published_at,
        )

    @with_retry(max_retries=2, exceptions=(Exception,))
    def _extract_full_text(self, url: str) -> tuple[str | None, str | None]:
        """
        用 trafilatura 提取正文全文与原始HTML。
        失败返回 (None, None)，由调用方回退到 RSS summary。
        """
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(downloaded)
                return text, downloaded
        except Exception as e:
            logger.debug(f"trafilatura 提取失败 {url}: {e}")
        return None, None

    @staticmethod
    def _detect_language(text: str) -> Language:
        """简单语言检测：中文字符占比判断"""
        if not text:
            return Language.UNKNOWN
        chinese_count = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        ratio = chinese_count / len(text) if text else 0
        if ratio > 0.1:
            return Language.ZH
        elif ratio < 0.01:
            return Language.EN
        return Language.UNKNOWN
