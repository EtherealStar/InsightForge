"""Patch _find_content_root to return (root, scoped) tuple."""
import re

filepath = r"d:\study\Logos\infrastructure\markdown_converter.py"

with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Fix return type annotation
content = content.replace(
    ") -> BeautifulSoup | Tag:",
    ") -> tuple[BeautifulSoup | Tag, bool]:",
)

# 2. Fix docstring
old_doc = '''        """
        尝试定位 HTML 中的正文容器。

        搜索优先级：
        1. <article> 标签
        2. <main> 标签
        3. 常见正文 class（post-content, article-body, entry-content 等）
        4. 回退到整个 soup
        """'''

new_doc = '''        """
        尝试定位 HTML 中的正文容器。

        搜索优先级：
        1. content_selector（用户/RSS 配置指定）
        2. 站点专用选择器（如澎湃）
        3. <article> 标签
        4. <main> 标签
        5. 常见正文 class（post-content, article-body, entry-content 等）
        6. 回退到整个 soup

        Returns:
            (root, scoped) — scoped 为 True 表示成功定位到正文容器，
            False 表示回退到了整个 soup。
        """'''

# Handle both CRLF and LF
for line_ending in ["\r\n", "\n"]:
    old = old_doc.replace("\n", line_ending)
    new = new_doc.replace("\n", line_ending)
    if old in content:
        content = content.replace(old, new)
        print("Replaced docstring")
        break
else:
    print("WARNING: docstring not found")

# 3. Fix return statements inside _find_content_root
# We need to be careful to only replace returns inside this specific method.
# Find the method and replace returns within it.

# Pattern: find the method body and fix returns
# "return content" -> "return content, True" (the one inside the selector loop)
# "return article_tag" -> "return article_tag, True"
# "return main_tag" -> "return main_tag, True"
# "return content_div" -> "return content_div, True"
# "return soup" -> "return soup, False" (the fallback)

# We'll do targeted replacements using context

content = content.replace(
    "            if content and content.get_text(strip=True):\n                return content\n",
    "            if content and content.get_text(strip=True):\n                return content, True\n",
)
content = content.replace(
    "            if content and content.get_text(strip=True):\r\n                return content\r\n",
    "            if content and content.get_text(strip=True):\r\n                return content, True\r\n",
)

content = content.replace(
    "        if article_tag:\n            return article_tag\n",
    "        if article_tag:\n            return article_tag, True\n",
)
content = content.replace(
    "        if article_tag:\r\n            return article_tag\r\n",
    "        if article_tag:\r\n            return article_tag, True\r\n",
)

content = content.replace(
    "        if main_tag:\n            return main_tag\n",
    "        if main_tag:\n            return main_tag, True\n",
)
content = content.replace(
    "        if main_tag:\r\n            return main_tag\r\n",
    "        if main_tag:\r\n            return main_tag, True\r\n",
)

content = content.replace(
    "        if content_div:\n            return content_div\n",
    "        if content_div:\n            return content_div, True\n",
)
content = content.replace(
    "        if content_div:\r\n            return content_div\r\n",
    "        if content_div:\r\n            return content_div, True\r\n",
)

# The final "return soup" fallback - be specific with context
content = content.replace(
    "        # 回退到整个 soup\n        return soup\n",
    "        # 回退到整个 soup\n        return soup, False\n",
)
content = content.replace(
    "        # 回退到整个 soup\r\n        return soup\r\n",
    "        # 回退到整个 soup\r\n        return soup, False\r\n",
)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(content)

print("Done patching _find_content_root")
