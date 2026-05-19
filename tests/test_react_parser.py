"""ReAct Parser 单元测试

测试覆盖:
    1. 基本 Thought/Action/Answer 解析
    2. Action Input JSON 解析（含容错）
    3. 直接 Answer（无工具调用）
    4. 多轮推理解析
    5. 流式解析器
    6. 边界情况
"""

import pytest
from agent.react.parser import ReActParser, ReActStep, StreamingReActParser


# ======================================================================
# 1. 基本解析
# ======================================================================


class TestReActParser:
    """测试 ReAct 输出解析器。"""

    def setup_method(self):
        self.parser = ReActParser()

    def test_parse_thought_and_answer(self):
        """直接回答（无工具调用）。"""
        text = """Thought: 用户在打招呼，不需要工具
Answer: 你好！我是 Logos 新闻助手，有什么可以帮你的？"""

        steps = self.parser.parse(text)

        assert len(steps) == 2
        assert steps[0].step_type == "thought"
        assert "打招呼" in steps[0].content
        assert steps[1].step_type == "answer"
        assert "你好" in steps[1].content

    def test_parse_thought_action(self):
        """解析 Thought + Action + Action Input。"""
        text = """Thought: 用户想了解 AI 情报，需要检索证据
Action: search_evidence
Action Input: {"query": "AI 情报", "top_k": 5}"""

        steps = self.parser.parse(text)

        assert len(steps) == 2
        assert steps[0].step_type == "thought"
        assert steps[1].step_type == "action"
        assert steps[1].tool_name == "search_evidence"
        assert steps[1].tool_input == {"query": "AI 情报", "top_k": 5}

    def test_parse_action_without_input(self):
        """Action 无参数。"""
        text = """Thought: 需要查询结构化事实
Action: query_intel_facts
Action Input: {}"""

        steps = self.parser.parse(text)

        assert len(steps) == 2
        assert steps[1].step_type == "action"
        assert steps[1].tool_name == "query_intel_facts"
        assert steps[1].tool_input == {}

    def test_parse_multiline_answer(self):
        """多行 Answer。"""
        text = """Thought: 信息充足
Answer: 根据搜索结果，最近的 AI 新闻包括：

1. **GPT-5 发布** — OpenAI 发布了最新模型
2. **DeepMind 研究** — Google 发表新论文

这些进展表明 AI 领域发展迅速。"""

        steps = self.parser.parse(text)

        assert len(steps) == 2
        assert steps[1].step_type == "answer"
        assert "GPT-5" in steps[1].content
        assert "DeepMind" in steps[1].content

    def test_parse_empty_input(self):
        """空输入。"""
        steps = self.parser.parse("")
        assert len(steps) == 0

    def test_parse_unparseable_as_answer(self):
        """无法解析的内容视为 answer。"""
        text = "这是一段普通文本，没有任何标记。"

        steps = self.parser.parse(text)

        assert len(steps) == 1
        assert steps[0].step_type == "answer"
        assert steps[0].content == text


# ======================================================================
# 2. JSON 输入解析（含容错）
# ======================================================================


class TestJsonParsing:
    """测试 Action Input 的 JSON 解析。"""

    def test_valid_json(self):
        result = ReActParser._parse_json_input('{"query": "test", "top_k": 5}')
        assert result == {"query": "test", "top_k": 5}

    def test_json_with_markdown_fence(self):
        result = ReActParser._parse_json_input('```json\n{"query": "test"}\n```')
        assert result == {"query": "test"}

    def test_invalid_json_with_braces(self):
        """提取花括号内容。"""
        result = ReActParser._parse_json_input('some text {"query": "test"} more text')
        assert result == {"query": "test"}

    def test_plain_string_fallback(self):
        """纯文本回退为 query 参数。"""
        result = ReActParser._parse_json_input("AI 新闻搜索")
        assert result == {"query": "AI 新闻搜索"}

    def test_empty_string(self):
        result = ReActParser._parse_json_input("")
        assert result == {}


# ======================================================================
# 3. 流式解析器
# ======================================================================


class TestStreamingReActParser:
    """测试流式 ReAct 解析器。"""

    def setup_method(self):
        self.parser = StreamingReActParser()

    def test_single_thought(self):
        steps = self.parser.feed("Thought: 用户在问问题\n")
        assert len(steps) == 1
        assert steps[0].step_type == "thought"
        assert steps[0].content == "用户在问问题"

    def test_action_across_tokens(self):
        """Action 和 Action Input 跨多个 token。"""
        steps1 = self.parser.feed("Action: search")
        assert len(steps1) == 0  # 还没换行

        steps2 = self.parser.feed("_evidence\n")
        # Action 行完成但不生成步骤（等 Action Input）
        assert len(steps2) == 0

        steps3 = self.parser.feed('Action Input: {"query": "AI"}\n')
        assert len(steps3) == 1
        assert steps3[0].step_type == "action"
        assert steps3[0].tool_name == "search_evidence"
        assert steps3[0].tool_input == {"query": "AI"}

    def test_flush_remaining(self):
        """flush 处理缓冲区剩余内容。"""
        self.parser.feed("Answer: 你好世界")
        # 没有 \n，不会产生步骤
        steps = self.parser.flush()
        # flush 应该产出 answer
        assert any(s.step_type == "answer" for s in steps)

    def test_reset(self):
        """重置清空状态。"""
        self.parser.feed("Thought: 测试\n")
        self.parser.reset()
        assert self.parser._buffer == ""
        assert self.parser._current_step_type is None
