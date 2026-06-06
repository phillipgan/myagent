"""数据分析工具 / Data Analysis Tool — Excel/CSV/PDF + pandas

支持操作：
Supported Operations:
  - info: 文件概览 / File overview (rows, dtypes, nulls)
  - head: 前 N 行预览 / First N rows preview
  - describe: 描述性统计 / Descriptive statistics
  - columns: 列名和样本值 / Column names and sample values
  - query: 安全查询 / Safe query (filter/compare/sort, no eval)

安全设计：
Safety Design:
  - C-03: 文件路径沙箱检查 / File path sandbox check
  - C-04: 禁用 df.query() eval / Disable df.query() eval, use safe column filtering
"""

import asyncio
import logging
import re
from pathlib import Path
from .base import BaseTool, ToolResult
# C-03: 使用共享沙箱检查 / Use shared sandbox check
from ._security_utils import check_sandbox

logger = logging.getLogger(__name__)


class DataAnalysisTool(BaseTool):
    name = "data_analysis"
    description = "Analyze data files (CSV, Excel, JSON). Provide statistics, summaries, and insights."

    async def execute(
        self,
        action: str = "info",
        file_path: str = "",
        query: str = "",
    ) -> ToolResult:
        """数据分析 / Data analysis"""
        try:
            import pandas as pd
        except ImportError:
            return ToolResult(error="pandas not installed. Run: pip install pandas openpyxl", success=False)

        if not file_path:
            return ToolResult(error="file_path is required", success=False)

        fpath = Path(file_path).expanduser()

        # C-03: 沙箱检查 / Sandbox check
        safe, reason = check_sandbox(fpath)
        if not safe:
            return ToolResult(error=f"⛔ {reason}", success=False)

        if not fpath.exists():
            return ToolResult(error=f"File not found: {file_path}", success=False)

        suffix = fpath.suffix.lower()
        try:
            if suffix == ".csv":
                df = await asyncio.to_thread(pd.read_csv, fpath)
            elif suffix in (".xlsx", ".xls"):
                df = await asyncio.to_thread(pd.read_excel, fpath)
            elif suffix == ".json":
                df = await asyncio.to_thread(pd.read_json, fpath)
            elif suffix == ".tsv":
                df = await asyncio.to_thread(pd.read_csv, fpath, sep="\t")
            else:
                return ToolResult(error=f"Unsupported format: {suffix}", success=False)
        except Exception as e:
            return ToolResult(error=f"Read failed: {e}", success=False)

        # 执行分析 / Execute analysis
        if action == "info":
            result = self._info(df, fpath)
        elif action == "head":
            result = self._head(df)
        elif action == "describe":
            result = self._describe(df)
        elif action == "columns":
            result = self._columns(df)
        elif action == "query":
            if not query:
                return ToolResult(error="query is required for 'query' action", success=False)
            result = self._safe_query(df, query)
        else:
            result = self._info(df, fpath)

        return ToolResult(output=result)

    def _info(self, df, fpath) -> str:
        lines = [
            f"📊 File: {fpath.name}",
            f"Shape: {df.shape[0]} rows × {df.shape[1]} columns",
            f"\nColumns:",
        ]
        for col in df.columns:
            dtype = df[col].dtype
            nulls = df[col].isnull().sum()
            lines.append(f"  • {col} ({dtype}) — {nulls} nulls")
        lines.append(f"\nMemory: {df.memory_usage(deep=True).sum() / 1024:.1f} KB")
        return "\n".join(lines)

    def _head(self, df, n=10) -> str:
        return f"First {n} rows:\n{df.head(n).to_string()}"

    def _describe(self, df) -> str:
        return f"Statistics:\n{df.describe(include='all').to_string()}"

    def _columns(self, df) -> str:
        lines = ["Columns:"]
        for col in df.columns:
            sample = df[col].dropna().head(3).tolist()
            lines.append(f"  {col}: {sample}")
        return "\n".join(lines)

    def _safe_query(self, df, query: str) -> str:
        """C-04: 安全查询 / Safe query — no df.query() eval, use safe column filtering

        支持的查询格式:
Supported query formats:
        - 列名: "price" → 显示该列描述 / Column name: show column description
        - 筛选: "price > 100" → 按条件筛选 / Filter: "price > 100" → conditional filter
        - 排序: "sort by price desc" → 按列排序 / Sort: "sort by price desc" → sort by column
        """
        query = query.strip()
        if len(query) > 500:
            return "Query too long (max 500 characters)."

        # 检查是否只是列名 / Check if only column name
        if query in df.columns:
            return f"Column '{query}':\n{df[query].describe().to_string()}"

        # 尝试解析为比较筛选 / Try parse as comparison filter: "column operator value"
        filter_match = re.match(
            r'^(\w+)\s*(>=|<=|!=|==|>|<)\s*(.+)$', query
        )
        if filter_match:
            col_name, operator, value_str = filter_match.groups()
            if col_name not in df.columns:
                return f"Column '{col_name}' not found. Available: {', '.join(df.columns[:20])}"

            # 安全的值解析 / Safe value parsing
            try:
                # 尝试数值 / Try numeric
                value = float(value_str.strip().strip('"').strip("'"))
            except ValueError:
                value = value_str.strip().strip('"').strip("'")

            # 使用安全的布尔索引 / Use safe boolean indexing instead of df.query()
            try:
                col = df[col_name]
                if operator == ">":
                    filtered = df[col > value]
                elif operator == ">=":
                    filtered = df[col >= value]
                elif operator == "<":
                    filtered = df[col < value]
                elif operator == "<=":
                    filtered = df[col <= value]
                elif operator == "!=":
                    filtered = df[col != value]
                elif operator == "==":
                    filtered = df[col == value]
                else:
                    return f"Unsupported operator: {operator}"

                return f"Filter: {query}\nResult: {len(filtered)} rows (of {len(df)})\n{filtered.head(20).to_string()}"
            except Exception as e:
                return f"Filter failed: {e}"

        # 尝试排序 / Try sorting: "sort by column [asc|desc]"
        sort_match = re.match(r'^sort\s+by\s+(\w+)(?:\s+(asc|desc))?$', query, re.IGNORECASE)
        if sort_match:
            col_name = sort_match.group(1)
            ascending = sort_match.group(2) != "desc" if sort_match.group(2) else True
            if col_name not in df.columns:
                return f"Column '{col_name}' not found. Available: {', '.join(df.columns[:20])}"
            try:
                sorted_df = df.sort_values(by=col_name, ascending=ascending)
                return f"Sort by {col_name} {'asc' if ascending else 'desc'}:\n{sorted_df.head(20).to_string()}"
            except Exception as e:
                return f"Sort failed: {e}"

        # 无法解析的查询 / Unparseable query
        return (
            f"Cannot parse query: '{query}'\n"
            f"Supported formats:\n"
            f"  - Column name: 'price'\n"
            f"  - Filter: 'price > 100'\n"
            f"  - Sort: 'sort by price desc'\n"
            f"Available columns: {', '.join(df.columns[:20])}"
        )

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "data_analysis",
                "description": "Analyze data files (CSV, Excel, JSON, TSV). Actions: 'info' overview, 'head' first rows, 'describe' statistics, 'columns' sample values, 'query' filter/sort data (safe column operations only).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["info", "head", "describe", "columns", "query"], "description": "Analysis action"},
                        "file_path": {"type": "string", "description": "Path to data file"},
                        "query": {"type": "string", "description": "Query string (for 'query' action). Supports: column name, 'col > value' filter, 'sort by col desc'"},

                    },
                    "required": ["action", "file_path"]
                }
            }
        }
