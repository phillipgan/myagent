"""工具注册表 / Tool Registry"""

import logging
from .base import BaseTool, ToolResult
from .exec import ExecTool
from .file_read import ReadTool
from .file_write import WriteTool
from .file_edit import EditTool
from .web_search import WebSearchTool
from .web_fetch import WebFetchTool

from .email import EmailReadTool, EmailSendTool
from .calendar import CalendarTool
from .data_analysis import DataAnalysisTool
from .feishu_api import FeishuAPITool
from .deep_search import DeepSearchTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """工具注册表 / Tool Registry — Manage all available tools"""

    def __init__(self, llm_router=None):
        self._tools: dict[str, BaseTool] = {}
        self._llm_router = llm_router
        self._register_defaults()

    def _register_defaults(self):
        """注册默认内置工具 / Register default built-in tools (OpenClaw Skills Compatible)"""
        defaults = [
            ExecTool(), ReadTool(), WriteTool(), EditTool(),
            WebSearchTool(), WebFetchTool(),
            EmailReadTool(), EmailSendTool(), CalendarTool(),
            DataAnalysisTool(), FeishuAPITool(),  # M-02: 凭据通过环境变量读取 / Credentials via env vars in FeishuAPITool.__init__
            # L-10: 传入 llm_router 以启用 LLM 综合分析 / Pass llm_router to enable LLM analysis
            DeepSearchTool(llm_router=self._llm_router),
        ]
        for tool in defaults:
            self._tools[tool.name] = tool
        logger.info(f"Registered {len(defaults)} default tools: {list(self._tools.keys())}")

    def register(self, tool: BaseTool):
        """注册自定义工具 / Register custom tool"""
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def get_schemas(self) -> list[dict]:
        """返回所有工具的 schemas / Return OpenAI function calling schemas for all tools"""
        return [tool.get_schema() for tool in self._tools.values()]

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    async def execute(self, tool_name: str, **kwargs) -> ToolResult:
        """执行指定工具 / Execute specified tool — auto-filter unaccepted params"""
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolResult(error=f"Unknown tool: {tool_name}", success=False)
        try:
            # F-01: 过滤 LLM 生成的多余参数 / Filter extra LLM-generated params, only pass accepted ones
            import inspect
            sig = inspect.signature(tool.execute)
            accepted_params = set(sig.parameters.keys())
            filtered_kwargs = {k: v for k, v in kwargs.items() if k in accepted_params}
            if len(filtered_kwargs) < len(kwargs):
                dropped = set(kwargs.keys()) - accepted_params
                logger.debug(f"Tool {tool_name}: dropped unexpected params: {dropped}")
            return await tool.execute(**filtered_kwargs)
        except Exception as e:
            logger.error(f"Tool {tool_name} error: {e}")
            return ToolResult(error=str(e), success=False)
