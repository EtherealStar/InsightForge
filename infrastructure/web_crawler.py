"""基于 Crawlee 的网页新闻爬取器"""
import asyncio
import hashlib
import re
import structlog
import uuid
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import trafilatura
from crawlee.crawlers import BeautifulSoupCrawler, BeautifulSoupCrawlingContext
from crawlee import ConcurrencySettings
from crawlee.statistics import Statistics
from crawlee.storages import RequestQueue

from models.article import Article, Language
from core.exceptions import CollectorError

logger = structlog.get_logger(__name__)


_TRACKING_QUERY_PARAMS = {
    "commtag",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "spm",
    "from",
    "ref",
}


@dataclass(frozen=True)
class _CrawlerRules:
    article_patterns: tuple[re.Pattern, ...] = ()
    exclude_patterns: tuple[re.Pattern, ...] = ()


_THEPAPER_RULES = _CrawlerRules(
    article_patterns=(
        re.compile(r"https?://www\.thepaper\.cn/newsDetail_forward_\d+(?:\?.*)?$", re.I),
    ),
    exclude_patterns=(
        re.compile(r"/list_\d+(?:\?|$)", re.I),
        re.compile(r"/download(?:\?|$)", re.I),
        re.compile(r"[?&]commTag=true", re.I),
    ),
)


_BJNEWS_RULES = _CrawlerRules(
    article_patterns=(
        re.compile(r"https?://www\.bjnews\.com\.cn/detail/\d+\.html(?:\?.*)?$", re.I),
    ),
)


_INFZM_RULES = _CrawlerRules(
    article_patterns=(
        re.compile(r"https?://www\.infzm\.com/contents/\d+(?:\?.*)?$", re.I),
    ),
)


def _site_default_rules(site_name: str, site_url: str) -> _CrawlerRules:
    """Return built-in URL rules for known news sites."""
    host = urlparse(site_url).netloc.lower()
    name = site_name.lower()
    if "thepaper.cn" in host or "澎湃" in name or "thepaper" in name:
        return _THEPAPER_RULES
    if "bjnews.com.cn" in host or "新京报" in name or "bjnews" in name:
        return _BJNEWS_RULES
    if "infzm.com" in host or "南方周末" in name or "infzm" in name:
        return _INFZM_RULES
    return _CrawlerRules()


def _compile_patterns(patterns: list[str] | tuple[str, ...] | None) -> tuple[re.Pattern, ...]:
    """Compile user-supplied regex patterns, ignoring invalid entries."""
    compiled: list[re.Pattern] = []
    for pattern in patterns or []:
        if not pattern:
            continue
        try:
            compiled.append(re.compile(pattern, re.I))
        except re.error as exc:
            logger.warning(f"忽略无效 URL 规则 '{pattern}': {exc}")
    return tuple(compiled)


def _as_crawlee_patterns(patterns: tuple[re.Pattern, ...]) -> tuple[re.Pattern, ...]:
    """
    Crawlee checks include/exclude regexes with re.match().

    User patterns are easier to write as snippets such as /list_\\d+ or
    [?&]commTag=true, so adapt unanchored expressions to match anywhere.
    """
    adapted: list[re.Pattern] = []
    for pattern in patterns:
        source = pattern.pattern
        if source.startswith("^") or source.startswith(".*"):
            adapted.append(pattern)
        else:
            adapted.append(re.compile(f".*(?:{source})", pattern.flags))
    return tuple(adapted)


def _merge_rules(
    site_name: str,
    site_url: str,
    article_url_patterns: list[str] | None = None,
    exclude_url_patterns: list[str] | None = None,
) -> _CrawlerRules:
    """Merge built-in site rules with optional per-site configuration."""
    defaults = _site_default_rules(site_name, site_url)
    return _CrawlerRules(
        article_patterns=defaults.article_patterns + _compile_patterns(article_url_patterns),
        exclude_patterns=defaults.exclude_patterns + _compile_patterns(exclude_url_patterns),
    )


def _canonicalize_url(url: str) -> str:
    """Normalize URLs for storage/deduplication without changing path case."""
    parsed = urlparse(url)
    kept_params = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_QUERY_PARAMS and not key.lower().startswith("utm_")
    ]
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path,
            parsed.params,
            urlencode(kept_params, doseq=True),
            "",
        )
    )


def _url_matches_rules(url: str, rules: _CrawlerRules) -> bool:
    """Return whether a URL should be processed as an article."""
    canonical_url = _canonicalize_url(url)
    for pattern in rules.exclude_patterns:
        if pattern.search(url) or pattern.search(canonical_url):
            return False
    if not rules.article_patterns:
        return True
    return any(pattern.search(url) or pattern.search(canonical_url) for pattern in rules.article_patterns)


def _build_storage_name(site_name: str, site_url: str) -> str:
    """为单次爬取生成独立 Crawlee 存储名称，避免复用 default 队列。"""
    slug = re.sub(r"[^a-z0-9]+", "-", site_name.lower()).strip("-")
    if not slug:
        slug = urlparse(site_url).netloc.lower() or "site"
        slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-") or "site"

    url_hash = hashlib.sha1(site_url.encode("utf-8")).hexdigest()[:8]
    run_id = uuid.uuid4().hex[:12]
    return f"web-crawler-{slug[:40]}-{url_hash}-{run_id}"


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
        max_pages: int | None = None,
        article_url_patterns: list[str] | None = None,
        exclude_url_patterns: list[str] | None = None,
        content_selector: str | None = None,
        noise_selectors: list[str] | None = None,
    ) -> list[Article]:
        """内部异步爬取方法"""
        articles: list[Article] = []
        storage_name = _build_storage_name(site_name, site_url)
        page_limit = max_pages or self.max_pages
        rules = _merge_rules(
            site_name,
            site_url,
            article_url_patterns=article_url_patterns,
            exclude_url_patterns=exclude_url_patterns,
        )

        concurrency = ConcurrencySettings(
            desired_concurrency=self.max_concurrency,
            max_concurrency=self.max_concurrency,
        )

        request_queue = await RequestQueue.open(name=storage_name)

        crawler = BeautifulSoupCrawler(
            max_requests_per_crawl=page_limit,
            concurrency_settings=concurrency,
            request_manager=request_queue,
            statistics=Statistics.with_default_state(
                persistence_enabled=True,
                persist_state_kvs_name=storage_name,
                persist_state_key="CRAWLER_STATISTICS",
                statistics_log_format="inline",
            ),
        )

        @crawler.router.default_handler
        async def handler(context: BeautifulSoupCrawlingContext) -> None:
            url = context.request.url
            page_html = str(context.soup)

            if _url_matches_rules(url, rules):
                full_text = trafilatura.extract(page_html) or ""
                title_tag = context.soup.find("title")
                title = title_tag.get_text(strip=True) if title_tag else ""

                h1_tag = context.soup.find("h1")
                if h1_tag:
                    h1_text = h1_tag.get_text(strip=True)
                    if h1_text and len(h1_text) > len(title):
                        title = h1_text

                if full_text and len(full_text) >= self.MIN_CONTENT_LENGTH and title:
                    canonical_url = _canonicalize_url(url)
                    language = _detect_language(title + full_text)
                    article = Article(
                        title=title,
                        url=canonical_url,
                        content=full_text,
                        html_content=page_html,
                        summary=full_text[:500],
                        source=site_name,
                        language=language,
                        published_at=_extract_publish_date(context.soup) or datetime.now(),
                    )
                    article.content_selector = content_selector or ""
                    article.noise_selectors = noise_selectors or []
                    articles.append(article)
                    context.log.info(f"提取文章: {title[:60]}")

            await context.enqueue_links(
                selector=link_selector or "a",
                strategy="same-hostname",
                include=_as_crawlee_patterns(rules.article_patterns) or None,
                exclude=_as_crawlee_patterns(rules.exclude_patterns) or None,
            )

        try:
            logger.info(
                f"[WebCrawler] {site_name}: 使用独立存储 {storage_name}"
            )
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
        max_pages: int | None = None,
        article_url_patterns: list[str] | None = None,
        exclude_url_patterns: list[str] | None = None,
        content_selector: str | None = None,
        noise_selectors: list[str] | None = None,
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
                    self._crawl(
                        site_name,
                        site_url,
                        link_selector,
                        max_pages,
                        article_url_patterns,
                        exclude_url_patterns,
                        content_selector,
                        noise_selectors,
                    ),
                )
                return future.result()
        else:
            return asyncio.run(
                self._crawl(
                    site_name,
                    site_url,
                    link_selector,
                    max_pages,
                    article_url_patterns,
                    exclude_url_patterns,
                    content_selector,
                    noise_selectors,
                )
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
            article_url_patterns = site.get("article_url_patterns")
            exclude_url_patterns = site.get("exclude_url_patterns")
            content_selector = site.get("content_selector")
            noise_selectors = site.get("noise_selectors")
            try:
                articles = self.crawl_site(
                    name,
                    url,
                    link_selector,
                    max_pages,
                    article_url_patterns,
                    exclude_url_patterns,
                    content_selector,
                    noise_selectors,
                )
                all_articles.extend(articles)
                logger.info(f" {name}: 爬取到 {len(articles)} 篇文章")
            except Exception as e:
                msg = f" {name}: 爬取失败 — {e}"
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
