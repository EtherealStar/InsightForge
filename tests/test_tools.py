"""Agent Tools 层单元测试

测试覆盖:
    1. BaseTool — 参数校验、执行、OpenAI Schema 生成
    2. ToolRegistry — 注册/注销/查询/Schema 批量生成
    3. ToolChain — 链式执行、管道传参、失败策略
    4. AsyncToolExecutor — 异步执行、批量执行、超时控制
    5. 异常体系 — 各异常类型正确继承
"""

import asyncio
import time
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock
from typing import Any

from agent.tools.base import BaseTool, ToolParameter, ToolResult
from agent.tools.builtin import register_builtin_tools
from agent.tools.registry import ToolRegistry, get_tool_registry
from agent.tools.chain import ToolChain, ToolChainResult
from agent.tools.executor import AsyncToolExecutor, ToolCall
from agent.tools.errors import (
    ToolError,
    ToolNotFoundError,
    ToolValidationError,
    ToolExecutionError,
    ToolTimeoutError,
    ToolChainError,
)
from core.exceptions import NewsAssistantError


# ======================================================================
# 测试用工具实现
# ======================================================================


class EchoTool(BaseTool):
    """测试用工具：原样返回输入消息。"""

    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "回显输入消息"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="message",
                type="string",
                description="要回显的消息",
            ),
        ]

    def _run(self, message: str, **kwargs) -> str:
        return f"Echo: {message}"


class AddTool(BaseTool):
    """测试用工具：两数相加。"""

    @property
    def name(self) -> str:
        return "add"

    @property
    def description(self) -> str:
        return "计算两个数字的和"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="a", type="number", description="第一个数"),
            ToolParameter(name="b", type="number", description="第二个数"),
        ]

    def _run(self, a: float, b: float, **kwargs) -> float:
        return a + b


class FailTool(BaseTool):
    """测试用工具：始终失败。"""

    @property
    def name(self) -> str:
        return "fail"

    @property
    def description(self) -> str:
        return "总是执行失败的工具"

    @property
    def parameters(self) -> list[ToolParameter]:
        return []

    def _run(self, **kwargs) -> None:
        raise RuntimeError("故意失败")


class SlowTool(BaseTool):
    """测试用工具：模拟耗时操作。"""

    @property
    def name(self) -> str:
        return "slow"

    @property
    def description(self) -> str:
        return "模拟耗时操作"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="duration",
                type="number",
                description="休眠秒数",
                required=False,
                default=1.0,
            ),
        ]

    def _run(self, duration: float = 1.0, **kwargs) -> str:
        time.sleep(duration)
        return f"完成 {duration}s 等待"


class OptionalParamTool(BaseTool):
    """测试用工具：带可选参数和枚举。"""

    @property
    def name(self) -> str:
        return "optional_param"

    @property
    def description(self) -> str:
        return "带可选参数的测试工具"

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="query",
                type="string",
                description="查询文本",
            ),
            ToolParameter(
                name="limit",
                type="integer",
                description="结果数量",
                required=False,
                default=10,
            ),
            ToolParameter(
                name="language",
                type="string",
                description="语言",
                required=False,
                default="zh",
                enum=["zh", "en"],
            ),
        ]

    def _run(self, query: str, limit: int = 10, language: str = "zh", **kwargs) -> dict:
        return {"query": query, "limit": limit, "language": language}


# ======================================================================
# Fixtures
# ======================================================================


@pytest.fixture(autouse=True)
def clean_registry():
    """每个测试前后清空注册中心（避免测试间干扰）。"""
    registry = get_tool_registry()
    registry.clear()
    yield registry
    registry.clear()


# ======================================================================
# 1. BaseTool 测试
# ======================================================================


class TestBaseTool:
    """测试工具基类的核心行为。"""

    def test_execute_success(self):
        tool = EchoTool()
        result = tool.execute(message="hello")

        assert result.success is True
        assert result.data == "Echo: hello"
        assert result.tool_name == "echo"
        assert result.execution_time > 0
        assert result.error is None

    def test_execute_with_number_params(self):
        tool = AddTool()
        result = tool.execute(a=3, b=5)

        assert result.success is True
        assert result.data == 8

    def test_execute_failure_returns_error_result(self):
        tool = FailTool()
        result = tool.execute()

        assert result.success is False
        assert "故意失败" in result.error
        assert result.tool_name == "fail"

    def test_validate_missing_required_param(self):
        tool = EchoTool()

        with pytest.raises(ToolValidationError) as exc_info:
            tool.execute()
        assert "message" in str(exc_info.value)

    def test_validate_unknown_param(self):
        tool = EchoTool()

        with pytest.raises(ToolValidationError) as exc_info:
            tool.execute(message="hi", unknown_param="x")
        assert "unknown_param" in str(exc_info.value)

    def test_validate_wrong_type(self):
        tool = AddTool()

        with pytest.raises(ToolValidationError) as exc_info:
            tool.execute(a="not_a_number", b=5)
        assert "类型错误" in str(exc_info.value)

    def test_default_value_filling(self):
        tool = OptionalParamTool()
        result = tool.execute(query="test")

        assert result.success is True
        assert result.data["query"] == "test"
        assert result.data["limit"] == 10
        assert result.data["language"] == "zh"

    def test_override_default_value(self):
        tool = OptionalParamTool()
        result = tool.execute(query="test", limit=5, language="en")

        assert result.data["limit"] == 5
        assert result.data["language"] == "en"

    def test_to_openai_schema(self):
        tool = OptionalParamTool()
        schema = tool.to_openai_schema()

        assert schema["type"] == "function"
        func = schema["function"]
        assert func["name"] == "optional_param"
        assert "description" in func
        params = func["parameters"]
        assert params["type"] == "object"
        assert "query" in params["properties"]
        assert "limit" in params["properties"]
        assert "language" in params["properties"]
        assert "query" in params["required"]
        assert "limit" not in params.get("required", [])

        # 检查 enum
        lang_schema = params["properties"]["language"]
        assert lang_schema["enum"] == ["zh", "en"]

    def test_to_dict(self):
        tool = EchoTool()
        d = tool.to_dict()

        assert d["name"] == "echo"
        assert d["description"] == "回显输入消息"
        assert len(d["parameters"]) == 1
        assert d["parameters"][0]["name"] == "message"

    def test_tool_result_to_dict(self):
        result = ToolResult(
            success=True, data={"key": "value"}, tool_name="test", execution_time=0.5
        )
        d = result.to_dict()

        assert d["success"] is True
        assert d["data"] == {"key": "value"}
        assert d["tool_name"] == "test"
        assert "error" not in d

    def test_tool_result_error_to_dict(self):
        result = ToolResult(
            success=False, error="boom", tool_name="test", execution_time=0.1
        )
        d = result.to_dict()

        assert d["success"] is False
        assert d["error"] == "boom"
        assert "data" not in d

    def test_repr(self):
        tool = EchoTool()
        r = repr(tool)
        assert "echo" in r
        assert "回显" in r


# ======================================================================
# 2. ToolRegistry 测试
# ======================================================================


class TestToolRegistry:
    """测试工具注册中心。"""

    def test_register_and_get(self, clean_registry):
        registry = clean_registry
        tool = EchoTool()
        registry.register(tool)

        retrieved = registry.get("echo")
        assert retrieved is tool
        assert registry.has("echo")
        assert registry.count == 1

    def test_register_duplicate_raises(self, clean_registry):
        registry = clean_registry
        registry.register(EchoTool())

        with pytest.raises(ToolError, match="已注册"):
            registry.register(EchoTool())

    def test_register_non_tool_raises(self, clean_registry):
        registry = clean_registry

        with pytest.raises(TypeError):
            registry.register("not_a_tool")

    def test_unregister(self, clean_registry):
        registry = clean_registry
        registry.register(EchoTool())
        registry.unregister("echo")

        assert not registry.has("echo")
        assert registry.count == 0

    def test_unregister_not_found_raises(self, clean_registry):
        registry = clean_registry

        with pytest.raises(ToolNotFoundError):
            registry.unregister("nonexistent")

    def test_get_not_found_raises(self, clean_registry):
        registry = clean_registry

        with pytest.raises(ToolNotFoundError):
            registry.get("nonexistent")

    def test_list_tools(self, clean_registry):
        registry = clean_registry
        echo = EchoTool()
        add = AddTool()
        registry.register(echo)
        registry.register(add)

        tools = registry.list_tools()
        assert len(tools) == 2
        assert echo in tools
        assert add in tools

    def test_list_names(self, clean_registry):
        registry = clean_registry
        registry.register(EchoTool())
        registry.register(AddTool())

        names = registry.list_names()
        assert "echo" in names
        assert "add" in names

    def test_get_schemas(self, clean_registry):
        registry = clean_registry
        registry.register(EchoTool())
        registry.register(AddTool())

        schemas = registry.get_schemas()
        assert len(schemas) == 2
        assert all(s["type"] == "function" for s in schemas)

        schema_names = [s["function"]["name"] for s in schemas]
        assert "echo" in schema_names
        assert "add" in schema_names

    def test_contains_and_len(self, clean_registry):
        registry = clean_registry
        registry.register(EchoTool())

        assert "echo" in registry
        assert "nonexistent" not in registry
        assert len(registry) == 1

    def test_clear(self, clean_registry):
        registry = clean_registry
        registry.register(EchoTool())
        registry.register(AddTool())
        registry.clear()

        assert registry.count == 0

    def test_singleton(self):
        r1 = get_tool_registry()
        r2 = get_tool_registry()
        assert r1 is r2

    def test_register_builtin_tools_refreshes_instances(self, clean_registry):
        registry = clean_registry
        service_registry = MagicMock()
        service_registry.has.return_value = True
        service_registry.require.side_effect = lambda name: MagicMock(name=name)
        config_manager = SimpleNamespace(
            service_registry=service_registry,
        )

        first_count = register_builtin_tools(config_manager, refresh=True)
        first_web_search = registry.get("web_search")

        second_count = register_builtin_tools(config_manager, refresh=True)
        second_web_search = registry.get("web_search")

        assert first_count == 14
        assert second_count == 14
        assert first_web_search is not second_web_search
        assert set(registry.list_names()) == {
            "search_evidence",
            "query_intel_facts",
            "get_intel_fact",
            "create_intel_fact",
            "update_intel_fact",
            "link_fact_to_competitor",
            "link_fact_to_product",
            "create_insight_claim",
            "query_insight_claims",
            "web_search",
            "list_competitors",
            "get_competitor_profile",
            "compare_competitors",
            "generate_analysis_report",
        }

    def test_builtin_tool_definitions_do_not_keep_legacy_tools(self):
        from agent.tools.builtin.definitions import create_builtin_tool_definition_registry

        definition_registry = create_builtin_tool_definition_registry()

        assert "search_evidence" in definition_registry.active_tool_names()
        assert definition_registry.removed_tool_names() == []
        assert not {
            "query_knowledge_base",
            "get_recent_news",
            "get_news_stats",
            "read_article",
            "generate_brief",
        } & set(definition_registry.active_tool_names())

    def test_builtin_tool_factory_skips_missing_service(self):
        from agent.tools.builtin.definitions import create_builtin_tool_definition_registry
        from agent.tools.builtin.factory import BuiltinToolFactory
        from services.service_registry import ServiceRegistry

        definition_registry = create_builtin_tool_definition_registry()
        factory = BuiltinToolFactory(ServiceRegistry({"intel_service": object()}))

        assert factory.create(definition_registry.get("query_intel_facts")) is not None
        assert factory.create(definition_registry.get("search_evidence")) is None

    def test_search_evidence_passes_filters_to_hybrid_service(self):
        from agent.tools.builtin.search_evidence import SearchEvidenceTool
        from models.document import HybridDocumentSearchResult, ParentDocumentChunk

        service = MagicMock()
        service.search.return_value = [
            HybridDocumentSearchResult(
                parent_chunk=ParentDocumentChunk(
                    parent_chunk_id="p1",
                    document_id="doc1",
                    content="Cursor released a new feature.",
                    token_count=10,
                    child_point_ids=["c1"],
                    doc_name="Doc",
                    url="https://example.com",
                ),
                rrf_score=0.3,
                match_sources=["semantic"],
            )
        ]
        result = SearchEvidenceTool(service).execute(
            query="Cursor feature",
            top_k=3,
            competitor_ids=[1],
            document_type="article",
            date_from="2026-01-01",
            date_to="2026-01-31",
        )

        assert result.success is True
        service.search.assert_called_once_with(
            query="Cursor feature",
            top_k=3,
            filters={
                "competitor_ids": [1],
                "document_type": "article",
                "date_from": "2026-01-01",
                "date_to": "2026-01-31",
            },
        )

    def test_search_evidence_rejects_invalid_date_without_calling_service(self):
        from agent.tools.builtin.search_evidence import SearchEvidenceTool

        service = MagicMock()
        result = SearchEvidenceTool(service).execute(
            query="Cursor",
            date_from="2026/01/01",
        )

        assert result.success is False
        service.search.assert_not_called()

    def test_generate_analysis_report_tool_delegates_to_report_service(self):
        from agent.tools.builtin.generate_analysis_report import GenerateAnalysisReportTool

        report_service = MagicMock()
        report_service.generate_analysis_report.return_value = {
            "report_id": 7,
            "status": "waiting_review",
            "review_status": "passed",
        }

        result = GenerateAnalysisReportTool(report_service).execute(
            competitor_ids=["1", 2],
            report_type="comparison",
            focus="pricing",
            dimensions=["product"],
            date_from="2026-01-01",
            date_to="2026-01-31",
            auto_publish=True,
        )

        assert result.success is True
        assert result.data["status"] == "waiting_review"
        report_service.generate_analysis_report.assert_called_once_with(
            [1, 2],
            report_type="comparison",
            focus="pricing",
            dimensions=["product"],
            date_from="2026-01-01",
            date_to="2026-01-31",
            auto_publish=True,
        )


# ======================================================================
# 3. ToolChain 测试
# ======================================================================


class TestToolChain:
    """测试工具链管理系统。"""

    def test_single_step_chain(self, clean_registry):
        registry = clean_registry
        registry.register(EchoTool())

        chain = ToolChain("test_chain")
        chain.add_step("echo", params={"message": "hello"})

        result = chain.run()
        assert result.success is True
        assert len(result.step_results) == 1
        assert result.last_result.data == "Echo: hello"
        assert result.total_time > 0

    def test_multi_step_chain(self, clean_registry):
        registry = clean_registry
        registry.register(EchoTool())
        registry.register(AddTool())

        chain = ToolChain("multi_chain")
        chain.add_step("echo", params={"message": "step1"})
        chain.add_step("add", params={"a": 3, "b": 5})

        result = chain.run()
        assert result.success is True
        assert len(result.step_results) == 2
        assert result.step_results[0].data == "Echo: step1"
        assert result.step_results[1].data == 8

    def test_pipe_placeholder(self, clean_registry):
        """测试 $prev 管道传参。"""
        registry = clean_registry
        registry.register(EchoTool())

        # 第二步的 message 使用上一步结果
        chain = ToolChain("pipe_chain")
        chain.add_step("echo", params={"message": "first"})
        chain.add_step("echo", params={"message": "$prev"})

        result = chain.run()
        assert result.success is True
        # 第二步的输入是 "Echo: first"（上一步的 data）
        assert result.step_results[1].data == "Echo: Echo: first"

    def test_stop_on_failure(self, clean_registry):
        """测试 stop_on_failure=True 时链中断。"""
        registry = clean_registry
        registry.register(EchoTool())
        registry.register(FailTool())

        chain = ToolChain("fail_chain", stop_on_failure=True)
        chain.add_step("echo", params={"message": "ok"})
        chain.add_step("fail")
        chain.add_step("echo", params={"message": "不应该执行"})

        with pytest.raises(ToolChainError) as exc_info:
            chain.run()
        assert exc_info.value.step_index == 1

    def test_continue_on_failure(self, clean_registry):
        """测试 stop_on_failure=False 时链继续。"""
        registry = clean_registry
        registry.register(EchoTool())
        registry.register(FailTool())

        chain = ToolChain("continue_chain", stop_on_failure=False)
        chain.add_step("echo", params={"message": "step1"})
        chain.add_step("fail")
        chain.add_step("echo", params={"message": "step3"})

        result = chain.run()
        assert result.success is False
        assert result.failed_step == 1
        assert len(result.step_results) == 3
        assert result.step_results[0].success is True
        assert result.step_results[1].success is False
        assert result.step_results[2].success is True

    def test_empty_chain(self, clean_registry):
        chain = ToolChain("empty")
        result = chain.run()

        assert result.success is True
        assert len(result.step_results) == 0

    def test_fluent_api(self):
        chain = ToolChain("fluent")
        returned = chain.add_step("a").add_step("b").add_step("c")

        assert returned is chain
        assert chain.step_count == 3

    def test_chain_result_to_dict(self, clean_registry):
        registry = clean_registry
        registry.register(EchoTool())

        chain = ToolChain("dict_test")
        chain.add_step("echo", params={"message": "hi"})
        result = chain.run()

        d = result.to_dict()
        assert d["success"] is True
        assert d["chain_name"] == "dict_test"
        assert len(d["steps"]) == 1

    def test_tool_not_found_in_chain(self, clean_registry):
        chain = ToolChain("missing_tool")
        chain.add_step("nonexistent_tool")

        with pytest.raises(ToolChainError):
            chain.run()

    def test_repr(self):
        chain = ToolChain("test")
        chain.add_step("a").add_step("b")
        r = repr(chain)
        assert "test" in r
        assert "a" in r
        assert "b" in r


# ======================================================================
# 4. AsyncToolExecutor 测试
# ======================================================================


class TestAsyncToolExecutor:
    """测试异步工具执行器。"""

    @pytest.fixture
    def executor(self, clean_registry):
        registry = clean_registry
        registry.register(EchoTool())
        registry.register(AddTool())
        registry.register(FailTool())
        registry.register(SlowTool())

        executor = AsyncToolExecutor(max_workers=2, default_timeout=5.0)
        yield executor
        executor.shutdown()

    def test_execute_single(self, executor):
        result = asyncio.get_event_loop().run_until_complete(
            executor.execute("echo", message="async hello")
        )

        assert result.success is True
        assert result.data == "Echo: async hello"

    def test_execute_not_found(self, executor):
        result = asyncio.get_event_loop().run_until_complete(
            executor.execute("nonexistent")
        )

        assert result.success is False
        assert "未注册" in result.error

    def test_execute_batch(self, executor):
        calls = [
            ToolCall("echo", {"message": "a"}),
            ToolCall("add", {"a": 1, "b": 2}),
            ToolCall("echo", {"message": "c"}),
        ]

        results = asyncio.get_event_loop().run_until_complete(
            executor.execute_batch(calls)
        )

        assert len(results) == 3
        assert results[0].data == "Echo: a"
        assert results[1].data == 3
        assert results[2].data == "Echo: c"

    def test_execute_batch_empty(self, executor):
        results = asyncio.get_event_loop().run_until_complete(
            executor.execute_batch([])
        )
        assert results == []

    def test_execute_with_timeout_success(self, executor):
        result = asyncio.get_event_loop().run_until_complete(
            executor.execute_with_timeout(
                "echo", timeout=5.0, message="fast"
            )
        )
        assert result.success is True

    def test_execute_with_timeout_expired(self, executor):
        result = asyncio.get_event_loop().run_until_complete(
            executor.execute_with_timeout(
                "slow", timeout=0.1, duration=5.0
            )
        )

        assert result.success is False
        assert "超时" in result.error

    def test_execute_chain(self, executor, clean_registry):
        chain = ToolChain("async_chain")
        chain.add_step("echo", params={"message": "step1"})
        chain.add_step("add", params={"a": 10, "b": 20})

        result = asyncio.get_event_loop().run_until_complete(
            executor.execute_chain(chain)
        )

        assert result.success is True
        assert len(result.step_results) == 2


# ======================================================================
# 5. 异常体系测试
# ======================================================================


class TestExceptions:
    """测试异常层次结构。"""

    def test_tool_error_inherits_base(self):
        assert issubclass(ToolError, NewsAssistantError)

    def test_tool_not_found_error(self):
        err = ToolNotFoundError("my_tool")
        assert err.tool_name == "my_tool"
        assert "my_tool" in str(err)
        assert isinstance(err, ToolError)
        assert isinstance(err, NewsAssistantError)

    def test_tool_validation_error(self):
        err = ToolValidationError("my_tool", "缺少参数 x")
        assert err.tool_name == "my_tool"
        assert "缺少参数 x" in str(err)
        assert isinstance(err, ToolError)

    def test_tool_execution_error(self):
        cause = RuntimeError("boom")
        err = ToolExecutionError("my_tool", "执行失败", cause)
        assert err.cause is cause
        assert isinstance(err, ToolError)

    def test_tool_timeout_error(self):
        err = ToolTimeoutError("my_tool", 30.0)
        assert err.timeout == 30.0
        assert "30.0" in str(err)
        assert isinstance(err, ToolError)

    def test_tool_chain_error(self):
        err = ToolChainError("my_chain", 2, "工具不存在")
        assert err.chain_name == "my_chain"
        assert err.step_index == 2
        assert isinstance(err, ToolError)

    def test_all_catchable_by_base(self):
        """所有工具异常都可以被 NewsAssistantError 捕获。"""
        exceptions = [
            ToolError("test"),
            ToolNotFoundError("x"),
            ToolValidationError("x", "y"),
            ToolExecutionError("x", "y"),
            ToolTimeoutError("x", 1.0),
            ToolChainError("x", 0, "y"),
        ]
        for exc in exceptions:
            assert isinstance(exc, NewsAssistantError), (
                f"{type(exc).__name__} 不继承 NewsAssistantError"
            )
