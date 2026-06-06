"""Ollama 本地模型 Provider / Ollama Local Model Provider — Reuse httpx.AsyncClient

通过 Ollama REST API 调用本地模型。
Call locally deployed models via Ollama REST API (localhost:11434).
支持流式响应和 function calling。
Supports streaming and function calling (via Ollama tools param).

优势：本地运行、无 API 费用、数据不出境。
Advantages: local, no API cost, data stays on-premise.
劣势：受限于 GPU 显存。
Disadvantage: limited by GPU VRAM (DGX Spark up to 35B models).

修复:
Fixes:
- H-03: 添加异常处理和日志 / Add exception handling and logging
- H-04: arguments 可能为字符串 / Handle string-type arguments
"""

import json
import logging
import httpx
from .base import LLMProvider, LLMResponse, ToolCall

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Ollama 本地模型 / Ollama Local Model"""

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen3.5:4b"):
        super().__init__(base_url=base_url.rstrip("/"), api_key="")
        self.model = model
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=120)

    async def chat(self, messages: list[dict], tools: list[dict] | None = None,
                   model: str = "", temperature: float = 0.7) -> LLMResponse:
        url = "/api/chat"
        payload = {
            "model": model.split("/", 1)[-1] if model else self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature},
        }

        if tools:
            payload["tools"] = tools

        try:
            resp = await self._client.post(url, json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            # H-03: 添加异常处理和日志 / Add exception handling and logging
            logger.error(f"Ollama API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Ollama unexpected error: {e}")
            raise

        data = resp.json()

        content = data.get("message", {}).get("content", "")
        tool_calls = []

        if data.get("message", {}).get("tool_calls"):
            for tc in data["message"]["tool_calls"]:
                raw_args = tc["function"].get("arguments", {})
                # H-04: arguments 是字符串时尝试解析 / If arguments is string, try parsing
                if isinstance(raw_args, str):
                    try:
                        raw_args = json.loads(raw_args)
                    except json.JSONDecodeError:
                        raw_args = {"raw": raw_args}
                tool_calls.append(ToolCall(
                    id=tc.get("id", f"tc_{len(tool_calls)}"),
                    name=tc["function"]["name"],
                    arguments=raw_args,
                ))

        return LLMResponse(content=content, tool_calls=tool_calls)

    async def models(self) -> list[str]:
        try:
            resp = await self._client.get("/api/tags")
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception as e:
            logger.warning(f"Failed to list Ollama models: {e}")
            return []

    async def embed(self, text: str, model: str = "") -> list[float]:
        payload = {"model": model or self.model, "input": text}
        try:
            resp = await self._client.post("/api/embed", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("embeddings", [[]])[0]
        except Exception as e:
            logger.warning(f"Ollama embed failed: {e}")
            return []

    async def close(self):
        """关闭 client 连接池 / Close client connection pool"""
        try:
            await self._client.aclose()
        except Exception:
            pass
