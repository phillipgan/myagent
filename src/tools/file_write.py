"""文件写入工具 / File Write Tool（v0.5.0 — 使用共享沙箱模块）

修复:
Fixes:
- C-05: 沙箱目录动态获取 cwd()
- C-10: 使用共享 _security_utils / Use shared _security_utils module
- H-M06: 原子写入 / Atomic write (temp file + rename)
"""

import os
import aiofiles
import logging
from pathlib import Path
from .base import BaseTool, ToolResult
from ._security_utils import check_sandbox

logger = logging.getLogger(__name__)


class WriteTool(BaseTool):
    name = "write"
    description = "Write content to a file, creating it if needed"

    async def execute(self, path: str, content: str) -> ToolResult:
        """写入文件（原子写入）/ Write file (atomic)"""
        try:
            file_path = Path(path).expanduser()
            safe, reason = check_sandbox(file_path)
            if not safe:
                return ToolResult(error=f"⛔ {reason}", success=False)
            file_path.parent.mkdir(parents=True, exist_ok=True)

            # 原子写入：先写临时文件，再 rename / Atomic write: temp file then rename
            tmp_path = file_path.with_suffix(file_path.suffix + ".tmp")
            try:
                async with aiofiles.open(tmp_path, "w", encoding="utf-8") as f:
                    await f.write(content)
                # POSIX 上 rename 是原子操作 / POSIX rename is atomic
                os.replace(str(tmp_path), str(file_path))
            except Exception:
                # 清理临时文件 / Clean up temp file
                try:
                    tmp_path.unlink(missing_ok=True)
                except Exception:
                    pass
                raise

            byte_count = len(content.encode("utf-8"))
            char_count = len(content)
            return ToolResult(output=f"Written {byte_count} bytes ({char_count} chars) to {path}")

        except Exception as e:
            return ToolResult(error=str(e), success=False)

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "write",
                "description": "Write content to a file. Creates the file and parent directories if needed.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "File path to write"
                        },
                        "content": {
                            "type": "string",
                            "description": "Content to write"
                        }
                    },
                    "required": ["path", "content"]
                }
            }
        }
