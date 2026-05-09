"""SummaryService 测试。"""

from datetime import datetime
from unittest.mock import MagicMock

from models.article import Article
from services.summary_service import SummaryService


def _articles():
    return [
        Article(
            id=1,
            title="A",
            url="https://example.com/1",
            content="c1",
            published_at=datetime.now(),
        ),
        Article(
            id=2,
            title="B",
            url="https://example.com/2",
            content="c2",
            published_at=datetime.now(),
        ),
    ]


def test_summarize_pending_success():
    llm = MagicMock()
    llm.generate.return_value = (
        '[{"index":1,"summary":"s1","tags":["AI"]},'
        '{"index":2,"summary":"s2","tags":["Tech"]}]'
    )
    store = MagicMock()
    store.get_pending_summary.return_value = _articles()

    service = SummaryService(llm_client=llm, article_store=store, batch_size=2)
    result = service.summarize_pending()

    assert result["success"] == 2
    assert result["failed"] == 0
    assert store.update_summary.call_count == 2
    assert store.mark_summarized.call_count == 2


def test_summarize_pending_all_failed_marks_summarized():
    llm = MagicMock()
    llm.generate.return_value = "not-json"
    store = MagicMock()
    pending = _articles()
    store.get_pending_summary.return_value = pending

    service = SummaryService(llm_client=llm, article_store=store, batch_size=2)
    result = service.summarize_pending()

    assert result["success"] == 0
    assert result["failed"] == 2
    store.mark_summarized.assert_called_once_with([1, 2])
