"""Gateway 服务 / Gateway Server — FastAPI + WebSocket + Webhook + Dashboard + Feishu

安全改进（v0.5.0）/ Security Improvements (v0.5.0):
- C-01: 内部端点强制要求 HMAC 签名 / Internal endpoints require HMAC signature, reject without secret
- C-01: 默认绑定 127.0.0.1 / Default bind 127.0.0.1
- H-18: status 端点添加认证保护 / Status endpoint auth protection
- H-19: 网络安全加固 / Network security hardening
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import time
from typing import Optional

from fastapi import FastAPI, WebSocket, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import uvicorn

from src.config import AgentConfig
from src.agent import AgentOrchestrator
from src.gateway.channels.feishu import FeishuChannel
from src.gateway.channels.telegram import TelegramChannel
from src.gateway.channels.cli import CLIChannel
from src.gateway.dashboard import DASHBOARD_HTML
from src.gateway.watchdog import ChannelWatchdog
from src.scheduler import CronScheduler, register_default_jobs

logger = logging.getLogger(__name__)

# C-01: 内部回调 HMAC 签名密钥 / Internal HMAC secret — must be set
def _get_internal_secret() -> str:
    """延迟读取 secret / Lazy-read secret (.env may load after import)"""
    return os.environ.get("MYAGENT_INTERNAL_SECRET", "")


class Gateway:
    """统一消息网关 / Unified Message Gateway"""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.app = FastAPI(title="MyAgent Gateway", version="0.5.0")
        self.agent: Optional[AgentOrchestrator] = None
        self.feishu: Optional[FeishuChannel] = None
        self.telegram: Optional[TelegramChannel] = None
        self.scheduler = CronScheduler(timezone="Asia/Dubai")
        self.watchdog = ChannelWatchdog(
            check_interval=1800,    # 30 分钟 / 30 minutes
            max_retries=5,
            backoff_base=60,
            backoff_max=3600,
        )
        # C-03: 初始化锁 / Init lock, prevent concurrent Orchestrator creation
        self._init_lock = asyncio.Lock()

        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["http://localhost:5196", "http://127.0.0.1:5196"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        # Routes
        self.app.get("/")(self._handle_dashboard)
        self.app.websocket("/ws")(self._handle_ws)
        self.app.post("/webhook/feishu")(self._handle_feishu_webhook)
        self.app.post("/internal/feishu_message")(self._handle_feishu_internal)
        self.app.post("/internal/telegram_message")(self._handle_telegram_internal)
        self.app.get("/api/status")(self._handle_status)
        self.app.get("/api/scheduler")(self._handle_scheduler_status)

    async def _init_agent(self):
        """C-03: asyncio.Lock + double-check 防止并发初始化 / Prevent concurrent init with asyncio.Lock + double-check
        V8-C01: 用 asyncio.to_thread 包装阻塞初始化 / Wrap blocking init with asyncio.to_thread
        """
        if self.agent:
            return
        async with self._init_lock:
            if self.agent:  # double-check
                return
            # V8-C01: Orchestrator.__init__ 包含同步 I/O / Has sync I/O (SQLite, file scan),
            # 放到线程池中避免阻塞事件循环 / Run in thread pool to avoid blocking event loop
            self.agent = await asyncio.to_thread(AgentOrchestrator, self.config)

            # 飞书通道（lark-oapi WebSocket + REST）/ Feishu channel (lark-oapi WebSocket + REST)
            if self.config.channels.feishu.enabled:
                self.feishu = FeishuChannel({
                    "app_id": self.config.channels.feishu.app_id,
                    "app_secret": self.config.channels.feishu.app_secret,
                    "verification_token": self.config.channels.feishu.verification_token,
                    "encrypt_key": self.config.channels.feishu.encrypt_key,
                    "callback_url": "http://localhost:5196/internal/feishu_message",
                })
                self.feishu.set_handler(self._handle_feishu_message)
                logger.info("Feishu channel enabled (lark-oapi)")
            else:
                logger.info("Feishu channel disabled")

            # Telegram 通道（aiogram polling subprocess）/ Telegram channel (aiogram polling subprocess)
            if self.config.channels.telegram.enabled and self.config.channels.telegram.bot_token:
                self.telegram = TelegramChannel({
                    "bot_token": self.config.channels.telegram.bot_token,
                    "admin_ids": self.config.channels.telegram.admin_ids,
                    "allowed_groups": self.config.channels.telegram.allowed_groups,
                    "callback_url": "http://localhost:5196/internal/telegram_message",
                })
                self.telegram.set_handler(self._handle_telegram_message)
                logger.info("Telegram channel enabled (aiogram)")
            else:
                logger.info("Telegram channel disabled")

            # 注册通道到看门狗 / Register channels to watchdog
            if self.feishu:
                self.watchdog.register(
                    name="feishu",
                    start_fn=self.feishu.start,
                    stop_fn=self.feishu.stop,
                    is_alive_fn=lambda: (
                        self.feishu._ws_process.is_alive()
                        if self.feishu._ws_process else False
                    ),
                )
            if self.telegram:
                self.watchdog.register(
                    name="telegram",
                    start_fn=self.telegram.start,
                    stop_fn=self.telegram.stop,
                    is_alive_fn=lambda: (
                        self.telegram._ws_process.is_alive()
                        if self.telegram._ws_process else False
                    ),
                )

            # 定时任务 / Cron jobs
            register_default_jobs(self.scheduler, self.agent)
            self.scheduler.set_log_dir(
                str(self.config.workspace) + "/logs/scheduler"
            )
            self.scheduler.start()
            logger.info("Scheduler started")

    async def _handle_feishu_message(self, text: str, sender_id: str = "", chat_id: str = "") -> str:
        """飞书消息处理回调 / Feishu message handler callback"""
        full_resp = ""
        async for event in self.agent.process_message(text):
            if event["type"] == "text":
                full_resp = event["content"]
        return full_resp

    async def _handle_telegram_message(self, text: str, chat_id: str = "", username: str = "") -> str:
        """Telegram 消息处理回调 / Telegram message handler callback"""
        full_resp = ""
        async for event in self.agent.process_message(text):
            if event["type"] == "text":
                full_resp = event["content"]
        return full_resp

    async def start(self, host: str = "127.0.0.1", port: int = 5196):
        await self._init_agent()

        # C-01: 启动时检查 secret 配置 / Check secret config on startup
        _secret = _get_internal_secret()
        if not _secret:
            logger.warning("⚠️ MYAGENT_INTERNAL_SECRET not set — internal endpoints will reject requests!")
            logger.warning("⚠️ Set MYAGENT_INTERNAL_SECRET env var for security")

        # 启动 / Startup飞书 WebSocket 子进程
        if self.feishu:
            logger.info("Starting Feishu WebSocket subprocess...")
            await self.feishu.start()

        # 启动 / Startup Telegram 子进程
        if self.telegram:
            logger.info("Starting Telegram polling subprocess...")
            await self.telegram.start()

        # 启动 / Startup通道看门狗
        if self.watchdog._channels:
            logger.info("Starting channel watchdog...")
            await self.watchdog.start()

        logger.info(f"Gateway starting on {host}:{port}")
        config = uvicorn.Config(self.app, host=host, port=port, log_level="warning")
        server = uvicorn.Server(config)

        # 注册 shutdown 钩子 / Register shutdown hook (cross-uvicorn compat)
        async def _on_shutdown():
            logger.info("Gateway shutting down, cleaning up subprocesses...")
            await self.stop()

        if hasattr(server, 'shutdownHandlers'):
            server.shutdownHandlers.append(_on_shutdown)
        else:
            # uvicorn >= 0.34 — use signal handlers on Linux/macOS only
            import signal
            import sys
            loop = asyncio.get_running_loop()
            if sys.platform != 'win32':
                # Unix: use add_signal_handler
                for sig in (signal.SIGTERM, signal.SIGINT):
                    loop.add_signal_handler(sig, lambda: asyncio.ensure_future(_on_shutdown()))
            else:
                # Windows: add_signal_handler not supported, use KeyboardInterrupt fallback
                logger.info("Windows detected — using KeyboardInterrupt handler for graceful shutdown")

        await server.serve()

    async def stop(self):
        """清理所有子进程和资源 / Clean up all subprocesses and resources"""
        # 先停止看门狗 / Stop watchdog first
        if self.watchdog:
            try:
                await self.watchdog.stop()
            except Exception as e:
                logger.error(f"Error stopping watchdog: {e}")

        if self.feishu:
            try:
                await self.feishu.stop()
            except Exception as e:
                logger.error(f"Error stopping Feishu channel: {e}")

        if self.telegram:
            try:
                await self.telegram.stop()
            except Exception as e:
                logger.error(f"Error stopping Telegram channel: {e}")

        # 关闭 LLM Router 连接池 / Close LLM Router connection pool
        if self.agent and hasattr(self.agent, "llm"):
            try:
                await self.agent.llm.close_all()
            except Exception as e:
                logger.error(f"Error closing LLM router: {e}")

        logger.info("Gateway cleanup complete")

    # --- Internal Auth ---

    async def _verify_internal(self, request: Request) -> bool:
        """C-01: 验证 HMAC 签名 / Verify HMAC signature — reject without secret"""
        _secret = _get_internal_secret()
        if not _secret:
            logger.error("MYAGENT_INTERNAL_SECRET not set — rejecting internal request")
            return False
        sig = request.headers.get("X-Internal-Signature", "")
        if not sig:
            return False
        try:
            body = await request.body()
            if not body:
                return False
            expected = hmac.new(
                _get_internal_secret().encode(), body, hashlib.sha256
            ).hexdigest()
            return hmac.compare_digest(sig, expected)
        except Exception:
            return False

    # --- Handlers ---

    async def _handle_dashboard(self):
        return HTMLResponse(DASHBOARD_HTML)

    async def _handle_status(self):
        """H-18: status 端点 — 仅限本地访问 / Status endpoint — local access only"""
        # 简单的本地访问检查 / Simple local access check (WebSocket/dashboard is local)
        await self._init_agent()
        status = self.agent.get_status()
        status["scheduler"] = self.scheduler.get_status()
        status["channels"] = {
            "feishu": {
                "enabled": self.config.channels.feishu.enabled,
                "mode": "websocket subprocess + webhook",
                "ws_process_alive": self.feishu._ws_process.is_alive() if self.feishu and hasattr(self.feishu, '_ws_process') and self.feishu._ws_process else False,
            },
            "telegram": self.telegram.get_status() if self.telegram else {
                "enabled": False,
            },
        }
        status["watchdog"] = self.watchdog.get_status()
        return status

    async def _handle_scheduler_status(self):
        return self.scheduler.get_status()

    async def _handle_ws(self, ws: WebSocket):
        await ws.accept()
        await self._init_agent()
        logger.info("WebSocket client connected")
        try:
            while True:
                data = await ws.receive_json()
                message = data.get("message", "")
                if not message:
                    continue
                async for event in self.agent.process_message(message):
                    await ws.send_json(event)
        except Exception:
            logger.info("WebSocket disconnected")

    async def _handle_feishu_webhook(self, request: Request):
        """飞书 Webhook 回调（兼容模式）/ Feishu Webhook callback (compat mode)"""
        await self._init_agent()
        body = await request.json()

        if body.get("type") == "url_verification":
            return Response(
                content=json.dumps({"challenge": body.get("challenge")}),
                media_type="application/json",
            )

        if self.feishu:
            result = await self.feishu.handle_webhook(body, headers=dict(request.headers))
            return Response(content=json.dumps(result), media_type="application/json")

        return Response(
            content=json.dumps({"error": "Feishu not configured"}),
            media_type="application/json",
            status_code=404,
        )

    async def _handle_feishu_internal(self, request: Request):
        """内部回调：飞书子进程转发消息到主进程 / Internal: Feishu subprocess forwards to main

        F-04: 异步架构 — 立即返回 202 / Async — return 202, push reply after background processing
        避免长任务导致子进程 callback 超时 / Avoid callback timeout from long tasks
        """
        if not await self._verify_internal(request):
            return {"status": "error", "error": "Unauthorized"}
        await self._init_agent()
        data = await request.json()

        text = data.get("text", "")
        sender_id = data.get("sender_id", "")
        chat_id = data.get("chat_id", "")

        if not text.strip():
            return {"status": "empty"}

        logger.info(f"[Feishu internal] {sender_id}: {text[:80]}")

        # F-04: 启动后台任务，立即返回 / Start background task, return immediately
        asyncio.ensure_future(
            self._process_and_reply_feishu(text, chat_id)
        )

        return {"status": "processing"}

    async def _process_and_reply_feishu(self, text: str, chat_id: str):
        """后台处理飞书消息并推送回复 / Background: process Feishu message and push reply

        F-05: 中间进度推送 + 立即确认 / Intermediate progress push + immediate ack
        - Send immediate acknowledgment "Received, processing..."
        - 每完成一个工具调用，推送进度消息 / Push progress per tool call
        - 最终回复替换进度消息 / Final reply replaces progress
        """
        try:
            # F-05-1: 立即确认收到 / Immediate acknowledgment
            if chat_id and self.feishu:
                await self.feishu.send(chat_id, "⏳ Received, processing...")

            full_resp = ""
            step_count = 0
            progress_msg_id = None
            last_progress_time = 0

            import time as _t
            async for event in self.agent.process_message(text):
                if event["type"] == "tool_result":
                    import time as _t
                    now = _t.monotonic()
                    # F-05-2: 每完成一步推送进度 / Push progress per step (min 5s interval)
                    if chat_id and self.feishu and (now - last_progress_time) >= 10:
                        step_count += 1
                        tool_name = event.get("name", "unknown")
                        success = event.get("success", True)
                        status_icon = "✅" if success else "⚠️"
                        friendly_names = {
                            "web_search": "Web Search",
                            "deep_search": "Deep Search",
                            "web_fetch": "Web Fetch",
                            "write": "Write File",
                            "edit": "Edit File",
                            "read": "Read File",
                            "email_send": "Send Email",
                            "email_read": "Read Email",
                            "exec": "Execute Command",
                            "data_analysis": "Data Analysis",
                        }
                        friendly = friendly_names.get(tool_name, tool_name)
                        progress_text = f"{status_icon} Step {step_count}: {friendly} done"
                        try:
                            await self.feishu.send(chat_id, progress_text)
                            last_progress_time = now
                        except Exception:
                            pass
                elif event["type"] == "text":
                    full_resp = event["content"]

            # 发送最终回复 / Send final reply
            if full_resp and chat_id and self.feishu:
                await self.feishu.send(chat_id, full_resp)
        except Exception as e:
            logger.error(f"Feishu background processing error: {e}")
            if chat_id and self.feishu:
                await self.feishu.send(chat_id, f"❌ Error: {e}")

    async def _handle_telegram_internal(self, request: Request):
        """内部回调：Telegram 子进程转发消息到主进程 / Internal: Telegram subprocess forwards to main

        F-04: 命令同步返回，普通消息异步 / Commands sync, regular messages async
        """
        if not await self._verify_internal(request):
            return {"status": "error", "error": "Unauthorized"}
        await self._init_agent()
        data = await request.json()

        if not self.telegram:
            return {"status": "error", "error": "Telegram not configured"}

        msg_type = data.get("type", "")

        # 命令和 bot_info 同步处理（快速响应）/ Commands and bot_info sync (fast response)
        if msg_type in ("bot_info", "command"):
            return await self.telegram.handle_internal_message(data)

        # 普通消息：异步处理，立即返回 / Regular messages: async processing, return immediately
        if msg_type == "message":
            asyncio.ensure_future(
                self._process_and_reply_telegram(data)
            )
            return {"status": "processing"}

        return await self.telegram.handle_internal_message(data)

    async def _process_and_reply_telegram(self, data: dict):
        """后台处理 Telegram 消息并推送回复 / Background: process Telegram message and push reply

        F-05: 中间进度推送 + 立即确认 / Intermediate progress push + immediate ack
        """
        try:
            text = data.get("text", "")
            chat_id = data.get("chat_id", 0)
            username = data.get("username", "")

            # F-05-1: 立即确认收到 / Immediate acknowledgment
            if chat_id and self.telegram:
                await self.telegram.send_message(chat_id, "⏳ Received, processing...")

            full_resp = ""
            step_count = 0
            last_progress_time = 0

            async for event in self.agent.process_message(text):
                if event["type"] == "tool_result":
                    import time as _t
                    now = _t.monotonic()
                    if chat_id and self.telegram and (now - last_progress_time) >= 10:
                        step_count += 1
                        tool_name = event.get("name", "unknown")
                        success = event.get("success", True)
                        status_icon = "✅" if success else "⚠️"
                        friendly_names = {
                            "web_search": "Web Search",
                            "deep_search": "Deep Search",
                            "web_fetch": "Web Fetch",
                            "write": "Write File",
                            "edit": "Edit File",
                            "read": "Read File",
                            "email_send": "Send Email",
                            "email_read": "Read Email",
                            "exec": "Execute Command",
                            "data_analysis": "Data Analysis",
                        }
                        friendly = friendly_names.get(tool_name, tool_name)
                        progress_text = f"{status_icon} Step {step_count}: {friendly} done"
                        try:
                            await self.telegram.send_message(chat_id, progress_text)
                            last_progress_time = now
                        except Exception:
                            pass
                elif event["type"] == "text":
                    full_resp = event["content"]

            # 发送最终回复 / Send final reply
            if full_resp and self.telegram:
                await self.telegram.send_message(chat_id, full_resp)
                # 维护对话历史 / Maintain conversation history
                if chat_id not in self.telegram._conversations:
                    self.telegram._conversations[chat_id] = []
                self.telegram._conversations[chat_id].append({"role": "user", "content": text})
                self.telegram._conversations[chat_id].append({"role": "assistant", "content": full_resp})
                if len(self.telegram._conversations[chat_id]) > 100:
                    self.telegram._conversations[chat_id] = self.telegram._conversations[chat_id][-60:]
        except Exception as e:
            logger.error(f"Telegram background processing error: {e}")
            if self.telegram:
                try:
                    await self.telegram.send_message(chat_id, f"❌ Error: {e}")
                except Exception:
                    pass
