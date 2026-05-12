"""MemoryService 单元测试。"""

from types import SimpleNamespace

from models.agent_session import AgentSession
from models.memory import MemoryStatus, MemoryType, PersistentMemory
from services.memory_service import MemoryService, estimate_tokens


class FakeMemoryStore:
    def __init__(self):
        self.memories = [
            PersistentMemory(
                id="m1",
                memory_type=MemoryType.FEEDBACK,
                title="concise",
                summary="回复保持简洁",
                content="用户偏好简洁直接的回答。",
                status=MemoryStatus.ACTIVE,
            )
        ]

    def get_active_core_memories(self, kind=None):
        return [SimpleNamespace(content="核心规则：基于事实回答。")]

    def list_memory_index(self, memory_types=None):
        return [SimpleNamespace(line="- [feedback-concise] - 回复保持简洁")]

    def list_persistent_memories(self, status=None, memory_type=None):
        return [
            item
            for item in self.memories
            if (status is None or item.status == status)
            and (memory_type is None or item.memory_type == memory_type)
        ]

    def create_persistent_memory(
        self,
        memory_type,
        title,
        summary,
        content,
        source_session_id=None,
        confidence=None,
        status=MemoryStatus.PENDING,
    ):
        item = PersistentMemory(
            id=f"m{len(self.memories) + 1}",
            memory_type=memory_type,
            title=title,
            summary=summary,
            content=content,
            source_session_id=source_session_id,
            confidence=confidence,
            status=status,
        )
        self.memories.append(item)
        return item


class FakeSessionStore:
    def __init__(self):
        self.session = AgentSession(id="s1", topic="AI", summary="当前任务：研究 AI。")

    def get_session(self, session_id):
        return self.session if session_id == "s1" else None


def test_build_memory_context_includes_three_layers():
    service = MemoryService(FakeMemoryStore(), FakeSessionStore())

    context = service.build_memory_context("s1", "请简洁回答 AI 新闻")

    assert "核心记忆" in context
    assert "MEMORY 索引" in context
    assert "相关持久记忆" in context
    assert "会话记忆" in context


def test_estimate_tokens_handles_mixed_text():
    assert estimate_tokens("hello world") > 0
    assert estimate_tokens("中文内容") >= 4


def test_extract_persistent_memory_candidates_creates_pending():
    class FakeLLM:
        def generate(self, system_prompt, user_message):
            return """
            [
              {
                "memory_type": "feedback",
                "title": "prefer-short",
                "summary": "用户希望回答更短",
                "content": "用户反馈后续回答应更短、更直接。",
                "confidence": 0.9
              }
            ]
            """

    store = FakeMemoryStore()
    service = MemoryService(store, FakeSessionStore(), FakeLLM())

    items = service.extract_persistent_memory_candidates("s1", "以后短一点", "好的")

    assert len(items) == 1
    assert items[0].status == MemoryStatus.PENDING
    assert items[0].source_session_id == "s1"


def test_extract_persistent_memory_candidates_ignores_invalid_json():
    class FakeLLM:
        def generate(self, system_prompt, user_message):
            return "not json"

    service = MemoryService(FakeMemoryStore(), FakeSessionStore(), FakeLLM())

    assert service.extract_persistent_memory_candidates("s1", "q", "a") == []


def test_extract_persistent_memory_candidates_skips_duplicates():
    class FakeLLM:
        def generate(self, system_prompt, user_message):
            return """
            [{
              "memory_type": "feedback",
              "title": "concise",
              "summary": "回复保持简洁",
              "content": "用户偏好简洁直接的回答。",
              "confidence": 0.95
            }]
            """

    service = MemoryService(FakeMemoryStore(), FakeSessionStore(), FakeLLM())

    assert service.extract_persistent_memory_candidates("s1", "q", "a") == []


def test_extract_persistent_memory_candidates_without_llm_is_noop():
    service = MemoryService(FakeMemoryStore(), FakeSessionStore(), None)

    assert service.extract_persistent_memory_candidates("s1", "q", "a") == []
