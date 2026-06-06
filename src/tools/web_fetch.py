"""网页内容获取工具 / Web Fetch Tool（v0.5.0 — 使用共享 SSRF 防护）

抓取指定 URL 的网页内容，剥离 HTML 标签，返回纯文本。
Fetches URL content, strips HTML tags, returns plain text.
内置 SSRF 防护：阻止私有 IP、元数据端点、DNS 重绑定。
Built-in SSRF protection: blocks private IPs, metadata endpoints, DNS rebinding.

修复:
Fixes:
- C-10: 使用共享 _security_utils / Use shared _security_utils module
- H-11: 增强 SSRF 防护 / Enhanced SSRF protection (DNS validation, IPv6)
"""

import re
import httpx
from .base import BaseTool, ToolResult
from ._security_utils import is_safe_url


class WebFetchTool(BaseTool):
    name = "web_fetch"
    description = "Fetch and extract readable content from a URL"

    async def execute(
        self,
        url: str,
        max_chars: int = 5000,
    ) -> ToolResult:
        """获取网页内容 / Fetch web content"""
        try:
            # H-11: 使用增强的 SSRF 防护 / Enhanced SSRF protection
            safe, reason = is_safe_url(url)
            if not safe:
                return ToolResult(error=f"⛔ URL blocked: {reason}", success=False)

            async with httpx.AsyncClient(
                timeout=20, follow_redirects=True
            ) as client:
                resp = await client.get(url, headers={
                    "User-Agent": "Mozilla/5.0 (compatible; MyAgent/0.1)"
                })
                resp.raise_for_status()
                content = resp.text

            # HTML 清理 / HTML cleanup
            content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
            content = re.sub(r'<[^>]+>', ' ', content)
            content = re.sub(r'\s+', ' ', content).strip()

            if len(content) > max_chars:
                content = content[:max_chars] + f"\n\n... (truncated, {len(content)} total chars)"

            return ToolResult(output=content)

        except Exception as e:
            return ToolResult(error=str(e), success=False)

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "web_fetch",
                "description": "Fetch and extract readable content from a URL. Converts HTML to plain text.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "URL to fetch"
                        },
                        "max_chars": {
                            "type": "integer",
                            "description": "Maximum characters to return (default: 5000)"
                        }
                    },
                    "required": ["url"]
                }
            }
        }
