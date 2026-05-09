"""基于 Crawlee 的网页新闻爬取器"""
import asyncio
import structlog
from datetime import datetime
from urllib.parse import urlparse

import trafilatura
from crawlee.crawlers import BeautifulSoupCrawler, BeautifulSoupCrawlingContext
from crawlee import ConcurrencySettings

from models.article import Article, Language
from core.exceptions import CollectorError

logger = structlog.get_logger(__name__)


class WebCrawler:
    """
    通过 Crawlee BeautifulSoupCrawler 爬取指定网站的新闻文章。

    工作流程:
    1. 从种子 URL 出发，发现页面中的链接
    2. 仅跟踪同域名下的链接
    3. 用 trafilatura 从每个页面提取正文
    4. 过滤掉正文过短的页面（非文章页）
    5. 返回 list[Article]
    """

    MIN_CONTENT_LENGTH = 100

    def __init__(
        self,
        max_pages: int = 20,
        max_concurrency: int = 5,
    ):
        self.max_pages = max_pages
        self.max_concurrency = max_concurrency

    async def _crawl(
        self,
        site_name: str,
        site_url: str,
        link_selector: str | None = None,
    ) -> list[Article]:
        """内部异步爬取方法"""
        articles: list[Article] = []
        seed_domain = urlparse(site_url).netloc

        concurrency = ConcurrencySettings(
            desired_concurrency=self.max_concurrency,
            max_concurrency=self.max_concurrency,
        )

        crawler = BeautifulSoupCrawler(
            max_requests_per_crawl=self.max_pages,
            concurrency_settings=concurrency,
        )

        @crawler.router.default_handler
        async def handler(context: BeautifulSoupCrawlingContext) -> None:
            url = context.request.url
            page_html = str(context.soup)

            full_text = trafilatura.extract(page_html) or ""
            title_tag = context.soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else ""

            h1_tag = context.soup.find("h1")
            if h1_tag:
                h1_text = h1_tag.get_text(strip=True)
                if h1_text and len(h1_text) > len(title):
                    title = h1_text

            if full_text and len(full_text) >= self.MIN_CONTENT_LENGTH and title:
                language = _detect_language(title + full_text)
                article = Article(
                    title=title,
                    url=url,
                    content=full_text,
                    html_content=page_html,
                    summary=full_text[:500],
                    source=site_name,
                    language=language,
                    published_at=_extract_publish_date(context.soup) or datetime.now(),
                )
                articles.append(article)
                context.log.info(f"提取文章: {title[:60]}")

            await context.enqueue_links(
                selector=link_selector or "a",
                strategy="same-domain",
            )

        try:
            await crawler.run([site_url])
        except Exception as e:
            logger.error(f"Crawlee 爬取 {site_name} ({site_url}) 失败: {e}")
            raise CollectorError(f"网页爬取失败: {site_name} — {e}")

        logger.info(f"[WebCrawler] {site_name}: 爬取到 {len(articles)} 篇文章")
        return articles

    def crawl_site(
        self,
        site_name: str,
        site_url: str,
        link_selector: str | None = None,
    ) -> list[Article]:
        """
        同步入口：爬取指定网站并返回文章列表。
        在已有事件循环时安全运行。
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    self._crawl(site_name, site_url, link_selector),
                )
                return future.result()
        else:
            return asyncio.run(
                self._crawl(site_name, site_url, link_selector)
            )

    def crawl_all(self, sites: list[dict]) -> tuple[list[Article], list[str]]:
        """
        爬取所有配置的网站源。
        每个站点独立 try/except，单站失败不影响整体。

        sites 格式: [{"name": "...", "url": "...", "max_pages": 20, "link_selector": "a.article"}]
        """
        all_articles: list[Article] = []
        errors: list[str] = []
        for site in sites:
            name = site.get("name", "unknown")
            url = site.get("url", "")
            if not url:
                continue
            max_pages = site.get("max_pages", self.max_pages)
            link_selector = site.get("link_selector")
            try:
                old_max = self.max_pages
                self.max_pages = max_pages
                articles = self.crawl_site(name, url, link_selector)
                self.max_pages = old_max
                all_articles.extend(articles)
                logger.info(f"✅ {name}: 爬取到 {len(articles)} 篇文章")
            except Exception as e:
                msg = f"❌ {name}: 爬取失败 — {e}"
                logger.error(msg)
                errors.append(msg)
        logger.info(f"[WebCrawler] 总计爬取 {len(all_articles)} 篇文章")
        return all_articles, errors


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


def _extract_publish_date(soup) -> datetime | None:
    """尝试从 HTML meta 标签提取发布时间"""
    date_metas = [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"name": "publishdate"}),
        ("meta", {"name": "publish_date"}),
        ("meta", {"property": "og:article:published_time"}),
        ("time", {"datetime": True}),
    ]
    for tag_name, attrs in date_metas:
        tag = soup.find(tag_name, attrs)
        if tag:
            date_str = tag.get("content") or tag.get("datetime") or ""
            if date_str:
                try:
                    return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    continue
    return None
