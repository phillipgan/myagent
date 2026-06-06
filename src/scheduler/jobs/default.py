"""内置定时任务 / Built-in Cron Jobs — Morning Brief, Email Check, News Summary / Built-in Cron Jobs — Morning Brief, Email Check, News Summary

修复:
Fixes:
- C-07: 天气查询改用 httpx / Weather uses httpx HTTP, no longer shell curl
"""

import asyncio
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


async def _fetch_weather(city: str = "Dubai") -> str:
    """C-07: 使用 httpx 获取天气 / Get weather via httpx, no longer shell curl"""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://wttr.in/{city}",
                params={"format": "3"},
                headers={"User-Agent": "curl/7.68.0"},
            )
            resp.raise_for_status()
            return resp.text.strip()
    except Exception as e:
        logger.warning(f"Weather fetch failed: {e}")
        return "查询失败"


async def morning_brief(agent) -> str:
    """🌅 每日早报 / Morning Brief — weather + email summary + schedule"""
    parts = [f"🌅 Good morning! {datetime.now().strftime('%Y年%m月%d日 %A')}\n"]  # 早安问候 / Morning greeting

    # 天气 — C-07: 使用 HTTP 请求 / Weather — C-07: use HTTP request
    try:
        weather = await _fetch_weather("Dubai")
        parts.append(f"🌤️ 迪拜天气: {weather}")
    except Exception:
        parts.append("🌤️ 天气查询失败")

    # 邮件摘要 / Email summary
    try:
        emails = await agent.tools.execute("email_read", action="list", account="gmail", limit=5)
        parts.append(f"\n📧 最近邮件:\n{emails.output[:500]}")
    except Exception:
        parts.append("\n📧 邮件查询失败")

    # 记忆回顾 / Memory recall — wrap sync SQLite in asyncio.to_thread
    try:
        recent = await asyncio.to_thread(agent.memory.episodic.get_recent, hours=24, limit=5)
        if recent:
            parts.append("\n📝 昨日回顾:")
            for mem in recent:
                parts.append(f"  - {mem['content'][:80]}")
    except Exception:
        pass

    brief = "\n".join(parts)

    # 存储到记忆 / Store to memory
    try:
        await asyncio.to_thread(
            agent.memory.episodic.store,
            content=f"Morning brief generated: {brief[:200]}",
            metadata={"type": "morning_brief"},
            importance=0.5,
        )
    except Exception:
        pass

    return brief


async def email_check(agent) -> str:
    """📧 邮件巡检 / Email Check — check important unread emails"""
    try:
        result = await agent.tools.execute("email_read", action="list", account="gmail", limit=3)
        summary = f"📧 邮件巡检 ({datetime.now().strftime('%H:%M')}):\n{result.output[:300]}"

        try:
            await asyncio.to_thread(
                agent.memory.episodic.store,
                content=summary,
                metadata={"type": "email_check"},
                importance=0.3,
            )
        except Exception:
            pass
        return summary
    except Exception as e:
        return f"Email check failed: {e}"


async def memory_consolidation(agent) -> str:
    """🧠 记忆巩固 / Memory Consolidation — cleanup expired + update stats"""
    try:
        await asyncio.to_thread(agent.memory.episodic.cleanup)
    except Exception as e:
        logger.warning(f"Memory cleanup failed: {e}")

    try:
        recent = await asyncio.to_thread(agent.memory.episodic.get_recent, hours=24, limit=100)
        result = f"🧠 记忆巩固完成: {len(recent)} 条近期记忆"
    except Exception:
        result = "🧠 记忆巩固完成"

    logger.info(result)
    return result


def register_default_jobs(scheduler, agent):
    """注册默认定时任务 / Register default cron jobs"""
    scheduler.register_job(
        "morning_brief",
        "0 7 * * 1-5",  # 工作日早上7点 / Weekday 7AM
        lambda: morning_brief(agent),
        description="工作日早报（天气+邮件+日程）",
    )

    scheduler.register_job(
        "email_check",
        "*/30 * * * *",  # 每30分钟 / Every 30 minutes
        lambda: email_check(agent),
        description="邮件巡检",
    )

    scheduler.register_job(
        "memory_consolidation",
        "0 3 * * *",  # 每日凌晨3点 / Daily 3AM
        lambda: memory_consolidation(agent),
        description="记忆巩固和清理",
    )
