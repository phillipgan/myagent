"""并行多源搜索引擎 / Parallel Multi-Source Search Engine — Core Module

支持 3-10 个搜索源并行查询、交叉比对、来源追踪。
Supports 3-10 parallel search sources, cross-validation, source tracking.

架构：
Architecture:
  - SearchSource (Enum): 搜索源枚举 / Search source enum (Brave/Tavily/DuckDuckGo/Serper)
  - SearchResult (dataclass): 统一结果格式 / Unified result format
  - SearchReport (dataclass): 搜索报告 / Search report (aggregate + cross-validate + save)
  - BaseSearchProvider (ABC): 搜索提供者基类 / Search provider base class
  - ParallelSearchEngine: 并行搜索引擎 / Parallel engine (schedule + dedupe + score)

交叉验证逻辑：
Cross-Validation Logic:
  多个源返回同一 URL → 提升可信度 / Multiple sources same URL → higher credibility
  结果去重基于 URL 规范化 / Dedup via URL normalization (strip query params + fragment)

报告保存到 workspace/search_reports/YYYY-MM-DD_query_hash.json
Report saved to workspace/search_reports/YYYY-MM-DD_query_hash.json
"""

import asyncio
import hashlib
import json
import logging
import os
import re
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

import httpx

# H-11: 使用共享 SSRF 防护 / Use shared SSRF protection
from ._security_utils import is_safe_url

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────
# 数据模型 / Data Models
# ────────────────────────────────────────────────────────

class SourceType(str, Enum):
    BRAVE = "brave"
    TAVILY = "tavily"
    GOOGLE = "google"
    DUCKDUCKGO = "duckduckgo"
    BING = "bing"
    PERPLEXITY = "perplexity"
    SERPAPI = "serpapi"
    GROK = "grok"
    FIRECRAWL = "firecrawl"
    GEMINI = "gemini"


@dataclass
class SearchResult:
    """单条搜索结果 / Single Search Result"""
    title: str
    url: str
    snippet: str
    source: SourceType          # 来自哪个搜索引擎 / Which search engine
    raw_content: str = ""       # 抓取的全文（可选）/ Full content fetched (optional)
    relevance_score: float = 0.0  # 相关度评分 0-1 / Relevance score 0-1
    credibility_score: float = 0.0  # 可信度评分 0-1 / Credibility score 0-1
    cross_validated: bool = False  # 是否被其他来源交叉验证 / Cross-validated by other sources
    validation_count: int = 0   # 被验证次数 / Validation count
    fetched_at: str = ""

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "source": self.source.value,
            "relevance_score": round(self.relevance_score, 3),
            "credibility_score": round(self.credibility_score, 3),
            "cross_validated": self.cross_validated,
            "validation_count": self.validation_count,
            "fetched_at": self.fetched_at,
        }


@dataclass
class SearchReport:
    """完整的搜索报告 / Complete Search Report"""
    query: str
    timestamp: str
    results: list[SearchResult] = field(default_factory=list)
    sources_used: list[str] = field(default_factory=list)
    sources_failed: list[str] = field(default_factory=list)
    cross_validated_results: list[SearchResult] = field(default_factory=list)
    summary: str = ""
    total_time_ms: int = 0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "timestamp": self.timestamp,
            "total_results": len(self.results),
            "cross_validated_count": len(self.cross_validated_results),
            "sources_used": self.sources_used,
            "sources_failed": self.sources_failed,
            "total_time_ms": self.total_time_ms,
            "results": [r.to_dict() for r in self.results[:20]],
            "cross_validated": [r.to_dict() for r in self.cross_validated_results],
            "summary": self.summary,
        }

    def to_text(self) -> str:
        """人类可读的搜索报告 / Human-readable search report"""
        lines = [
            f"🔍 搜索报告: {self.query}",
            f"⏱ 耗时: {self.total_time_ms}ms | 来源: {len(self.sources_used)}个 | 结果: {len(self.results)}条",
            f"✅ 交叉验证: {len(self.cross_validated_results)}条",
            "",
        ]

        if self.cross_validated_results:
            lines.append("═══ 🎯 交叉验证结果（高可信度）═══")
            for i, r in enumerate(self.cross_validated_results[:10], 1):
                lines.append(
                    f"  {i}. [{r.source.value}] {r.title}\n"
                    f"     {r.url}\n"
                    f"     {r.snippet[:150]}\n"
                    f"     验证{r.validation_count}次 | 相关度{r.relevance_score:.0%} | 可信度{r.credibility_score:.0%}"
                )
            lines.append("")

        # 按来源分组 / Group by source
        by_source = {}
        for r in self.results:
            by_source.setdefault(r.source.value, []).append(r)

        for src, results in by_source.items():
            lines.append(f"─── {src} ({len(results)}条) ───")
            for r in results[:5]:
                lines.append(f"  • {r.title}\n    {r.url}")
            lines.append("")

        return "\n".join(lines)

    async def save(self, directory: str = ""):
        """H-17: 保存搜索报告到文件 / Save search report to file (async)"""
        if directory:
            save_dir = Path(directory)
        else:
            # 使用项目内 workspace/search_reports 目录 / Use project-local workspace/search_reports
            _project_root = Path(__file__).resolve().parent.parent.parent
            save_dir = _project_root / "workspace" / "search_reports"
        save_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        query_hash = hashlib.sha256(self.query.encode()).hexdigest()[:8]
        filename = f"search_{ts}_{query_hash}.json"
        filepath = save_dir / filename

        def _write():
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

        await asyncio.to_thread(_write)
        logger.info(f"Search report saved: {filepath}")
        return str(filepath)


# ────────────────────────────────────────────────────────
# 搜索源基类 / Search Provider Base Class
# ────────────────────────────────────────────────────────

class BaseSearchProvider(ABC):
    """搜索源抽象基类 / Search Provider Abstract Base Class"""

    source_type: SourceType
    priority: int = 5  # 1-10，越高越优先 / 1-10, higher = higher priority

    @abstractmethod
    async def search(self, query: str, count: int = 5) -> list[SearchResult]:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """检查 API key 是否配置 / Check if API key is configured"""
        ...


# ────────────────────────────────────────────────────────
# 搜索源实现 / Search Provider Implementations
# ────────────────────────────────────────────────────────

class BraveSearchProvider(BaseSearchProvider):
    source_type = SourceType.BRAVE
    priority = 9

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("BRAVE_SEARCH_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str, count: int = 5) -> list[SearchResult]:
        if not self.api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={"X-Subscription-Token": self.api_key, "Accept": "application/json"},
                    params={"q": query, "count": count},
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for item in data.get("web", {}).get("results", []):
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("description", ""),
                    source=self.source_type,
                    fetched_at=datetime.now().isoformat(),
                ))
            return results
        except Exception as e:
            logger.warning(f"Brave search failed: {e}")
            return []


class TavilySearchProvider(BaseSearchProvider):
    source_type = SourceType.TAVILY
    priority = 9

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("TAVILY_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str, count: int = 5) -> list[SearchResult]:
        if not self.api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    "https://api.tavily.com/search",
                    json={"api_key": self.api_key, "query": query, "max_results": count, "include_answer": True},
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for item in data.get("results", []):
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    snippet=item.get("content", ""),
                    source=self.source_type,
                    raw_content=item.get("content", ""),
                    fetched_at=datetime.now().isoformat(),
                ))
            return results
        except Exception as e:
            logger.warning(f"Tavily search failed: {e}")
            return []


class GoogleSearchProvider(BaseSearchProvider):
    source_type = SourceType.GOOGLE
    priority = 8

    def __init__(self, api_key: str = "", cx: str = ""):
        self.api_key = api_key or os.environ.get("GOOGLE_SEARCH_API_KEY", "")
        self.cx = cx or os.environ.get("GOOGLE_SEARCH_CX", "")

    def is_available(self) -> bool:
        return bool(self.api_key and self.cx)

    async def search(self, query: str, count: int = 5) -> list[SearchResult]:
        if not self.is_available():
            return []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://www.googleapis.com/customsearch/v1",
                    params={"key": self.api_key, "cx": self.cx, "q": query, "num": count},
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for item in data.get("items", []):
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    source=self.source_type,
                    fetched_at=datetime.now().isoformat(),
                ))
            return results
        except Exception as e:
            logger.warning(f"Google search failed: {e}")
            return []


class DuckDuckGoProvider(BaseSearchProvider):
    """DuckDuckGo — 免费无需 API key / Free, no API key needed"""
    source_type = SourceType.DUCKDUCKGO
    priority = 3

    def is_available(self) -> bool:
        return True  # 无需 key / No key needed

    async def search(self, query: str, count: int = 5) -> list[SearchResult]:
        try:
            async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                resp = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query},
                    headers={"User-Agent": "Mozilla/5.0 (compatible; MyAgent/1.0)"},
                )
                resp.raise_for_status()
                html = resp.text

            # 解析 HTML 结果 / Parse HTML results
            results = []
            # 简单正则提取 / Simple regex extraction
            titles = re.findall(r'<a[^>]*class="result__a"[^>]*>(.*?)</a>', html, re.DOTALL)
            urls = re.findall(r'uddg=([^&"]+)', html)
            snippets = re.findall(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', html, re.DOTALL)

            for i in range(min(len(titles), count)):
                url = urls[i] if i < len(urls) else ""
                title = re.sub(r'<[^>]+>', '', titles[i]).strip()
                snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ""
                if title:
                    results.append(SearchResult(
                        title=title,
                        url=url,
                        snippet=snippet,
                        source=self.source_type,
                        fetched_at=datetime.now().isoformat(),
                    ))
            return results[:count]
        except Exception as e:
            logger.warning(f"DuckDuckGo search failed: {e}")
            return []


class PerplexityProvider(BaseSearchProvider):
    source_type = SourceType.PERPLEXITY
    priority = 8

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("PERPLEXITY_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str, count: int = 5) -> list[SearchResult]:
        if not self.api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.perplexity.ai/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": "sonar",
                        "messages": [{"role": "user", "content": query}],
                        "return_citations": True,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            citations = data.get("citations", [])

            results = []
            for i, cite in enumerate(citations[:count]):
                results.append(SearchResult(
                    title=f"Perplexity Citation #{i+1}",
                    url=cite,
                    snippet=content[:300],
                    source=self.source_type,
                    raw_content=content,
                    fetched_at=datetime.now().isoformat(),
                ))

            if not results and content:
                results.append(SearchResult(
                    title="Perplexity AI Answer",
                    url="",
                    snippet=content[:500],
                    source=self.source_type,
                    raw_content=content,
                    fetched_at=datetime.now().isoformat(),
                ))

            return results
        except Exception as e:
            logger.warning(f"Perplexity search failed: {e}")
            return []


class GrokSearchProvider(BaseSearchProvider):
    """xAI Grok — 实时搜索（已禁用: API 返回 410）/ Live Search (DISABLED: returns 410)"""
    source_type = SourceType.GROK
    priority = 7

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("XAI_API_KEY", "")

    def is_available(self) -> bool:
        return False  # F-03: Grok API 返回 410 Gone / Grok API returns 410 Gone

    async def search(self, query: str, count: int = 5) -> list[SearchResult]:
        if not self.api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://api.x.ai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    json={
                        "model": "grok-3",
                        "messages": [{"role": "user", "content": query}],
                        "search_parameters": {"mode": "auto"},
                    },
                )
                resp.raise_for_status()
                data = resp.json()

            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            # Grok 的搜索结果在消息中 / Grok search results in message
            results = [SearchResult(
                title="Grok Live Search",
                url="",
                snippet=content[:500],
                source=self.source_type,
                raw_content=content,
                fetched_at=datetime.now().isoformat(),
            )]
            return results
        except Exception as e:
            logger.warning(f"Grok search failed: {e}")
            return []


class GeminiSearchProvider(BaseSearchProvider):
    """Google Gemini — 搜索增强生成 / Search-augmented generation"""
    source_type = SourceType.GEMINI
    priority = 7

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        # H-03: 缓存客户端 / Cache client, avoid creating connection per request
        self._client = None

    def _get_client(self):
        if self._client is None and self.api_key:
            import openai
            self._client = openai.AsyncOpenAI(
                api_key=self.api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            )
        return self._client

    def is_available(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str, count: int = 5) -> list[SearchResult]:
        if not self.api_key:
            return []
        try:
            client = self._get_client()
            response = await client.chat.completions.create(
                model="gemini-2.5-flash",
                messages=[{"role": "user", "content": f"Search the web and answer: {query}"}],
                tools=[{"type": "function", "function": {"name": "googleSearchRetrieval", "description": "Search", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}}}}],
            )
            content = response.choices[0].message.content or ""
            return [SearchResult(
                title="Gemini Search",
                url="",
                snippet=content[:500],
                source=self.source_type,
                raw_content=content,
                fetched_at=datetime.now().isoformat(),
            )]
        except Exception as e:
            logger.warning(f"Gemini search failed: {e}")
            return []


class BingSearchProvider(BaseSearchProvider):
    """Bing Web Search API / Bing 网络搜索 API"""
    source_type = SourceType.BING
    priority = 7

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("BING_SEARCH_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str, count: int = 5) -> list[SearchResult]:
        if not self.api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://api.bing.microsoft.com/v7.0/search",
                    headers={"Ocp-Apim-Subscription-Key": self.api_key},
                    params={"q": query, "count": count},
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for item in data.get("webPages", {}).get("value", []):
                results.append(SearchResult(
                    title=item.get("name", ""),
                    url=item.get("url", ""),
                    snippet=item.get("snippet", ""),
                    source=self.source_type,
                    fetched_at=datetime.now().isoformat(),
                ))
            return results
        except Exception as e:
            logger.warning(f"Bing search failed: {e}")
            return []


class FirecrawlSearchProvider(BaseSearchProvider):
    """Firecrawl — 搜索+抓取 / Search + Crawl"""
    source_type = SourceType.FIRECRAWL
    priority = 6

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("FIRECRAWL_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str, count: int = 5) -> list[SearchResult]:
        if not self.api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.post(
                    "https://api.firecrawl.dev/v1/search",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={"query": query, "limit": count},
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for item in data.get("data", data.get("results", [])):
                results.append(SearchResult(
                    title=item.get("metadata", {}).get("title", item.get("title", "")),
                    url=item.get("url", item.get("metadata", {}).get("sourceURL", "")),
                    snippet=item.get("markdown", item.get("content", ""))[:300],
                    source=self.source_type,
                    raw_content=item.get("markdown", item.get("content", "")),
                    fetched_at=datetime.now().isoformat(),
                ))
            return results
        except Exception as e:
            logger.warning(f"Firecrawl search failed: {e}")
            return []


class SerpAPIProvider(BaseSearchProvider):
    """SerpAPI — Google 搜索代理 / Google search proxy"""
    source_type = SourceType.SERPAPI
    priority = 7

    def __init__(self, api_key: str = ""):
        self.api_key = api_key or os.environ.get("SERPAPI_KEY") or os.environ.get("SERPAPI_API_KEY", "")

    def is_available(self) -> bool:
        return bool(self.api_key)

    async def search(self, query: str, count: int = 5) -> list[SearchResult]:
        if not self.api_key:
            return []
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    "https://serpapi.com/search",
                    params={"q": query, "api_key": self.api_key, "engine": "google", "num": count},
                )
                resp.raise_for_status()
                data = resp.json()

            results = []
            for item in data.get("organic_results", []):
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    source=self.source_type,
                    fetched_at=datetime.now().isoformat(),
                ))
            return results
        except Exception as e:
            logger.warning(f"SerpAPI search failed: {e}")
            return []


# ────────────────────────────────────────────────────────
# 交叉验证 / Cross-validation引擎 / Cross-Validation Engine
# ────────────────────────────────────────────────────────

class CrossValidator:
    """搜索结果交叉验证器 / Search Result Cross-Validator"""

    # 可信度评分权重：基于域名 / Credibility score weights: by domain
    DOMAIN_CREDIBILITY = {
        "reuters.com": 0.95, "apnews.com": 0.95, "bbc.com": 0.93, "bbc.co.uk": 0.93,
        "nytimes.com": 0.92, "washingtonpost.com": 0.91, "theguardian.com": 0.90,
        "bloomberg.com": 0.92, "ft.com": 0.91, "wsj.com": 0.91,
        "nature.com": 0.95, "science.org": 0.94, "arxiv.org": 0.88,
        "gov": 0.90, "edu": 0.88, "org": 0.75,
        "wikipedia.org": 0.82, "github.com": 0.80,
    }

    @staticmethod
    def normalize_url(url: str) -> str:
        """URL 归一化 / URL normalization — for matching"""
        url = url.lower().strip()
        url = re.sub(r'^https?://(www\.)?', '', url)
        url = re.sub(r'[?#].*$', '', url)
        url = url.rstrip('/')
        return url

    @staticmethod
    def normalize_title(title: str) -> str:
        """标题归一化 / Title normalization"""
        title = title.lower().strip()
        title = re.sub(r'[^\w\s]', '', title)
        title = re.sub(r'\s+', ' ', title)
        return title

    def validate(self, results: list[SearchResult]) -> list[SearchResult]:
        """执行交叉验证 / Perform cross-validation"""
        if not results:
            return []

        # 1. URL 匹配 / 1. URL match
        url_groups: dict[str, list[SearchResult]] = {}
        for r in results:
            if r.url:
                norm_url = self.normalize_url(r.url)
                url_groups.setdefault(norm_url, []).append(r)

        # 2. 标题匹配（模糊）/ 2. Title match (fuzzy)
        title_groups: dict[str, list[SearchResult]] = {}
        for r in results:
            if r.title:
                norm_title = self.normalize_title(r.title)
                # 取前30字符作为模糊键 / First 30 chars as fuzzy key
                key = norm_title[:30]
                title_groups.setdefault(key, []).append(r)

        # 3. 标记交叉验证 / 3. Mark cross-validation
        validated_urls = set()
        for norm_url, group in url_groups.items():
            if len(group) >= 2:
                validated_urls.add(norm_url)
                sources = set(r.source for r in group)
                for r in group:
                    r.cross_validated = True
                    r.validation_count = len(sources)

        # 标题匹配补充 / Title matching supplement
        for key, group in title_groups.items():
            if len(group) >= 2:
                sources = set(r.source for r in group)
                for r in group:
                    if not r.cross_validated:
                        r.cross_validated = True
                        r.validation_count = max(r.validation_count, len(sources))

        # 4. 计算可信度评分 / 4. Calculate credibility
        for r in results:
            r.credibility_score = self._calc_credibility(r)

        # 5. 计算相关度评分 / 5. Calculate relevance (title/snippet vs query)
        # 留给 LLM 后处理 / Left for LLM post-processing

        return results

    def _calc_credibility(self, result: SearchResult) -> float:
        """计算单条结果的可信度 / Calculate credibility for single result"""
        base = 0.5
        # 域名加分 / Domain bonus
        for domain, score in self.DOMAIN_CREDIBILITY.items():
            if domain in result.url.lower():
                base = max(base, score)
                break

        # 交叉验证 / Cross-validation加分
        if result.cross_validated:
            base = min(1.0, base + 0.1 * result.validation_count)

        return round(base, 3)

    def rank_results(self, results: list[SearchResult]) -> list[SearchResult]:
        """综合排序 / Comprehensive ranking"""
        for r in results:
            r.relevance_score = (
                r.credibility_score * 0.4 +
                (0.3 if r.cross_validated else 0.0) +
                min(r.validation_count * 0.1, 0.3)
            )
        results.sort(key=lambda x: (x.cross_validated, x.relevance_score), reverse=True)
        return results


# ────────────────────────────────────────────────────────
# 并行搜索引擎 / Parallel Search Engine
# ────────────────────────────────────────────────────────

class ParallelSearchEngine:
    """
    并行多源搜索引擎
    - 同时查询 3-10 个搜索源 / Query 3-10 sources simultaneously
    - 对结果进行交叉比对 / Cross-validate results
    - 保存完整来源信息 / Save complete source info
    """

    def __init__(self, max_sources: int = 10, timeout: float = 25.0):
        self.max_sources = max_sources
        self.timeout = timeout
        self.validator = CrossValidator()
        self._providers: list[BaseSearchProvider] = []
        self._register_providers()

    def _register_providers(self):
        """注册所有可用的搜索源 / Register all available search providers"""
        all_providers = [
            BraveSearchProvider(),
            TavilySearchProvider(),
            GoogleSearchProvider(),
            PerplexityProvider(),
            GrokSearchProvider(),
            GeminiSearchProvider(),
            BingSearchProvider(),
            SerpAPIProvider(),
            FirecrawlSearchProvider(),
            DuckDuckGoProvider(),  # 免费，优先级最低 / Free, lowest priority
        ]

        # 按优先级排序 / Sort by priority, take top max_sources available
        available = [p for p in all_providers if p.is_available()]
        available.sort(key=lambda p: p.priority, reverse=True)
        self._providers = available[:self.max_sources]

        logger.info(f"Search engine: {len(self._providers)} providers available: "
                     f"{[p.source_type.value for p in self._providers]}")

    @property
    def available_sources(self) -> list[str]:
        return [p.source_type.value for p in self._providers]

    async def search(
        self,
        query: str,
        count_per_source: int = 5,
        max_sources: int = 0,
        fetch_content: bool = False,
    ) -> SearchReport:
        """
        执行并行搜索

        Args:
            query: 搜索查询
            count_per_source: 每个来源返回的结果数
            max_sources: 最大使用来源数（0=全部可用）
            fetch_content: 是否抓取全文
        """
        start_time = time.time()
        providers = self._providers[:max_sources] if max_sources else self._providers

        if not providers:
            return SearchReport(
                query=query,
                timestamp=datetime.now().isoformat(),
                sources_failed=["No search providers available"],
            )

        # 并行执行所有搜索 / Execute all searches in parallel
        tasks = [p.search(query, count_per_source) for p in providers]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

        # 收集结果 / Collect results
        all_results: list[SearchResult] = []
        sources_used: list[str] = []
        sources_failed: list[str] = []

        for provider, result in zip(providers, raw_results):
            if isinstance(result, Exception):
                sources_failed.append(f"{provider.source_type.value}: {result}")
                logger.warning(f"{provider.source_type.value} error: {result}")
            elif result:
                all_results.extend(result)
                sources_used.append(provider.source_type.value)
            else:
                sources_failed.append(provider.source_type.value)

        # 交叉验证 / Cross-validation
        validated = self.validator.validate(all_results)

        # 排序 / Ranking
        ranked = self.validator.rank_results(validated)

        # 提取交叉验证结果 / Extract cross-validated results
        cross_validated = [r for r in ranked if r.cross_validated]

        # 可选：抓取全文 / Optional: fetch full content
        if fetch_content and ranked:
            await self._fetch_content(ranked[:5])

        elapsed = int((time.time() - start_time) * 1000)

        report = SearchReport(
            query=query,
            timestamp=datetime.now().isoformat(),
            results=ranked,
            sources_used=sources_used,
            sources_failed=sources_failed,
            cross_validated_results=cross_validated,
            total_time_ms=elapsed,
            metadata={
                "providers_count": len(providers),
                "results_per_source": count_per_source,
            },
        )

        return report

    async def _fetch_content(self, results: list[SearchResult]):
        """抓取前N条结果的全文 / Fetch full content for top N results (with SSRF protection)"""
        async def fetch_one(result: SearchResult):
            if not result.url or result.raw_content:
                return
            # H-11: 使用共享 SSRF 防护 / Use shared SSRF protection
            safe, reason = is_safe_url(result.url)
            if not safe:
                return
            try:
                async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
                    resp = await client.get(result.url, headers={
                        "User-Agent": "Mozilla/5.0 (compatible; MyAgent/1.0)"
                    })
                    resp.raise_for_status()
                    content = resp.text
                    content = re.sub(r'<script[^>]*>.*?</script>', '', content, flags=re.DOTALL)
                    content = re.sub(r'<style[^>]*>.*?</style>', '', content, flags=re.DOTALL)
                    content = re.sub(r'<[^>]+>', ' ', content)
                    content = re.sub(r'\s+', ' ', content).strip()
                    result.raw_content = content[:10000]
            except Exception:
                pass

        await asyncio.gather(*[fetch_one(r) for r in results])
