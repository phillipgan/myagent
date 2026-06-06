"""Channel Watchdog — 通道看门狗 / Channel Watchdog

定期检测所有通道子进程的存活状态，发现崩溃自动重启。
Periodically checks channel subprocess health, auto-restarts on crash.
采用指数退避策略，避免 DNS 持续故障时疯狂重连。
Uses exponential backoff to avoid aggressive reconnection on persistent failures.
Uses exponential backoff to avoid aggressive reconnection on persistent DNS failures.

配置项（config/default.yaml → channels.watchdog）/ Config (config/default.yaml → channels.watchdog):
Config options (config/default.yaml → channels.watchdog):
    enabled: true           # 是否启用看门狗 / Enable watchdog (default true)
    check_interval: 1800    # 检测间隔（秒）/ Check interval (seconds, default 30 min)
    max_retries: 5          # 单通道最大连续重试 / Max consecutive retries per channel
    backoff_base: 60        # 退避基数（秒）/ Backoff base (sec), retry N = base × 2^(N-1)
    backoff_max: 3600       # 最大退避间隔 / Max backoff interval (seconds, default 1h)
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Optional, Callable, Awaitable

logger = logging.getLogger(__name__)


@dataclass
class ChannelState:
    """单个通道的运行状态 / Runtime state of a single channel"""
    name: str
    start_fn: Callable[[], Awaitable[None]]       # 启动 / Startup函数
    stop_fn: Callable[[], Awaitable[None]]         # 停止函数 / Stop function
    is_alive_fn: Callable[[], bool]                # 存活检测函数 / Alive check function
    # 运行时状态 / Runtime state
    consecutive_failures: int = 0
    last_check_time: float = 0.0
    last_restart_time: float = 0.0
    total_restarts: int = 0
    next_retry_after: float = 0.0  # 下次允许重试的时间戳（退避后）/ Next allowed retry timestamp (after backoff)


class ChannelWatchdog:
    """通道看门狗 — 后台定时检测 + 自动重启 / Channel Watchdog — background health check + auto-restart

    生命周期：
Lifecycle:
        1. Gateway.start() 中调用 watchdog.start() / Call watchdog.start() in Gateway.start()
        2. 每 check_interval 秒遍历所有通道 / Iterate all channels every check_interval seconds
        3. 对每个通道调用 is_alive_fn() / Call is_alive_fn() per channel
        4. 如果通道已死：/ 4. If channel is dead:
           a. 检查退避时间 / Check backoff time (reached next_retry_after?)
           b. 如果未到，跳过本次 / Not reached, skip this round
           c. 如果已到，执行重启 / Reached, execute stop_fn() → start_fn() restart
           d. 重启后更新失败计数和退避 / Increment failures, update next_retry_after
           e. 超过 max_retries 进入冷却 / Exceeded max_retries, enter cooldown
        5. 如果通道存活，重置计数 / Alive: reset consecutive_failures = 0
    """

    def __init__(
        self,
        check_interval: int = 1800,
        max_retries: int = 5,
        backoff_base: int = 60,
        backoff_max: int = 3600,
    ):
        self.check_interval = check_interval
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max

        self._channels: dict[str, ChannelState] = {}
        self._task: Optional[asyncio.Task] = None
        self._running = False

    def register(
        self,
        name: str,
        start_fn: Callable[[], Awaitable[None]],
        stop_fn: Callable[[], Awaitable[None]],
        is_alive_fn: Callable[[], bool],
    ):
        """注册一个通道到看门狗监控 / Register a channel to watchdog

        Args:
            name: 通道名称 / Channel name (e.g., "feishu", "telegram")
            start_fn: 异步启动函数 / Async start function
            stop_fn: 异步停止函数 / Async stop function
            is_alive_fn: 同步存活检测函数 / Sync alive check function (returns bool)
        """
        self._channels[name] = ChannelState(
            name=name,
            start_fn=start_fn,
            stop_fn=stop_fn,
            is_alive_fn=is_alive_fn,
        )
        logger.info(f"Watchdog: registered channel '{name}'")

    def unregister(self, name: str):
        """取消注册通道 / Unregister channel"""
        self._channels.pop(name, None)
        logger.info(f"Watchdog: unregistered channel '{name}'")

    async def start(self):
        """启动看门狗后台任务 / Start watchdog background task"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info(
            f"Watchdog started (interval={self.check_interval}s, "
            f"max_retries={self.max_retries}, backoff={self.backoff_base}-{self.backoff_max}s)"
        )

    async def stop(self):
        """停止看门狗 / Stop watchdog"""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Watchdog stopped")

    async def _run_loop(self):
        """主循环 — 定时检测所有通道 / Main loop — periodic channel health check"""
        # 首次启动延迟 60 秒 / Initial 60s delay for system init
        await asyncio.sleep(60)

        while self._running:
            try:
                await self._check_all()
            except Exception as e:
                logger.error(f"Watchdog check cycle error: {e}", exc_info=True)

            await asyncio.sleep(self.check_interval)

    async def _check_all(self):
        """检测所有注册的通道 / Check all registered channels"""
        now = time.monotonic()

        for name, state in list(self._channels.items()):
            state.last_check_time = now
            alive = False

            try:
                alive = state.is_alive_fn()
            except Exception as e:
                logger.warning(f"Watchdog: is_alive check failed for '{name}': {e}")

            if alive:
                # 通道正常，重置失败计数 / Channel healthy, reset failure count
                if state.consecutive_failures > 0:
                    logger.info(
                        f"Watchdog: channel '{name}' recovered "
                        f"(was {state.consecutive_failures} consecutive failures)"
                    )
                state.consecutive_failures = 0
                state.next_retry_after = 0.0
                continue

            # ── 通道已死，判断是否可以重试 / Channel dead, check if retry is allowed ──

            if now < state.next_retry_after:
                # 退避中，跳过 / In backoff, skip
                remaining = int(state.next_retry_after - now)
                logger.debug(
                    f"Watchdog: '{name}' is dead, waiting {remaining}s before retry "
                    f"(failure #{state.consecutive_failures})"
                )
                continue

            # 超过最大重试次数，进入长冷却 / Exceeded max retries, enter long cooldown
            if state.consecutive_failures >= self.max_retries:
                logger.warning(
                    f"Watchdog: '{name}' exceeded max_retries ({self.max_retries}), "
                    f"entering cooldown until next check cycle. "
                    f"Total restarts: {state.total_restarts}"
                )
                # 重置计数，下个大周期重试 / Reset count, retry next major cycle
                state.consecutive_failures = 0
                state.next_retry_after = now + self.check_interval
                continue

            # ── 执行重启 / Execute restart ──
            logger.warning(
                f"Watchdog: channel '{name}' is dead! "
                f"Attempting restart (attempt {state.consecutive_failures + 1}/{self.max_retries})..."
            )

            try:
                # 先停止（清理残留资源）/ Stop first (cleanup residual resources)
                await state.stop_fn()
                await asyncio.sleep(2)  # 短暂等待资源释放 / Brief wait for resource release

                # 再启动 / Then start
                await state.start_fn()

                state.consecutive_failures += 1
                state.last_restart_time = time.monotonic()
                state.total_restarts += 1

                # 计算退避 / Calculate backoff: base × 2^(failures-1), capped at max
                backoff = min(
                    self.backoff_base * (2 ** max(0, state.consecutive_failures - 1)),
                    self.backoff_max,
                )
                state.next_retry_after = time.monotonic() + backoff

                logger.info(
                    f"Watchdog: '{name}' restart attempted, "
                    f"next check in {backoff}s "
                    f"(consecutive failures: {state.consecutive_failures})"
                )

            except Exception as e:
                logger.error(
                    f"Watchdog: failed to restart '{name}': {e}", exc_info=True
                )
                state.consecutive_failures += 1
                state.total_restarts += 1
                backoff = min(
                    self.backoff_base * (2 ** max(0, state.consecutive_failures - 1)),
                    self.backoff_max,
                )
                state.next_retry_after = time.monotonic() + backoff

    def get_status(self) -> dict:
        """获取看门狗状态 / Get watchdog status (for /api/status)"""
        now = time.monotonic()
        channels = {}
        for name, state in self._channels.items():
            channels[name] = {
                "alive": state.is_alive_fn() if state.is_alive_fn else False,
                "consecutive_failures": state.consecutive_failures,
                "total_restarts": state.total_restarts,
                "last_check": int(state.last_check_time) if state.last_check_time else None,
                "last_restart": int(state.last_restart_time) if state.last_restart_time else None,
                "next_retry_in": max(0, int(state.next_retry_after - now)) if state.next_retry_after > now else 0,
            }
        return {
            "enabled": self._running,
            "check_interval": self.check_interval,
            "max_retries": self.max_retries,
            "channels": channels,
        }
