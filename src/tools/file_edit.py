"""文件编辑工具 / File Edit Tool — 精确文本替换（v0.5.0 — 使用共享沙箱模块）

修复:
Fixes:
- C-05: 沙箱目录动态获取 cwd()
- C-10: 使用共享 _security_utils / Use shared _security_utils module
"""

import aiofiles
from pathlib import Path
from .base import BaseTool, ToolResult
from ._security_utils import check_sandbox


class EditTool(BaseTool):
    name = "edit"
    description = "Make precise edits to a file using exact text replacement"

    async def execute(
        self,
        path: str,
        old_text: str,
        new_text: str,
    ) -> ToolResult:
        """精确编辑文件 / Precise file edit"""
        try:
            file_path = Path(path).expanduser()
            safe, reason = check_sandbox(file_path)
            if not safe:
                return ToolResult(error=f"⛔ {reason}", success=False)
            if not file_path.exists():
                return ToolResult(error=f"File not found: {path}", success=False)

            async with aiofiles.open(file_path, "r", encoding="utf-8") as f:
                content = await f.read()

            count = content.count(old_text)
            if count == 0:
                return ToolResult(error="old_text not found in file", success=False)
            if count > 1:
                return ToolResult(
                    error=f"old_text found {count} times — must be unique",
                    success=False,
                )

            new_content = content.replace(old_text, new_text)

            async with aiofiles.open(file_path, "w", encoding="utf-8") as f:
                await f.write(new_content)

            return ToolResult(output=f"Replaced 1 occurrence in {path}")

        except Exception as e:
            return ToolResult(error=str(e), success=False)

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "edit",
                "description": "Make precise edits to a file using exact text replacement. oldText must be unique in the file.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path to edit"
                        },
                        "old_text": {
                            "type": "string",
                            "description": "Exact text to find (must be unique)"
                        },
                        "new_text": {
                            "type": "string",
                            "description": "Replacement text"
                        }
                    },
                    "required": ["path", "old_text", "new_text"]
                }
            }
        }
