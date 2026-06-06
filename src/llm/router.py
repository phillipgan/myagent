"""LLM 模型路由 / LLM Model Router

修复:
Fixes:
- H-20: 统一 fallback 模型名 / Unify fallback model name with config
"""

import logging
from .providers.base import LLMProvider, LLMResponse
from .providers.openai_compat import OpenAICompatProvider

logger = logging.getLogger(__name__)


class LLMRouter:
    """多模型路由器 / Multi-Model Router"""

    def __init__(self, config):
        self.providers: dict[str, LLMProvider] = {}
        self.default_model = config.model.default
        self.routes = config.model.routes

        # 初始化提供商 / Initialize providers
        for name, prov_config in config.providers.items():
            if prov_config.base_url or prov_config.api_key:
                try:
                    self.providers[name] = OpenAICompatProvider(
                        base_url=prov_config.base_url,
                        api_key=prov_config.api_key or "dummy",
                        model=prov_config.model or "",
                    )
                except Exception as e:
                    logger.warning(f"Failed to init provider '{name}': {e}")

        # Ollama 始终可用（本地）/ Ollama always available (local)
        if "ollama" not in self.providers:
            try:
                self.providers["ollama"] = OpenAICompatProvider(
                    base_url="http://localhost:11434/v1",
                    api_key="ollama",
                )
            except Exception as e:
                logger.warning(f"Failed to init Ollama provider: {e}")

        logger.info(f"LLM Router initialized: {list(self.providers.keys())} providers, default={self.default_model}")

    def _parse_model_ref(self, model_ref: str) -> tuple[str, str]:
        """解析 provider/model 格式 / Parse provider/model format"""
        if "/" in model_ref:
            parts = model_ref.split("/", 1)
            provider = parts[0].strip()
            model = parts[1].strip()
            return provider, model
        return "", model_ref

    def get_provider(self, model_ref: str) -> tuple[LLMProvider | None, str]:
        """获取模型对应的提供商 / Get provider for a model"""
        provider_name, model_name = self._parse_model_ref(model_ref)

        if provider_name and provider_name in self.providers:
            prov = self.providers[provider_name]
            if not model_name and hasattr(prov, 'default_model') and prov.default_model:
                model_name = prov.default_model
            return prov, model_name

        # 没有 provider 或找不到时尝试 Ollama / Fallback to Ollama if no provider or not found
        return self.providers.get("ollama"), model_ref

    async def chat(
        self,
        messages: list[dict],
        tools: list[dict] | None = None,
        model: str | None = None,
        task_type: str | None = None,
        **kwargs,
    ) -> LLMResponse:
        """发送聊天请求 / Send chat request, auto-route to appropriate model"""

        # 确定使用的模型 / Determine model to use
        if model:
            model_ref = model
        elif task_type and task_type in self.routes:
            model_ref = self.routes[task_type]
        else:
            model_ref = self.default_model

        provider, model_name = self.get_provider(model_ref)

        if not provider:
            logger.error(f"No provider for model: {model_ref}")
            # H-20: fallback 使用 ollama 默认模型 / Fallback uses Ollama default model
            provider = self.providers.get("ollama")
            if provider and hasattr(provider, 'default_model') and provider.default_model:
                model_name = provider.default_model
            else:
                model_name = "qwen3.5:4b"
            if not provider:
                raise RuntimeError(f"No provider available for model: {model_ref}")

        logger.debug(f"Using model: {model_ref} -> provider={type(provider).__name__}")

        return await provider.chat(
            messages=messages,
            tools=tools,
            model=model_name,
            **kwargs,
        )

    async def close_all(self):
        """关闭所有 Provider 连接池 / Close all Provider connection pools"""
        for name, provider in self.providers.items():
            try:
                await provider.close()
            except Exception as e:
                logger.warning(f"Error closing provider '{name}': {e}")
        logger.info("All LLM provider connections closed")
