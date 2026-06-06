"""智谱 GLM Provider / Zhipu GLM Provider"""

import logging
from .openai_compat import OpenAICompatProvider

logger = logging.getLogger(__name__)


class ZhipuProvider(OpenAICompatProvider):
    """智谱 AI — GLM-4.6V / GLM-5.1 / GLM-5-Turbo"""

    # 智谱模型别名映射 / Zhipu model alias mapping
    MODEL_MAP = {
        "glm-5.1": "glm-5.1",
        "glm-5": "glm-5",
        "glm-5-turbo": "glm-5-turbo",
        "glm-5v-turbo": "glm-5v-turbo",
        "glm-4.7": "glm-4.7",
        "glm-4.6v": "glm-4.6v",
    }

    def __init__(self, api_key: str, base_url: str = "", model: str = "glm-5.1"):
        # 智谱兼容 OpenAI 格式 / Zhipu is OpenAI-compatible
        base = base_url or "https://open.bigmodel.cn/api/paas/v4"
        super().__init__(api_key=api_key, base_url=base, model=model)

    async def chat(self, messages, tools=None, model: str = "", **kwargs):
        """H-06: 使用 _resolve_model 解析模型别名 / Use _resolve_model for alias resolution"""
        resolved = self._resolve_model(model or self.default_model)
        return await super().chat(messages=messages, tools=tools, model=resolved, **kwargs)

    def _resolve_model(self, model: str) -> str:
        """解析模型别名 / Resolve model alias"""
        clean = model.split("/")[-1] if "/" in model else model
        return self.MODEL_MAP.get(clean, clean)
