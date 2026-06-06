"""飞书 API 工具 / Feishu API Tool — 发消息/读消息/搜索/文档

封装飞书开放平台 API，支持：
Wraps Feishu Open Platform API, supporting:
  - send_message: 向指定 chat_id 发送消息 / Send message to chat_id (text/markdown)
  - read_message: 读取指定消息 ID 的内容 / Read message by ID
  - search: 搜索聊天记录 / Search chat history

认证：通过 App ID + App Secret 获取 token，
Auth: Get tenant_access_token via App ID + Secret,
有效期 2 小时，提前 5 分钟自动刷新。
Valid 2 hours, auto-refresh 5 min before expiry.
"""

import json
import os
import logging
import httpx
from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class FeishuAPITool(BaseTool):
    name = "feishu_api"
    description = "Interact with Feishu/Lark API: send messages, read messages, search docs, manage chats."

    def __init__(self, app_id: str = "", app_secret: str = ""):
        self.app_id = app_id or os.environ.get("FEISHU_APP_ID", "")
        self.app_secret = app_secret or os.environ.get("FEISHU_APP_SECRET", "")
        self._tenant_token: str = ""
        self._token_expires: float = 0.0  # H-04: 添加过期时间 / Add expiry time
        self._base = "https://open.feishu.cn/open-apis"

    async def _get_token(self) -> str:
        """获取飞书 tenant_access_token / Get Feishu tenant_access_token with cache and auto-refresh.

        Token 有效期 2 小时，提前 5 分钟刷新。
Token valid 2h, refresh 5min early to avoid expiry.
        如果 token 已缓存且未过期，直接返回缓存值。
If cached and not expired, return cached token.
        """
        # H-04: 检查 token 是否过期 / Check if token expired (Feishu token valid 2h)
        import time
        if self._tenant_token and time.time() < self._token_expires:
            return self._tenant_token
        # token 不存在或已过期，重新获取 / Token missing or expired, refresh
        self._tenant_token = ""
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{self._base}/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )
            data = resp.json()
            if data.get("code") == 0:
                self._tenant_token = data.get("tenant_access_token", "")
                self._token_expires = time.time() + data.get("expire", 7200) - 300  # 提前 5 分钟刷新 / Refresh 5 min early
                logger.info("FeishuAPITool token refreshed")
        return self._tenant_token

    async def execute(self, action: str = "send_message", **kwargs) -> ToolResult:
        try:
            token = await self._get_token()
            if not token:
                return ToolResult(error="Failed to get Feishu token", success=False)

            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

            if action == "send_message":
                return await self._send(headers, kwargs)
            elif action == "read_message":
                return await self._read(headers, kwargs)
            elif action == "search":
                return await self._search(headers, kwargs)
            else:
                return ToolResult(error=f"Unknown action: {action}", success=False)

        except Exception as e:
            return ToolResult(error=str(e), success=False)

    async def _send(self, headers, kwargs) -> ToolResult:
        """发送消息到指定聊天 / Send message to chat. Supports text and markdown."""
        receive_id = kwargs.get("chat_id", "")
        msg_type = kwargs.get("msg_type", "text")
        content = kwargs.get("content", "")

        if msg_type == "text":
            content = json.dumps({"text": content})

        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._base}/im/v1/messages",
                headers=headers,
                params={"receive_id_type": "chat_id"},
                json={"receive_id": receive_id, "msg_type": msg_type, "content": content},
            )
            data = resp.json()
            if data.get("code") == 0:
                return ToolResult(output=f"Message sent to {receive_id}")
            return ToolResult(error=f"Send failed: {data.get('msg')}", success=False)

    async def _read(self, headers, kwargs) -> ToolResult:
        """读取指定消息 ID 的完整内容 / Read full content by message ID."""
        message_id = kwargs.get("message_id", "")
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self._base}/im/v1/messages/{message_id}",
                headers=headers,
            )
            data = resp.json()
            if data.get("code") == 0:
                items = data.get("data", {}).get("items", [])
                return ToolResult(output=json.dumps(items, ensure_ascii=False, indent=2))
            return ToolResult(error=f"Read failed: {data.get('msg')}", success=False)

    async def _search(self, headers, kwargs) -> ToolResult:
        """搜索飞书聊天记录 / Search Feishu chat history, return matches (truncated to 2000 chars)"""
        query = kwargs.get("query", "")
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{self._base}/search/v1/chat",
                headers=headers,
                json={"query": query},
            )
            data = resp.json()
            return ToolResult(output=json.dumps(data, ensure_ascii=False, indent=2)[:2000])

    def get_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": "feishu_api",
                "description": "Feishu/Lark API: send_message, read_message, search. Requires app_id and app_secret.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "action": {"type": "string", "enum": ["send_message", "read_message", "search"]},
                        "chat_id": {"type": "string", "description": "Target chat ID"},
                        "content": {"type": "string", "description": "Message content"},
                        "msg_type": {"type": "string", "description": "Message type (text, markdown)"},
                        "message_id": {"type": "string", "description": "Message ID to read"},
                        "query": {"type": "string", "description": "Search query"},
                    },
                    "required": ["action"],
                },
            },
        }
