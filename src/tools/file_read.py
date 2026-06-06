"""文件读取工具 / File Read Tool（v0.5.0 — 使用共享沙箱模块）

修复:
Fixes:
- C-05: 沙箱目录动态获取 cwd() / Dynamic cwd() for sandbox dirs
- C-10: 使用共享 _security_utils / Use shared module, eliminate duplication
"""

import aiofiles
from pathlib import Path
from .base import BaseTool, ToolResult
from ._security_utils import check_sandbox


class ReadTool(BaseTool):
    name = "read"
    description = "Read file contents"

    async def execute(
        self,
        path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> ToolResult:
        """读取文件内容 / Read file content"""
        try:
            file_path = Path(path).expanduser()
            safe, reason = check_sandbox(file_path)
            if not safe:
                return ToolResult(error=f"⛔ {reason}", success=False)
            if not file_path.exists():
                return ToolResult(error=f"File not found: {path}", success=False)
            if not file_path.is_file():
                return ToolResult(error=f"Not a file: {path}", success=False)

            async with aiofiles.open(file_path, "r", encoding="utf-8", errors="replace") as f:
                lines = await f.readlines()

            total = len(lines)
            start = max(0, offset)
            end = min(total, start + limit)
            selected = lines[start:end]

            result = "".join(selected)
            if end < total:
                result += f"\n... ({total - end} more lines, showing {start+1}-{end} of {total})"

            return ToolResult(output=result)

        except Exception as e:
            return ToolResult(error=str(e), success=False)

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "read",
                "description": "Read file contents. Supports text files with line-based offset and limit.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path to read"
                        },
                        "offset": {
                            "type": "integer",
                            "description": "Starting line number (0-indexed)"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum lines to read"
                        }
                    },
                    "required": ["path"]
                }
            }
        }
