"""网络搜索工具 / Web Search Tool

优先使用 Brave Search API，无 key 时降级到 DuckDuckGo。
Prefers Brave Search API, falls back to DuckDuckGo HTML parsing when no API key.
Brave 返回结构化结果，DuckDuckGo 解析 HTML。
Brave returns structured results, DuckDuckGo parses HTML for results.
"""

import os
import re
import httpx
from .base import BaseTool, ToolResult


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web using Brave Search API"

    async def execute(
        self,
        query: str,
        count: int = 5,
    ) -> ToolResult:
        """网络搜索 / Web search"""
        api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "")
        if not api_key:
            # 降级到 DuckDuckGo / Fallback to DuckDuckGo
            return await self._duckduckgo(query, count)

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={"X-Subscription-Token": api_key, "Accept": "application/json"},
                    params={"q": query, "count": count},
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for item in data.get("web", {}).get("results", []):
                results.append(
                    f"**{item.get('title', '')}**\n{item.get('url', '')}\n{item.get('description', '')}"
                )

            return ToolResult(output="\n\n---\n\n".join(results) if results else "No results found")

        except Exception as e:
            return ToolResult(error=str(e), success=False)

    async def _duckduckgo(self, query: str, count: int) -> ToolResult:
        """DuckDuckGo 降级搜索 / DuckDuckGo Fallback Search (L-08: HTML parsing).

        解析 DuckDuckGo HTML 页面中的结果链接和摘要。
Parses DuckDuckGo HTML for result links and snippets.
        如果主解析失败，尝试简单链接提取作为备用。
Falls back to simple link extraction if main parsing fails.
        """
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": "Mozilla/5.0 (compatible; MyAgent/0.4)"},
                )
                resp.raise_for_status()
                html = resp.text

            # 解析 DuckDuckGo HTML 结果 / Parse DuckDuckGo HTML results
            results = []
            # DuckDuckGo 结果块 / DuckDuckGo result blocks
            blocks = re.findall(
                r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>.*?'
                r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
                html, re.DOTALL | re.IGNORECASE
            )
            for url, title, snippet in blocks[:count]:
                title_clean = re.sub(r'<[^>]+>', '', title).strip()
                snippet_clean = re.sub(r'<[^>]+>', '', snippet).strip()
                results.append(f"**{title_clean}**\n{url}\n{snippet_clean}")

            if not results:
                # 备用：简单提取所有链接 / Fallback: simple extract all links
                links = re.findall(r'<a[^>]+class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html)
                for url, title in links[:count]:
                    title_clean = re.sub(r'<[^>]+>', '', title).strip()
                    results.append(f"**{title_clean}**\n{url}")

            if results:
                return ToolResult(output="\n\n---\n\n".join(results))
            return ToolResult(output=f"No DuckDuckGo results for: {query}")

        except Exception as e:
            return ToolResult(error=f"Search failed: {e}", success=False)

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search the web for information. Returns search results with titles, URLs, and descriptions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query string"
                        },
                        "count": {
                            "type": "integer",
                            "description": "Number of results (default: 5)"
                        }
                    },
                    "required": ["query"]
                }
            }
        }
