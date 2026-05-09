"""工具层专用异常层次

继承项目统一异常基类 NewsAssistantError，使工具层异常融入统一的异常体系。

异常层次:
    ToolError                    # 工具层基础异常
    ├── ToolNotFoundError        # 注册中心找不到指定工具
    ├── ToolValidationError      # 工具参数校验失败
    ├── ToolExecutionError       # 工具执行过程中出错
    ├── ToolTimeoutError         # 异步执行超时
    └── ToolChainError           # 工具链执行失败
"""

from core.exceptions import NewsAssistantError


class ToolError(NewsAssistantError):
    """工具层基础异常"""


class ToolNotFoundError(ToolError):
    """注册中心找不到指定工具"""

    def __init__(self, tool_name: str):
        self.tool_name = tool_name
        super().__init__(f"工具 '{tool_name}' 未注册")


class ToolValidationError(ToolError):
    """工具参数校验失败"""

    def __init__(self, tool_name: str, reason: str):
        self.tool_name = tool_name
        self.reason = reason
        super().__init__(f"工具 '{tool_name}' 参数校验失败: {reason}")


class ToolExecutionError(ToolError):
    """工具执行过程中出错"""

    def __init__(self, tool_name: str, reason: str, cause: Exception | None = None):
        self.tool_name = tool_name
        self.reason = reason
        self.cause = cause
        super().__init__(f"工具 '{tool_name}' 执行失败: {reason}")


class ToolTimeoutError(ToolError):
    """异步执行超时"""

    def __init__(self, tool_name: str, timeout: float):
        self.tool_name = tool_name
        self.timeout = timeout
        super().__init__(f"工具 '{tool_name}' 执行超时 ({timeout}s)")


class ToolChainError(ToolError):
    """工具链执行失败"""

    def __init__(self, chain_name: str, step_index: int, reason: str):
        self.chain_name = chain_name
        self.step_index = step_index
        self.reason = reason
        super().__init__(
            f"工具链 '{chain_name}' 在第 {step_index} 步失败: {reason}"
        )
