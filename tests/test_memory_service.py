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
        return [item for item in self.memories if status is None or item.status == status]


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
