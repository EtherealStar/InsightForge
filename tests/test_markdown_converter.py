"""测试 NewsMarkdownConverter 的 HTML 预清理和元数据提取"""
import pytest
from datetime import datetime

from infrastructure.markdown_converter import NewsMarkdownConverter
from models.article import Article, Language


@pytest.fixture
def converter():
    return NewsMarkdownConverter()


# ------------------------------------------------------------------
# 元数据提取测试
# ------------------------------------------------------------------

class TestMetadataExtraction:
    """测试从 HTML 中提取元数据"""

    def test_extract_author_from_jsonld(self, converter):
        """JSON-LD 中的作者应被正确提取"""
        html = '''
        <html><head>
        <script type="application/ld+json">
        {"@type": "Article", "author": {"@type": "Person", "name": "蒋编辑"}}
        </script>
        </head><body><p>正文</p></body></html>
        '''
        article = Article(title="测试", url="http://example.com", html_content=html)
        converter.convert_article(article)
        assert article.author == "蒋编辑"

    def test_extract_published_at_from_jsonld(self, converter):
        """JSON-LD 中的发布时间应被正确提取"""
        html = '''
        <html><head>
        <script type="application/ld+json">
        {"@type": "Article", "datePublished": "2026-01-26T04:12:43.000Z"}
        </script>
        </head><body><p>正文</p></body></html>
        '''
        article = Article(
            title="测试", url="http://example.com",
            html_content=html, published_at=None,
        )
        converter.convert_article(article)
        assert article.published_at is not None
        assert article.published_at.year == 2026
        assert article.published_at.month == 1
        assert article.published_at.day == 26

    def test_extract_tags_from_jsonld(self, converter):
        """JSON-LD 中的关键词应被解析为 tags 列表"""
        html = '''
        <html><head>
        <script type="application/ld+json">
        {"@type": "Article", "keywords": "特刊文章, 钢铁, 安全"}
        </script>
        </head><body><p>正文</p></body></html>
        '''
        article = Article(title="测试", url="http://example.com", html_content=html)
        converter.convert_article(article)
        assert article.tags == ["特刊文章", "钢铁", "安全"]

    def test_extract_author_from_meta(self, converter):
        """<meta name="author"> 应被提取"""
        html = '''
        <html><head>
        <meta name="author" content="张三">
        </head><body><p>正文</p></body></html>
        '''
        article = Article(title="测试", url="http://example.com", html_content=html)
        converter.convert_article(article)
        assert article.author == "张三"

    def test_extract_published_at_from_meta(self, converter):
        """<meta property="article:published_time"> 应被提取"""
        html = '''
        <html><head>
        <meta property="article:published_time" content="2026-03-15T10:00:00+08:00">
        </head><body><p>正文</p></body></html>
        '''
        article = Article(
            title="测试", url="http://example.com",
            html_content=html, published_at=None,
        )
        converter.convert_article(article)
        assert article.published_at is not None
        assert article.published_at.month == 3

    def test_existing_metadata_not_overwritten(self, converter):
        """已有的 author / published_at 不应被覆盖"""
        html = '''
        <html><head>
        <script type="application/ld+json">
        {"@type": "Article", "author": {"name": "HTML作者"}, "datePublished": "2020-01-01"}
        </script>
        </head><body><p>正文</p></body></html>
        '''
        original_date = datetime(2026, 6, 1)
        article = Article(
            title="测试", url="http://example.com",
            html_content=html,
            author="原始作者",
            published_at=original_date,
        )
        converter.convert_article(article)
        assert article.author == "原始作者"
        assert article.published_at == original_date


# ------------------------------------------------------------------
# HTML 清理测试
# ------------------------------------------------------------------

class TestHtmlCleaning:
    """测试 HTML 噪音清理"""

    def test_script_content_removed(self, converter):
        """<script> 标签内的 JS 代码不应出现在输出中"""
        html = '''
        <html><body>
        <script>window.dataLayer = window.dataLayer || [];</script>
        <p>这是正文内容</p>
        </body></html>
        '''
        article = Article(title="测试", url="http://example.com", html_content=html)
        converter.convert_article(article)
        assert "dataLayer" not in article.content
        assert "正文内容" in article.content

    def test_style_content_removed(self, converter):
        """<style> 标签内的 CSS 不应出现在输出中"""
        html = '''
        <html><head>
        <style>.gh-post { color: red; border-radius: 8px; }</style>
        </head><body><p>这是正文内容</p></body></html>
        '''
        article = Article(title="测试", url="http://example.com", html_content=html)
        converter.convert_article(article)
        assert "border-radius" not in article.content
        assert "gh-post" not in article.content
        assert "正文内容" in article.content

    def test_jsonld_content_removed(self, converter):
        """JSON-LD 内容不应出现在 Markdown 正文中"""
        html = '''
        <html><head>
        <script type="application/ld+json">
        {"@context": "https://schema.org", "@type": "Article", "headline": "测试标题"}
        </script>
        </head><body><p>这是正文内容</p></body></html>
        '''
        article = Article(title="测试", url="http://example.com", html_content=html)
        converter.convert_article(article)
        assert "@context" not in article.content
        assert "schema.org" not in article.content
        assert "正文内容" in article.content

    def test_nav_content_removed(self, converter):
        """<nav> 导航内容不应出现在输出中"""
        html = '''
        <html><body>
        <nav><a href="/about">关于</a><a href="/contact">联系</a></nav>
        <article><p>这是正文内容</p></article>
        </body></html>
        '''
        article = Article(title="测试", url="http://example.com", html_content=html)
        converter.convert_article(article)
        assert "关于" not in article.content
        assert "联系" not in article.content
        assert "正文内容" in article.content

    def test_footer_content_removed(self, converter):
        """<footer> 内容不应出现在输出中"""
        html = '''
        <html><body>
        <article><p>这是正文内容</p></article>
        <footer><p>版权所有 2026</p></footer>
        </body></html>
        '''
        article = Article(title="测试", url="http://example.com", html_content=html)
        converter.convert_article(article)
        assert "版权所有" not in article.content
        assert "正文内容" in article.content

    def test_noise_class_removed(self, converter):
        """包含导航/社交等 class 的 div 应被移除"""
        html = '''
        <html><body>
        <div class="social-share"><a>Share</a><a>Tweet</a></div>
        <article><p>这是正文内容</p></article>
        <div class="related-posts"><p>推荐阅读</p></div>
        </body></html>
        '''
        article = Article(title="测试", url="http://example.com", html_content=html)
        converter.convert_article(article)
        assert "Share" not in article.content
        assert "Tweet" not in article.content
        assert "推荐阅读" not in article.content
        assert "正文内容" in article.content


# ------------------------------------------------------------------
# 正文容器定位测试
# ------------------------------------------------------------------

class TestContentRootDetection:
    """测试正文容器定位"""

    def test_finds_article_tag(self, converter):
        """应优先定位 <article> 标签"""
        html = '''
        <html><body>
        <header><h1>网站标题</h1></header>
        <article>
            <h2>文章标题</h2>
            <p>这是正文内容，包含重要信息。</p>
        </article>
        <aside><p>侧边栏广告</p></aside>
        </body></html>
        '''
        article = Article(title="测试", url="http://example.com", html_content=html)
        converter.convert_article(article)
        assert "正文内容" in article.content
        assert "网站标题" not in article.content
        assert "侧边栏广告" not in article.content

    def test_finds_main_tag(self, converter):
        """当没有 <article> 时应使用 <main>"""
        html = '''
        <html><body>
        <header><h1>网站标题</h1></header>
        <main>
            <p>这是正文内容</p>
        </main>
        </body></html>
        '''
        article = Article(title="测试", url="http://example.com", html_content=html)
        converter.convert_article(article)
        assert "正文内容" in article.content

    def test_finds_content_class(self, converter):
        """应能识别 gh-content 等常见 CMS class"""
        html = '''
        <html><body>
        <div class="site-header">导航栏</div>
        <div class="gh-content">
            <p>这是正文内容</p>
        </div>
        <div class="site-footer">页脚</div>
        </body></html>
        '''
        article = Article(title="测试", url="http://example.com", html_content=html)
        converter.convert_article(article)
        assert "正文内容" in article.content


# ------------------------------------------------------------------
# 端到端集成测试
# ------------------------------------------------------------------

class TestEndToEnd:
    """模拟真实网页的端到端测试"""

    def test_ghost_cms_article(self, converter):
        """模拟 Ghost CMS 文章（类似捕获文本.md 的内容）"""
        html = '''
        <html>
        <head>
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "author": {"@type": "Person", "name": "蒋编辑"},
            "headline": "炼钢巨兽为何失控",
            "datePublished": "2026-01-26T04:12:43.000Z",
            "keywords": "特刊文章"
        }
        </script>
        <style>
        .gh-post-upgrade-cta { display: flex; color: #ffffff; }
        :root {--ghost-accent-color: #3a74f5;}
        </style>
        <script>
        window.dataLayer = window.dataLayer || [];
        function gtag(){dataLayer.push(arguments);}
        </script>
        </head>
        <body>
        <nav>
            <a href="/">首页</a>
            <a href="/about">关于</a>
            <a href="/recruit">征集志愿者</a>
        </nav>
        <article>
            <h1>炼钢巨兽为何失控：包钢球罐爆炸与钢铁的冶炼逻辑</h1>
            <p>包头市是一座重要的资源型城市，该地区蕴含大量煤炭、铁矿、稀土。</p>
            <h2>钢铁如何炼成</h2>
            <p>包钢和许多现代钢铁厂一样采用的是高炉-转炉工艺进行冶炼。</p>
            <img src="https://example.com/image.png" alt="高炉">
        </article>
        <div class="social-share">
            <a href="https://facebook.com/share">Share</a>
            <a href="https://twitter.com/tweet">Tweet</a>
        </div>
        <footer>
            <p>工劳小报 © 2026</p>
            <p>Published with Ghost</p>
        </footer>
        <script>
        $(".members-login").hide();
        $('input.auth-email').attr("placeholder","输入邮箱");
        </script>
        </body>
        </html>
        '''
        article = Article(
            title="炼钢巨兽为何失控",
            url="http://example.com/baotou",
            html_content=html,
            published_at=None,
        )
        converter.convert_article(article)

        # 元数据应被正确提取
        assert article.author == "蒋编辑"
        assert article.published_at is not None
        assert article.published_at.year == 2026
        assert article.tags == ["特刊文章"]

        # 正文内容应保留
        assert "包头市" in article.content
        assert "钢铁如何炼成" in article.content
        assert "高炉-转炉工艺" in article.content

        # 噪音内容应被移除
        assert "dataLayer" not in article.content
        assert "gtag" not in article.content
        assert "ghost-accent-color" not in article.content
        assert "gh-post-upgrade-cta" not in article.content
        assert "schema.org" not in article.content
        assert "Share" not in article.content
        assert "Tweet" not in article.content
        assert "Published with Ghost" not in article.content
        assert "members-login" not in article.content
        assert "征集志愿者" not in article.content

        # html_content 应被清空
        assert article.html_content == ""

    def test_plain_text_fallback(self, converter):
        """当没有 html_content 时应回退到 content"""
        article = Article(
            title="纯文本文章",
            url="http://example.com",
            content="这是一段纯文本内容\n\n\n\n包含多余空行",
            html_content="",
        )
        converter.convert_article(article)
        assert "纯文本内容" in article.content
        # 多余空行应被清理
        assert "\n\n\n" not in article.content

    def test_headings_newlines(self, converter):
        """标题前后应自动增加换行符，但不影响代码块"""
        article = Article(
            title="标题测试",
            url="http://example.com",
            content="前文\n# 一级标题\n后文\n```python\n# 注释不应被加空行\n```\n## 二级标题\n结尾",
            html_content="",
        )
        converter.convert_article(article)
        expected = "前文\n\n# 一级标题\n\n后文\n\n```python\n# 注释不应被加空行\n```\n\n## 二级标题\n\n结尾"
        assert article.content == expected
