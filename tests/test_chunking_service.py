"""ChunkingService semantic parent/child chunking tests."""

from infrastructure.chunking_service import ChunkingService
from models.document import SourceDocument


def _document(content: str, title: str = "测试文章") -> SourceDocument:
    return SourceDocument(
        document_id="00000000-0000-0000-0000-000000000042",
        title=title,
        url="https://example.com/chunk",
        content=content,
        source_type="web",
        document_type="competitor_doc",
        language="zh",
        competitor_ids=[1],
        product_ids=[2],
    )


def test_long_unheaded_article_splits_into_bounded_child_chunks():
    service = ChunkingService(max_child_tokens=120, target_parent_tokens=240)
    content = "这是一个没有标题的长段落，用来测试语义切割是否会按句子和长度稳定分块。" * 80

    children, parents = service.chunk_document(_document(content, title="无标题长文"))

    assert len(children) > 1
    assert parents
    assert all(child.token_count <= service.max_child_tokens for child in children)
    assert all(child.heading_path == ["无标题长文"] for child in children)


def test_mid_sized_document_has_multiple_children_and_one_parent():
    service = ChunkingService(max_child_tokens=80, target_parent_tokens=1000)
    content = "# 中等文章\n\n" + "这是一个中等长度文档，用来确保不会生成超限子块。" * 45

    children, parents = service.chunk_document(_document(content, title="中等文章"))

    assert len(children) > 1
    assert len(parents) == 1
    assert all(child.parent_chunk_id == parents[0].parent_chunk_id for child in children)
    assert all(child.token_count <= service.max_child_tokens for child in children)
    assert parents[0].child_point_ids == [child.point_id for child in children]


def test_child_content_contains_document_and_section_prefix():
    service = ChunkingService(max_child_tokens=160, target_parent_tokens=320)
    content = "# 主标题\n\n## 事故原因\n\n设备老化导致风险上升。"

    children, _ = service.chunk_document(_document(content, title="主标题"))

    assert children
    assert children[0].content.startswith("文档: 主标题\n章节: 事故原因")
    assert "设备老化" in children[0].content


def test_oversized_paragraph_prefers_sentence_boundaries():
    service = ChunkingService(max_child_tokens=90, target_parent_tokens=180)
    paragraph = (
        "第一句描述事故背景。"
        "第二句说明设备老化。"
        "第三句说明安全投入不足。"
        "第四句说明外包风险。"
    ) * 25

    children, _ = service.chunk_document(_document(paragraph, title="句子切割"))

    assert len(children) > 1
    assert all(child.token_count <= service.max_child_tokens for child in children)
    assert any("第二句说明设备老化。" in child.content for child in children)


def test_tables_and_lists_are_preserved_when_under_limit():
    service = ChunkingService(max_child_tokens=220, target_parent_tokens=440)
    content = (
        "# 结构化内容\n\n"
        "## 数据\n\n"
        "| 年份 | 事故 |\n| --- | --- |\n| 2024 | 示例 |\n\n"
        "- 第一项\n- 第二项\n\n"
        "> 重要引用"
    )

    children, _ = service.chunk_document(_document(content, title="结构化内容"))
    combined = "\n\n".join(child.content for child in children)

    assert "| 年份 | 事故 |" in combined
    assert "- 第一项\n- 第二项" in combined
    assert "> 重要引用" in combined


def test_child_metadata_is_preserved_for_qdrant_payload():
    service = ChunkingService(max_child_tokens=160, target_parent_tokens=320)
    children, parents = service.chunk_document(
        _document("# 标题\n\n正文内容。", title="元数据测试")
    )

    assert children
    child = children[0]
    assert child.document_type == "competitor_doc"
    assert child.competitor_ids == [1]
    assert child.product_ids == [2]
    assert child.language == "zh"
    assert child.heading_path[0] == "元数据测试"
    assert parents[0].document_type == "competitor_doc"


def test_parent_overlap_keeps_shared_child_point_ids():
    service = ChunkingService(max_child_tokens=80, target_parent_tokens=220, overlap_tokens=80)
    content = "\n\n".join(
        f"## 第{i}节\n\n" + ("这是用于形成多个子块和父块的内容。" * 12)
        for i in range(8)
    )

    children, parents = service.chunk_document(_document(content, title="Overlap"))

    assert len(parents) > 1
    overlaps = [
        set(parents[i].child_point_ids) & set(parents[i + 1].child_point_ids)
        for i in range(len(parents) - 1)
    ]
    assert any(overlaps)
    assert all(child.parent_chunk_id for child in children)
    assert len({child.point_id for child in children}) == len(children)


def test_short_document_generates_parent_and_child():
    service = ChunkingService(max_child_tokens=512, target_parent_tokens=1024)
    children, parents = service.chunk_document(_document("短文档正文。", title="短文档"))

    assert len(children) == 1
    assert len(parents) == 1
    assert children[0].parent_chunk_id == parents[0].parent_chunk_id
    assert parents[0].child_point_ids == [children[0].point_id]
