"""Deep Search 工具 / Deep Search Tool — Multi-source parallel + Cross-validation + LLM analysis

核心能力：
Core Capabilities:
  1. 同时调用 3-10 个搜索引擎 / Query 3-10 search engines simultaneously
  2. 交叉验证，标注可信度 / Cross-validate results, annotate credibility
  3. 可选 LLM 综合分析 / Optional LLM analysis (Zhipu GLM-5.1)
  4. 自动保存搜索报告 / Auto-save search reports to local files

使用场景：研究型查询。
Use case: research queries requiring depth and breadth.
"""

import json
import logging
from datetime import datetime

from .base import BaseTool, ToolResult
from .search_engine import ParallelSearchEngine

logger = logging.getLogger(__name__)


class DeepSearchTool(BaseTool):
    name = "deep_search"
    description = (
        "Perform a deep multi-source parallel search using 3-10 search engines simultaneously. "
        "Results are cross-validated across sources for credibility. "
        "Returns ranked results with source attribution."
    )

    def __init__(self, llm_router=None):
        self._engine = None
        self.llm = llm_router

    def _get_engine(self) -> ParallelSearchEngine:
        if self._engine is None:
            self._engine = ParallelSearchEngine()
        return self._engine

    async def execute(
        self,
        query: str,
        max_sources: int = 0,
        count_per_source: int = 5,
        fetch_content: bool = False,
        analyze: bool = False,
        save_report: bool = True,
    ) -> ToolResult:
        """执行深度搜索 / Execute deep search.

        Args:
            query: 搜索查询字符串 / Search query string
            max_sources: 最大搜索引擎数（0=全部可用）/ Max search engines (0=all available)
            count_per_source: 每个引擎返回的结果数 / Results per engine
            fetch_content: 是否抓取页面全文（更慢但更详细）/ Fetch full page content (slower but richer)
            analyze: 是否调用 LLM 做综合分析 / Whether to call LLM for analysis
            save_report: 是否保存报告到文件 / Whether to save report to file
        """
        engine = self._get_engine()

        # 1. 并行搜索 / 1. Parallel search
        report = await engine.search(
            query=query,
            count_per_source=count_per_source,
            max_sources=max_sources,
            fetch_content=fetch_content,
        )

        # 2. 可选：LLM 综合分析 / 2. Optional: LLM analysis
        if analyze and self.llm:
            analysis = await self._analyze_with_llm(query, report)
            report.summary = analysis

        # 3. 保存报告 / 3. Save report
        filepath = ""
        if save_report:
            filepath = await report.save()

        # 4. 构造输出 / 4. Build output
        output_parts = [
            report.to_text(),
        ]

        if report.summary:
            output_parts.append(f"\n📝 LLM 综合分析:\n{report.summary}")

        if filepath:
            output_parts.append(f"\n💾 报告已保存: {filepath}")

        return ToolResult(
            output="\n".join(output_parts),
        )

    async def _analyze_with_llm(self, query: str, report) -> str:
        """用 LLM 综合分析搜索结果 / LLM analysis — cross-validate, annotate sources, assess credibility"""
        # 收集片段 / Collect snippets
        snippets = []
        for r in report.cross_validated_results[:8]:
            snippets.append(f"[{r.source.value}] {r.title}\n{r.snippet[:300]}")

        if not snippets:
            for r in report.results[:8]:
                snippets.append(f"[{r.source.value}] {r.title}\n{r.snippet[:300]}")

        if not snippets:
            return "No results to analyze."

        try:
            response = await self.llm.chat(
                messages=[
                    {"role": "system", "content": (
                        "你是一个专业的研究分析助手。基于以下多源搜索结果，请：\n"
                        "1. 综合各来源信息，给出一个完整、客观的总结\n"
                        "2. 标注信息来源（如 [brave]、[tavily] 等）\n"
                        "3. 指出各来源间的共识和分歧\n"
                        "4. 评估信息的总体可信度"
                    )},
                    {"role": "user", "content": f"查询: {query}\n\n搜索结果:\n" + "\n\n".join(snippets)},
                ],
                model="zai/glm-5.1",
            )
            return response.content
        except Exception as e:
            logger.warning(f"LLM analysis failed: {e}")
            return f"Analysis unavailable: {e}"

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "deep_search",
                "description": (
                    "Deep multi-source parallel search. Queries 3-10 search engines simultaneously, "
                    "cross-validates results, and returns ranked results with source attribution. "
                    "Use this for research questions requiring comprehensive, verified information."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query string",
                        },
                        "max_sources": {
                            "type": "integer",
                            "description": "Max search sources to use (0=all available, 3-10 recommended)",
                        },
                        "count_per_source": {
                            "type": "integer",
                            "description": "Results per source (default: 5)",
                        },
                        "fetch_content": {
                            "type": "boolean",
                            "description": "Whether to fetch full page content (slower, default: false)",
                        },
                        "analyze": {
                            "type": "boolean",
                            "description": "Whether to run LLM analysis on results (default: false)",
                        },
                        "save_report": {
                            "type": "boolean",
                            "description": "Save report to file (default: true)",
                        },
                    },
                    "required": ["query"],
                },
            },
        }
