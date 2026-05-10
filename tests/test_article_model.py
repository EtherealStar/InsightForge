"""Article DTO/entity mapper tests."""

from datetime import datetime

from models.article import (
    Article,
    ArticleDTO,
    ArticleMapper,
    ArticleStatus,
    Language,
)


def test_article_entity_to_dto_roundtrip():
    article = Article(
        id=1,
        url_hash="hash",
        title="Title",
        url="https://example.com",
        content="content",
        summary="summary",
        source="source",
        author="author",
        language=Language.ZH,
        published_at=datetime(2026, 5, 10),
        tags=["ai"],
        status=ArticleStatus.EMBEDDED,
    )

    dto = ArticleMapper.entity_to_dto(article)
    restored = ArticleMapper.dto_to_entity(dto)

    assert isinstance(dto, ArticleDTO)
    assert restored.title == article.title
    assert restored.language == Language.ZH
    assert restored.status == ArticleStatus.EMBEDDED
    assert restored.tags == ["ai"]
