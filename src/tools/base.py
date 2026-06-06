"""工具基类 / Tool Base Class

定义所有工具的统一接口：execute() + get_schema()。
Defines unified interface: execute() + get_schema() returning OpenAI function calling format.
Defines unified interface: execute() + get_schema() returning OpenAI function calling format.
所有内置工具（12 个）都继承 BaseTool。
All 12 built-in tools inherit from BaseTool.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ToolResult:
    """工具执行结果 / Tool Execution Result — Unified return format.

    Attributes:
        output: 成功时的输出文本 / Output text on success
        error: 失败时的错误信息 / Error message on failure
        success: 是否执行成功 / Whether execution succeeded
    """
    output: str = ""
    error: str = ""
    success: bool = True

    def to_text(self) -> str:
        if self.error:
            return f"Error: {self.error}"
        return self.output


class BaseTool(ABC):
    """工具基类 / Tool Base Class — 所有内置工具必须继承并实现 execute() 和 get_schema()。"""

    name: str = ""
    description: str = ""

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """执行工具 / Execute tool"""
        pass

    @abstractmethod
    def get_schema(self) -> dict:
        """返回 OpenAI function calling 格式的 schema / Return OpenAI function calling schema"""
        pass
