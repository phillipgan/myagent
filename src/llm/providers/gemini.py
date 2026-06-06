"""Google Gemini Provider — 复用 AsyncOpenAI client / Reuse AsyncOpenAI client

修复:
Fixes:
- H-03: 添加异常处理和日志 / Add exception handling and logging
"""

import json
import logging
from openai import AsyncOpenAI
from .base import LLMProvider, LLMResponse, ToolCall

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """Google Gemini — 通过 OpenAI 兼容接口 / Via OpenAI-compatible API"""

    def __init__(self, api_key: str, model: str = "gemini-2.5-pro"):
        super().__init__(
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            api_key=api_key,
        )
        self.model = model
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=self.base_url,
        )

    async def chat(self, messages: list[dict], tools: list[dict] | None = None,
                   model: str = "", temperature: float = 0.7) -> LLMResponse:
        kwargs = {
            "model": model.split("/", 1)[-1] if model else self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = [{"type": "function", "function": t["function"]} for t in tools]

        try:
            response = await self._client.chat.completions.create(**kwargs)
        except Exception as e:
            # H-03: 添加日志记录 / Add logging
            logger.error(f"Gemini API error: {e}")
            raise

        # H-05: 检查空 choices / Check empty choices
        if not response.choices:
            return LLMResponse(content="", tool_calls=[], model=response.model)

        choice = response.choices[0]
        content = choice.message.content or ""
        tool_calls = []

        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}
                if isinstance(args, str):
                    args = {"raw": args}
                tool_calls.append(ToolCall(
                    id=tc.id, name=tc.function.name, arguments=args,
                ))

        return LLMResponse(content=content, tool_calls=tool_calls, model=response.model)

    async def close(self):
        """关闭 client 连接池 / Close client connection pool"""
        try:
            await self._client.close()
        except Exception:
            pass
