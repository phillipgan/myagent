"""LLM 提供商基类 / LLM Provider Base Class"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import AsyncIterator


@dataclass
class LLMResponse:
    """LLM 响应 / LLM Response"""
    content: str = ""
    tool_calls: list = None  # list[ToolCall]
    model: str = ""
    usage: dict = None

    def __post_init__(self):
        if self.tool_calls is None:
            self.tool_calls = []
        # H-15: usage 默认空 dict / Default empty dict, avoid downstream None crash
        if self.usage is None:
            self.usage = {}


@dataclass
class ToolCall:
    """工具调用 / Tool Call"""
    id: str
    name: str
    arguments: dict


class LLMProvider(ABC):
    """LLM 提供商基类 / LLM Provider Base Class"""

    def __init__(self, base_url: str = "", api_key: str = "", **kwargs):
        self.base_url = base_url
        self.api_key = api_key

    async def close(self):
        """关闭资源（连接池等）/ Close resources (connection pools)"""
        pass

    @abstractmethod
    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """发送聊天请求 / Send chat request"""
        pass
