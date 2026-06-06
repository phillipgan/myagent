"""Telegram 通道 — 基于 aiogram 3.x / Telegram Channel — Based on aiogram 3.x

架构：
Architecture:aiogram Bot + Long Polling / Architecture: aiogram Bot + Long Polling (default) / Webhook (optional)
- 长轮询模式：子进程运行 / Long polling: subprocess, no public IP needed
- Webhook 模式：通过 FastAPI 路由 / Webhook: via FastAPI route
- 支持：私聊、群组、内联键盘 / Supports: DM, groups, inline keyboards, Markdown/HTML, FSM

依赖：aiogram >= 3.15, httpx / Dependencies: aiogram >= 3.15, httpx
"""

import asyncio
import json
import logging
import multiprocessing
import os
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════
# 子进程 Worker（Long Polling 模式）/ Subprocess Worker (Long Polling mode)
# ═══════════════════════════════════════════════════════════

def _telegram_polling_worker(bot_token: str, callback_url: str, admin_ids: str = ""):
    """子进程：aiogram 长轮询 / Subprocess: aiogram long polling, HTTP callback to main"""
    import asyncio as _asyncio
    import logging as _logging

    _logging.basicConfig(level=_logging.INFO, format="%(asctime)s [tg-poll] %(levelname)s: %(message)s")
    log = _logging.getLogger("tg-polling")

    try:
        import urllib.request
        from aiogram import Bot, Dispatcher, types, F
        from aiogram.filters import Command, CommandStart
        from aiogram.enums import ParseMode
        from aiogram.client.default import DefaultBotProperties
    except ImportError:
        log.error("aiogram not installed. Run: pip install aiogram>=3.15")
        return

    bot = Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()

    # 解析管理员 ID / Parse admin IDs
    admin_set = set()
    if admin_ids:
        for uid in admin_ids.split(","):
            uid = uid.strip()
            if uid.isdigit():
                admin_set.add(int(uid))

    def _post_to_main(data: dict):
        """HTTP POST 回调主进程 / HTTP POST callback to main (with HMAC signature)
        H-08: 子进程中同步 urllib 安全 / Sync urllib in subprocess is safe (has own event loop)
        但缩短超时 / Shorten timeout to avoid long blocking
        """
        try:
            import hmac as _hmac
            import hashlib
            import os
            payload = json.dumps(data).encode()
            headers = {"Content-Type": "application/json"}
            secret = os.environ.get("MYAGENT_INTERNAL_SECRET", "")
            if secret:
                sig = _hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
                headers["X-Internal-Signature"] = sig
            req = urllib.request.Request(
                callback_url, data=payload, headers=headers, method="POST",
            )
            # F-04: 主进程立即返回 202，缩短超时 / Main returns 202 immediately, shorter timeout
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                return result.get("reply", "")
        except Exception as e:
            log.error(f"Callback to main process failed: {e}")
            return ""

    # ---------- 命令处理 / Command Handlers ----------

    @dp.message(CommandStart())
    async def cmd_start(message: types.Message):
        await message.answer(
            "👋 你好！我是 <b>MyAgent</b> 个人办公助手。\n\n"
            "直接发消息即可与我对话。\n"
            "输入 /help 查看帮助。"
        )

    @dp.message(Command("help"))
    async def cmd_help(message: types.Message):
        help_text = (
            "<b>🤖 MyAgent 帮助</b>\n\n"
            "🔹 直接发消息 — 与 AI 对话\n"
            "🔹 /status — 查看运行状态\n"
            "🔹 /skills — 查看已加载技能\n"
            "🔹 /tools — 查看可用工具\n"
            "🔹 /history — 查看最近对话\n"
            "🔹 /reset — 清除对话历史\n"
            "🔹 /help — 显示此帮助\n\n"
            "💡 支持自然语言，可执行搜索、文件操作、数据分析等任务。"
        )
        await message.answer(help_text)

    @dp.message(Command("status"))
    async def cmd_status(message: types.Message):
        reply = _post_to_main({
            "type": "command",
            "command": "status",
            "chat_id": message.chat.id,
            "user_id": message.from_user.id,
        })
        await message.answer(reply or "✅ MyAgent 运行中")

    @dp.message(Command("skills"))
    async def cmd_skills(message: types.Message):
        reply = _post_to_main({
            "type": "command",
            "command": "skills",
            "chat_id": message.chat.id,
            "user_id": message.from_user.id,
        })
        await message.answer(reply or "📦 技能列表加载中...")

    @dp.message(Command("tools"))
    async def cmd_tools(message: types.Message):
        reply = _post_to_main({
            "type": "command",
            "command": "tools",
            "chat_id": message.chat.id,
            "user_id": message.from_user.id,
        })
        await message.answer(reply or "🔧 工具列表加载中...")

    @dp.message(Command("history"))
    async def cmd_history(message: types.Message):
        reply = _post_to_main({
            "type": "command",
            "command": "history",
            "chat_id": message.chat.id,
            "user_id": message.from_user.id,
        })
        # Telegram 单条消息 4096 字符限制 / Telegram 4096 char limit per message
        if reply and len(reply) > 4096:
            for i in range(0, len(reply), 4096):
                await message.answer(reply[i:i + 4096])
        else:
            await message.answer(reply or "📝 暂无对话记录")

    @dp.message(Command("reset"))
    async def cmd_reset(message: types.Message):
        _post_to_main({
            "type": "command",
            "command": "reset",
            "chat_id": message.chat.id,
            "user_id": message.from_user.id,
        })
        await message.answer("🔄 对话历史已清除")

    # ---------- 普通消息处理 / Message Processing ----------

    @dp.message(F.text)
    async def handle_text(message: types.Message):
        user_id = message.from_user.id
        chat_id = message.chat.id
        chat_type = message.chat.type  # private / group / supergroup
        text = message.text

        # 群组权限检查 / Group permission check
        if chat_type in ("group", "supergroup"):
            # 群组中只有 @bot 或回复 bot 的消息才处理 / Only process @bot mentions and replies in groups
            if not message.reply_to_message and not _is_mentioned(text, bot):
                return
            # 去掉 @bot_name / Strip @bot_name
            text = _strip_bot_mention(text, bot)

        log.info(f"[{chat_type}] {message.from_user.username or user_id}: {text[:80]}")

        # 发送"正在输入"状态 / Send "typing" status
        await bot.send_chat_action(chat_id=chat_id, action="typing")

        # 回调主进程处理 / Callback to main process
        reply = _post_to_main({
            "type": "message",
            "text": text,
            "chat_id": chat_id,
            "user_id": user_id,
            "username": message.from_user.username or "",
            "chat_type": chat_type,
            "message_id": message.message_id,
        })

        if reply:
            # 消息过长时分段发送 / Split long messages into chunks
            if len(reply) > 4096:
                for i in range(0, len(reply), 4096):
                    await message.answer(reply[i:i + 4096])
            else:
                await message.answer(reply)

    # ---------- 群组辅助 / Group Helpers ----------

    def _is_mentioned(text: str, bot_obj) -> bool:
        """检查消息是否 @ 了 bot / Check if message mentions bot"""
        if bot_obj.username and f"@{bot_obj.username}" in text:
            return True
        return False

    def _strip_bot_mention(text: str, bot_obj) -> str:
        """移除 @bot 提及 / Remove @bot mention"""
        import re
        if bot_obj.username:
            text = re.sub(rf'@{re.escape(bot_obj.username)}\s*', '', text, count=1)
        return text.strip()

    # ---------- 错误处理 / Error Handling ----------

    @dp.error()
    async def on_error(event):
        log.error(f"aiogram error: {event.exception}")

    # ---------- 启动 / Startup ----------

    async def _run():
        me = await bot.get_me()
        log.info(f"Telegram bot @{me.username} (id:{me.id}) polling started")

        # 通知主进程 bot 信息 / Notify main process of bot info
        _post_to_main({
            "type": "bot_info",
            "bot_id": me.id,
            "bot_username": me.username,
            "bot_name": me.first_name,
        })

        # 启动 / Startup长轮询
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

    try:
        _asyncio.run(_run())
    except KeyboardInterrupt:
        log.info("Telegram polling interrupted")
    except Exception as e:
        log.error(f"Telegram polling error: {e}")


# ═══════════════════════════════════════════════════════════
# 主进程 TelegramChannel / Main Process TelegramChannel
# ═══════════════════════════════════════════════════════════

class TelegramChannel:
    """Telegram Bot 通道 / Telegram Bot Channel — aiogram subprocess + main process handler"""

    def __init__(self, config: dict):
        self.bot_token = config.get("bot_token", "")
        self.admin_ids = config.get("admin_ids", "")       # 逗号分隔的管理员 Telegram user ID / Comma-separated admin Telegram user IDs
        self.allowed_groups = config.get("allowed_groups", "")  # 逗号分隔的群组 ID / Comma-separated group IDs
        self._handler: Optional[Callable] = None
        self._ws_process = None
        self._callback_url = config.get("callback_url", "http://localhost:5196/internal/telegram_message")
        self._bot_info: dict = {}
        self._conversations: dict[int, list] = {}  # chat_id -> conversation history

        # 权限 / Permissions
        self._admin_set = set()
        if self.admin_ids:
            for uid in self.admin_ids.split(","):
                uid = uid.strip()
                if uid.lstrip("-").isdigit():
                    self._admin_set.add(int(uid))

        self._group_set = set()
        if self.allowed_groups:
            for gid in self.allowed_groups.split(","):
                gid = gid.strip()
                if gid.lstrip("-").isdigit():
                    self._group_set.add(int(gid))

    def set_handler(self, handler: Callable[[str, str, str], Awaitable[str]]):
        """设置消息处理函数 / Set message handler: handler(text, chat_id, username) -> reply"""
        self._handler = handler

    async def start(self):
        """启动 Telegram 通道 / Start Telegram channel (subprocess polling)"""
        if not self.bot_token:
            logger.error("Telegram bot_token is empty, skipping start")
            return

        logger.info(f"Starting Telegram polling subprocess (callback: {self._callback_url})")

        self._ws_process = multiprocessing.Process(
            target=_telegram_polling_worker,
            args=(self.bot_token, self._callback_url, self.admin_ids),
            daemon=True,
        )
        self._ws_process.start()
        logger.info(f"Telegram polling process started (PID: {self._ws_process.pid})")

    async def stop(self):
        """停止 Telegram 通道 / Stop Telegram channel"""
        if self._ws_process and self._ws_process.is_alive():
            self._ws_process.terminate()
            self._ws_process.join(timeout=5)
            logger.info("Telegram polling process stopped")

    async def handle_internal_message(self, data: dict) -> dict:
        """处理来自子进程的内部回调消息 / Handle internal callback message from subprocess"""
        msg_type = data.get("type", "")

        # Bot 信息注册 / Bot info registration
        if msg_type == "bot_info":
            self._bot_info = {
                "bot_id": data.get("bot_id"),
                "bot_username": data.get("bot_username"),
                "bot_name": data.get("bot_name"),
            }
            logger.info(f"Telegram bot registered: @{self._bot_info.get('bot_username')}")
            return {"status": "ok"}

        # 命令处理 / Command handlers
        if msg_type == "command":
            return await self._handle_command(data)

        # 消息处理 / Message handling
        if msg_type == "message":
            return await self._handle_message(data)

        return {"status": "unknown_type"}

    async def _handle_command(self, data: dict) -> dict:
        """处理 Telegram 命令 / Handle Telegram commands"""
        command = data.get("command", "")
        chat_id = data.get("chat_id", 0)
        user_id = data.get("user_id", 0)

        if command == "status":
            reply = "✅ MyAgent 运行中\n📡 Telegram 通道已连接"
            if self._bot_info:
                reply += f"\n🤖 Bot: @{self._bot_info.get('bot_username', 'unknown')}"
            return {"reply": reply}

        elif command == "skills":
            if self._handler:
                try:
                    reply = await self._handler("/skills", str(chat_id), "system")
                    return {"reply": reply}
                except Exception:
                    pass
            return {"reply": "📦 技能列表加载失败，请稍后重试"}

        elif command == "tools":
            if self._handler:
                try:
                    reply = await self._handler("/tools", str(chat_id), "system")
                    return {"reply": reply}
                except Exception:
                    pass
            return {"reply": "🔧 工具列表加载失败"}

        elif command == "history":
            history = self._conversations.get(chat_id, [])
            if not history:
                return {"reply": "📝 暂无对话记录"}
            lines = []
            for msg in history[-20:]:  # 最近20条 / Last 20 messages
                role = "👤" if msg["role"] == "user" else "🤖"
                content = msg["content"][:100].replace("\n", " ")
                lines.append(f"{role} {content}")
            return {"reply": "\n".join(lines)}

        elif command == "reset":
            self._conversations.pop(chat_id, None)
            return {"reply": "🔄 对话历史已清除"}

        return {"reply": ""}

    async def _handle_message(self, data: dict) -> dict:
        """处理普通消息 / Handle regular messages"""
        text = data.get("text", "")
        chat_id = data.get("chat_id", 0)
        user_id = data.get("user_id", 0)
        username = data.get("username", "")
        chat_type = data.get("chat_type", "private")

        if not text.strip():
            return {"status": "empty"}

        # 权限 / Permissions检查
        if chat_type == "private":
            if self._admin_set and user_id not in self._admin_set:
                logger.warning(f"Unauthorized DM from user {user_id}")
                return {"reply": "⛔ 你没有权限使用此 Bot。"}
        elif chat_type in ("group", "supergroup"):
            group_id = chat_id
            if self._group_set and group_id not in self._group_set:
                logger.warning(f"Unauthorized group {group_id}")
                return {"status": "unauthorized_group"}

        logger.info(f"[Telegram:{chat_type}] {username or user_id}: {text[:80]}")

        if self._handler:
            try:
                reply = await self._handler(text, str(chat_id), username)
                if reply:
                    # 维护对话历史 / Maintain conversation history
                    if chat_id not in self._conversations:
                        self._conversations[chat_id] = []
                    self._conversations[chat_id].append({"role": "user", "content": text})
                    self._conversations[chat_id].append({"role": "assistant", "content": reply})
                    # 限制历史长度 / Limit history length
                    if len(self._conversations[chat_id]) > 100:
                        self._conversations[chat_id] = self._conversations[chat_id][-60:]

                    return {"reply": reply}
            except Exception as e:
                logger.error(f"Telegram handler error: {e}")
                return {"reply": f"❌ 处理出错: {e}"}

        return {"reply": ""}

    def get_bot_info(self) -> dict:
        """获取 Bot 信息 / Get bot info"""
        return self._bot_info

    async def send_message(self, chat_id: int, text: str) -> bool:
        """F-04: 直接通过 Bot API 发送消息 / Send message directly via Bot API (for async push)
        不依赖子进程，主进程可直接回复用户
Does not depend on subprocess, main process can reply directly
        """
        if not self.bot_token:
            return False
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                # Telegram 单条消息 4096 字符限制 / Telegram 4096 char limit per message
                if len(text) > 4096:
                    chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
                else:
                    chunks = [text]
                for chunk in chunks:
                    resp = await client.post(
                        f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
                        json={"chat_id": chat_id, "text": chunk, "parse_mode": "HTML"}
                    )
                    data = resp.json()
                    if not data.get("ok"):
                        logger.error(f"Telegram send failed: {data.get('description', '')}")
                        return False
            return True
        except Exception as e:
            logger.error(f"Telegram send_message error: {e}")
            return False

    def get_status(self) -> dict:
        """获取通道状态 / Get channel status"""
        return {
            "enabled": True,
            "mode": "aiogram polling subprocess",
            "bot": self._bot_info.get("bot_username", "unknown"),
            "process_alive": self._ws_process.is_alive() if self._ws_process else False,
            "active_chats": len(self._conversations),
            "admin_ids": list(self._admin_set) if self._admin_set else "all",
        }
