"""定时任务调度器 — APScheduler / Cron Scheduler — APScheduler

修复:
Fixes:
- H-01: asyncio.Lock 懒初始化，避免在事件循环外创建
- H-22: 日志写入 asyncio.to_thread() / Log writes via asyncio.to_thread() to avoid blocking
- C-06: threading.Lock 保护 asyncio.Lock 初始化 / threading.Lock protects lazy init, prevents thread race
"""

import json
import logging
import asyncio
import threading
from datetime import datetime
from pathlib import Path
from typing import Callable, Awaitable

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


class CronScheduler:
    """定时任务调度器 / Cron Task Scheduler"""

    def __init__(self, timezone: str = "Asia/Dubai"):
        self.scheduler = AsyncIOScheduler(timezone=timezone)
        self.jobs: dict[str, dict] = {}
        self.log_dir: Path | None = None
        # C-06: threading.Lock 保护 asyncio.Lock 初始化 / threading.Lock protects asyncio.Lock init
        self._log_lock: asyncio.Lock | None = None
        self._init_lock = threading.Lock()

    def _get_lock(self) -> asyncio.Lock:
        """C-06: 线程安全的 asyncio.Lock 懒初始化 / Thread-safe asyncio.Lock lazy init"""
        if self._log_lock is None:
            with self._init_lock:
                if self._log_lock is None:
                    self._log_lock = asyncio.Lock()
        return self._log_lock

    def set_log_dir(self, log_dir: str):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def register_job(
        self,
        name: str,
        cron: str,
        handler: Callable[[], Awaitable[str]],
        description: str = "",
    ):
        """注册定时任务 / Register cron job"""
        self.jobs[name] = {
            "handler": handler,
            "cron": cron,
            "description": description,
            "last_run": None,
            "last_result": None,
        }

        trigger = CronTrigger.from_crontab(cron, timezone=self.scheduler.timezone)
        self.scheduler.add_job(
            self._run_job,
            trigger,
            id=name,
            args=[name],
            replace_existing=True,
            misfire_grace_time=300,
        )
        logger.info(f"Job registered: {name} ({cron})")

    async def _run_job(self, name: str):
        """执行定时任务 / Execute cron job"""
        job = self.jobs.get(name)
        if not job:
            return

        logger.info(f"Running job: {name}")
        try:
            result = await job["handler"]()
            result_str = str(result) if result else "OK"
            job["last_run"] = datetime.now().isoformat()
            job["last_result"] = result_str[:200]

            # 日志写入 / Log writing
            if self.log_dir:
                lock = self._get_lock()
                async with lock:
                    await asyncio.to_thread(self._write_log, name, result_str)

            logger.info(f"Job {name} completed")

        except Exception as e:
            logger.error(f"Job {name} failed: {e}")
            job["last_run"] = datetime.now().isoformat()
            job["last_result"] = f"Error: {e}"

    def _write_log(self, name: str, result: str):
        """同步写日志文件 / Sync log file write (in to_thread)"""
        log_file = self.log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        entry = {
            "timestamp": datetime.now().isoformat(),
            "job": name,
            "result": result[:500],
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def start(self):
        """启动调度器 / Start scheduler"""
        self.scheduler.start()
        logger.info(f"Scheduler started ({len(self.jobs)} jobs)")

    def stop(self):
        """停止调度器 / Stop scheduler"""
        self.scheduler.shutdown()
        logger.info("Scheduler stopped")

    def get_status(self) -> dict:
        """获取调度器状态 / Get scheduler status"""
        return {
            "running": self.scheduler.running,
            "jobs": {
                name: {
                    "cron": job["cron"],
                    "description": job["description"],
                    "last_run": job["last_run"],
                    "last_result": job["last_result"],
                }
                for name, job in self.jobs.items()
            },
        }
