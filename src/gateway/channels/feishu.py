"""飞书通道 — 基于飞书官方 SDK (lark-oapi) / Feishu Channel — Based on Feishu Official SDK

架构：
Architecture:子进程 WebSocket 长连接 + 主进程 Webhook 回调
Architecture: Subprocess WebSocket + Main process Webhook callback

- WebSocket 模式：子进程运行 lark-oapi Channel / WebSocket: subprocess runs lark-oapi Channel, HTTP callback to main
  → 无需公网 IP，无需 Cloudflare Tunnel
  → No public IP needed, no Cloudflare Tunnel required
- Webhook 模式：兼容传统回调 / Webhook: legacy callback (needs public IP or tunnel)
- REST API：发送消息、卡片、媒体 / REST API: send messages, cards, media

依赖：lark-oapi >= 1.6, httpx / Dependencies: lark-oapi >= 1.6, httpx
"""

import asyncio
import json
import logging
import multiprocessing
import os
import time
from typing import Optional, Callable

import httpx

import httpx

logger = logging.getLogger(__name__)


def _feishu_ws_worker(app_id, encrypt_key, verification_token, callback_url):
    """子进程：运行飞书 WebSocket 长连接 / Subprocess: Feishu WebSocket long connection

    C-04: app_secret 通过环境变量传入 / app_secret via env var, avoid /proc/<pid>/cmdline leak
    """
    # C-04: 从环境变量读取 app_secret / Read app_secret from env var
    app_secret = os.environ.get("MYAGENT_FEISHU_APP_SECRET", "")
    import asyncio
    import logging as lg
    lg.basicConfig(level=lg.INFO, format="%(asctime)s [feishu-ws] %(levelname)s: %(message)s")
    log = lg.getLogger("feishu-ws")

    try:
        from lark_oapi.channel import FeishuChannel as LarkChannel
        from lark_oapi import LogLevel
    except ImportError:
        log.error("lark-oapi not installed")
        return

    ch = LarkChannel(
        app_id=app_id,
        app_secret=app_secret,
        encrypt_key=encrypt_key,
        verification_token=verification_token,
        log_level=LogLevel.INFO,
    )

    def on_message(msg):
        """收到消息 → HTTP POST 到主进程 / Receive message → HTTP POST to main"""
        try:
            import urllib.request
            import os
            import hmac
            import hashlib
            data_dict = {
                "text": msg.content_text or "",
                "sender_id": getattr(msg, "sender_id", ""),
                "chat_id": getattr(msg, "chat_id", ""),
                "message_id": getattr(msg, "message_id", ""),
                "chat_type": getattr(msg, "chat_type", ""),
                "sender_name": getattr(msg, "sender_name", ""),
            }
            data = json.dumps(data_dict).encode()
            headers = {"Content-Type": "application/json"}
            secret = os.environ.get("MYAGENT_INTERNAL_SECRET", "")
            if secret:
                sig = hmac.new(secret.encode(), data, hashlib.sha256).hexdigest()
                headers["X-Internal-Signature"] = sig
            req = urllib.request.Request(
                callback_url, data=data, headers=headers, method="POST",
            )
            # F-04: 主进程立即返回 202 / Main returns 202 immediately, no long timeout needed
            with urllib.request.urlopen(req, timeout=10) as resp:
                resp.read()
        except Exception as e:
            log.error(f"Callback to main process failed: {e}")

    ch.on("message", on_message)
    log.info("Feishu WebSocket connecting...")

    try:
        asyncio.run(ch.connect())
    except KeyboardInterrupt:
        log.info("Feishu WebSocket interrupted")
    except Exception as e:
        log.error(f"Feishu WebSocket error: {e}")


class FeishuChannel:
    """飞书 Bot 通道 / Feishu Bot Channel — lark-oapi Channel + REST API"""

    def __init__(self, config: dict):
        self.app_id = config.get("app_id", "")
        self.app_secret = config.get("app_secret", "")
        self.verification_token = config.get("verification_token", "")
        self.encrypt_key = config.get("encrypt_key", "")
        self._handler: Optional[Callable] = None
        self._ws_process = None
        self._callback_url = config.get("callback_url", "http://localhost:5196/internal/feishu_message")
        # H-03: token 改为实例变量 / Token as instance var, avoid multi-instance sharing
        self._tenant_token: str = ""
        self._token_expires: float = 0.0
        # H-07: token 刷新锁 / Token refresh lock, prevent concurrent race
        self._token_lock: asyncio.Lock | None = None
        # H-13: 复用 httpx 客户端 / Reuse httpx client
        self._http_client: httpx.AsyncClient | None = None

    def set_handler(self, handler: Callable):
        """设置消息处理函数 / Set message handler: handler(text, sender_id, chat_id) -> str"""
        self._handler = handler

    async def start(self):
        """启动飞书通道（WebSocket 子进程）/ Start Feishu channel (WebSocket subprocess)

        C-04: app_secret 通过环境变量传递 / app_secret passed via env var, avoid /proc leak
        """
        logger.info(f"Starting Feishu WebSocket subprocess (callback: {self._callback_url})")

        # C-04: app_secret 放入环境变量 / Pass app_secret via env var, subprocess reads via os.environ
        os.environ["MYAGENT_FEISHU_APP_SECRET"] = self.app_secret

        self._ws_process = multiprocessing.Process(
            target=_feishu_ws_worker,
            args=(self.app_id, self.encrypt_key,
                  self.verification_token, self._callback_url),
            daemon=True,
        )
        self._ws_process.start()
        logger.info(f"Feishu WebSocket process started (PID: {self._ws_process.pid})")

    async def stop(self):
        """停止飞书通道 / Stop Feishu channel"""
        if self._ws_process and self._ws_process.is_alive():
            self._ws_process.terminate()
            self._ws_process.join(timeout=5)
            logger.info("Feishu WebSocket process stopped")

    async def handle_internal_message(self, data: dict) -> str:
        """处理来自子进程的内部回调消息 / Handle internal callback message from subprocess"""
        text = data.get("text", "")
        sender_id = data.get("sender_id", "")
        chat_id = data.get("chat_id", "")

        if not text.strip():
            return ""

        logger.info(f"Feishu message from {sender_id}: {text[:80]}")

        if self._handler:
            try:
                reply = await self._handler(text, sender_id, chat_id)
                return reply or ""
            except Exception as e:
                logger.error(f"Message handler error: {e}")
                return "抱歉，处理消息时出错，请稍后重试。"
        return ""

    # ==================== Webhook 模式（兼容）/ Webhook mode (compat) ====================

    async def handle_webhook(self, body: dict, headers: dict = None) -> dict:
        """处理飞书 Webhook 回调 / Handle Feishu Webhook callback"""
        if body.get("type") == "url_verification":
            return {"challenge": body.get("challenge")}

        header = body.get("header", {})
        event_type = header.get("event_type", "")
        event = body.get("event", {})

        if event_type == "im.message.receive_v1":
            content_str = event.get("message", {}).get("content", "{}")
            chat_id = event.get("message", {}).get("chat_id", "")
            sender_id = event.get("sender", {}).get("sender_id", {}).get("user_id", "")

            try:
                content = json.loads(content_str)
                text = content.get("text", "")
            except json.JSONDecodeError:
                text = content_str

            if self._handler and text:
                try:
                    reply = await self._handler(text, sender_id, chat_id)
                    if reply and chat_id:
                        await self.send(chat_id, reply)
                except Exception as e:
                    logger.error(f"Webhook handler error: {e}")

        return {"code": 0}

    # ==================== 发送消息 / Send Messages ====================

    def _get_http_client(self) -> httpx.AsyncClient:
        """获取复用的 HTTP 客户端 / Get reusable HTTP client"""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=15)
        return self._http_client

    async def send(self, chat_id: str, text: str) -> bool:
        """发送文本消息 / Send text message"""
        token = await self._get_token()
        if not token:
            return False

        client = self._get_http_client()
        resp = await client.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            headers={"Authorization": f"Bearer {token}"},
            params={"receive_id_type": "chat_id"},
            json={
                "receive_id": chat_id,
                "msg_type": "text",
                "content": json.dumps({"text": text}),
            },
        )
        data = resp.json()

        if data.get("code") != 0:
            logger.error(f"Send failed: {data.get('msg', '')}")
            return False
        return True

    async def send_reply(self, message_id: str, text: str) -> bool:
        """回复消息 / Reply to message"""
        token = await self._get_token()
        if not token:
            return False

        client = self._get_http_client()
        resp = await client.post(
            f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/reply",
            headers={"Authorization": f"Bearer {token}"},
            json={"msg_type": "text", "content": json.dumps({"text": text})},
        )
        data = resp.json()

        return data.get("code") == 0

    async def send_markdown(self, chat_id: str, title: str, md_content: str) -> bool:
        """发送 Markdown 卡片消息 / Send Markdown card message"""
        token = await self._get_token()
        if not token:
            return False

        card = {"elements": [{"tag": "markdown", "content": md_content}]}
        if title:
            card["header"] = {"title": {"tag": "plain_text", "content": title}, "template": "blue"}

        client = self._get_http_client()
        resp = await client.post(
            "https://open.feishu.cn/open-apis/im/v1/messages",
            headers={"Authorization": f"Bearer {token}"},
            params={"receive_id_type": "chat_id"},
            json={
                "receive_id": chat_id,
                "msg_type": "interactive",
                "content": json.dumps(card),
            },
        )
        data = resp.json()

        if data.get("code") != 0:
            logger.error(f"Markdown send failed: {data.get('msg', '')}")
            return False
        return True

    # ==================== Token 管理（实例变量）/ Token Management (instance vars) ====================

    def _get_token_lock(self) -> asyncio.Lock:
        """H-07: 懒初始化 token 刷新锁 / Lazy-init token refresh lock"""
        if self._token_lock is None:
            self._token_lock = asyncio.Lock()
        return self._token_lock

    async def _get_token(self) -> str:
        """获取/刷新 tenant_access_token / Get/refresh tenant_access_token (H-07: locked against concurrent race)"""
        # 快速路径：token 未过期 / Fast path: token not expired
        if self._tenant_token and time.time() < self._token_expires:
            return self._tenant_token

        # 加锁：防止并发刷新 / Lock: prevent concurrent refresh
        lock = self._get_token_lock()
        async with lock:
            # Double-check：锁获取后再次检查 / Double-check after acquiring lock
            if self._tenant_token and time.time() < self._token_expires:
                return self._tenant_token

            client = self._get_http_client()
            resp = await client.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": self.app_id, "app_secret": self.app_secret},
            )
            data = resp.json()

            if data.get("code") != 0:
                logger.error(f"Token error: {data}")
                return ""

            self._tenant_token = data["tenant_access_token"]
            self._token_expires = time.time() + data.get("expire", 7200) - 300
            logger.info("Feishu tenant token refreshed")
            return self._tenant_token

    # 保持旧接口兼容 / Maintain backward compatibility
    async def get_tenant_token(self) -> str:
        return await self._get_token()
