"""OpenAI 兼容接口 — 支持 Ollama / GLM / DeepSeek 等所有 OpenAI SDK 兼容提供商

修复:
Fixes:
- H-05: choices[0] IndexError 保护 / Protect choices[0] with IndexError handling
- H-16: arguments 可能是字符串 / Handle string-type arguments
"""

import json
import logging
from openai import AsyncOpenAI
from .base import LLMProvider, LLMResponse, ToolCall

logger = logging.getLogger(__name__)


class OpenAICompatProvider(LLMProvider):
    """OpenAI 兼容提供商 / OpenAI-Compatible Provider — Unified Interface"""

    def __init__(self, base_url: str, api_key: str = "dummy", model: str = ""):
        super().__init__(base_url, api_key)
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self.default_model = model

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str = "",
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> LLMResponse:
        """发送聊天请求 / Send chat request"""
        model = model or self.default_model

        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        try:
            response = await self.client.chat.completions.create(**kwargs)

            # H-05: 检查 choices 是否为空 / Check if choices is empty
            if not response.choices:
                return LLMResponse(
                    content="",
                    tool_calls=[],
                    model=response.model,
                    usage={},
                )

            choice = response.choices[0]

            tool_calls = []
            if choice.message.tool_calls:
                for tc in choice.message.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        # H-16: 保留原始字符串 / Keep original string
                        args = {"raw": tc.function.arguments}
                    # H-16: 如果 args 是字符串则包装 / If args is string (some providers), wrap it
                    if isinstance(args, str):
                        args = {"raw": args}
                    tool_calls.append(ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        arguments=args,
                    ))

            return LLMResponse(
                content=choice.message.content or "",
                tool_calls=tool_calls,
                model=response.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                } if response.usage else {},
            )

        except Exception as e:
            logger.error(f"LLM chat error ({model}): {e}")
            raise

    async def close(self):
        """关闭 AsyncOpenAI 连接池 / Close AsyncOpenAI client pool"""
        try:
            await self.client.close()
        except Exception:
            pass
