"""DeepResearchService（报告文件服务）测试。"""

from services.deep_research_service import DeepResearchService


def test_save_and_get_and_delete_report(tmp_path):
    service = DeepResearchService(output_dir=str(tmp_path))

    path = service.save_report(topic="AI 趋势", content="# report")
    assert path.endswith(".md")

    reports = service.list_reports()
    assert len(reports) == 1
    filename = reports[0]["filename"]

    loaded = service.get_report(filename)
    assert loaded is not None
    assert loaded["content"] == "# report"

    deleted = service.delete_report(filename)
    assert deleted is True
