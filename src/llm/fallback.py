"""LLM Fallback 链 / LLM Fallback Chain — Auto-degrade to backup models

修复:
Fixes:
- H-01: asyncio.Lock 懒初始化 / Lazy init asyncio.Lock, avoid creating outside event loop
- H-06: 单一锁保护全流程 / Single lock protects check+call+update (simplify race)
- H-19: reset_failures 获取锁 / reset_failures acquires lock
- C-05: threading.Lock 保护 asyncio.Lock 初始化 / threading.Lock protects asyncio.Lock lazy init, prevents thread race
"""

import asyncio
import logging
import threading
from typing import Optional

from .providers.base import LLMResponse

logger = logging.getLogger(__name__)


class FallbackChain:
    """模型降级链 / Model Fallback Chain — auto-switch on primary failure"""

    def __init__(self, router, chain: list[str] | None = None):
        self.router = router
        self.chain = chain or [
            "zai/glm-5.1",
            "openrouter/auto",
            "ollama/qwen3.5:4b",
        ]
        self._failure_counts: dict[str, int] = {}
        self._max_failures = 3
        # C-05: 使用 threading.Lock 保护 asyncio.Lock 初始化 / threading.Lock protects asyncio.Lock init
        self._lock: asyncio.Lock | None = None
        self._init_lock = threading.Lock()

    def _get_lock(self) -> asyncio.Lock:
        """C-05: 线程安全的 asyncio.Lock 懒初始化 / Thread-safe asyncio.Lock lazy init"""
        if self._lock is None:
            with self._init_lock:
                if self._lock is None:
                    self._lock = asyncio.Lock()
        return self._lock

    async def chat(self, messages, tools=None, model: str = "") -> LLMResponse:
        """带降级的聊天请求 / Chat request with fallback"""
        models_to_try = [model] if model else []
        models_to_try += [m for m in self.chain if m not in models_to_try]

        last_error = None
        lock = self._get_lock()

        for m in models_to_try:
            # 检查失败次数 / Check failure count
            async with lock:
                failures = self._failure_counts.get(m, 0)
                if failures >= self._max_failures:
                    logger.warning(f"Skipping model {m} (too many failures)")
                    continue

            try:
                result = await self.router.chat(messages=messages, tools=tools, model=m)
                async with lock:
                    self._failure_counts[m] = 0
                return result
            except Exception as e:
                last_error = e
                async with lock:
                    self._failure_counts[m] = self._failure_counts.get(m, 0) + 1
                logger.warning(f"Model {m} failed ({self._failure_counts[m]}/{self._max_failures}): {e}")
                continue

        raise RuntimeError(f"All models failed. Last error: {last_error}")

    async def reset_failures(self, model: str = ""):
        """H-19: 重置失败计数 / Reset failure count (thread-safe)"""
        lock = self._get_lock()
        async with lock:
            if model:
                self._failure_counts[model] = 0
            else:
                self._failure_counts.clear()
