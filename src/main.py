"""MyAgent — 个人办公助手 Agent 主入口 / Personal Office Assistant — Main Entry Point

提供 CLI 交互模式和 Gateway 网关模式。
Provides CLI interactive mode and Gateway mode (Web Dashboard + Feishu + Telegram).
Provides CLI interactive mode and Gateway mode (Web Dashboard + Feishu + Telegram).
网关默认端口 5196，绑定 127.0.0.1。
Gateway defaults to port 5196, bound to 127.0.0.1 for security.
Gateway default port 5196, bound to 127.0.0.1 for security.
"""

import asyncio
import logging
import sys
import argparse
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import load_config
from src.agent import AgentOrchestrator
from src.gateway import CLIChannel, Gateway


def setup_logging(level: str = "WARNING"):
    """配置全局日志格式和级别。/ Configure global logging format and level.

    Args:
        level: 日志级别字符串 / Log level string (DEBUG/INFO/WARNING/ERROR/CRITICAL)
    """
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.WARNING),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


async def run_cli(config):
    """启动 CLI 交互模式 — 终端 TUI 对话，无网关、无通道。/ Start CLI mode — terminal TUI chat, no gateway, no channels."""
    orchestrator = AgentOrchestrator(config)
    cli = CLIChannel()
    await cli.run(orchestrator)


async def run_gateway(config, port: int = 5196):
    """启动 Gateway 网关模式 — FastAPI + WebSocket + 飞书 + Telegram + Watchdog。/ Start Gateway mode — FastAPI + WebSocket + Feishu + Telegram + Watchdog.

    Args:
        config: AgentConfig 实例 / AgentConfig instance
        port: 监听端口（默认 5196）/ Listen port (default 5196)
    """
    import sys
    gateway = Gateway(config)
    # C-01: 默认绑定 127.0.0.1，避免暴露到整个网络 / C-01: Bind to 127.0.0.1 by default, avoid network exposure
    try:
        await gateway.start(host="127.0.0.1", port=port)
    except KeyboardInterrupt:
        # Windows 回退 — Ctrl+C 优雅关闭 / Windows fallback — Ctrl+C graceful shutdown
        print("\nShutting down...")
        await gateway.stop()


def main():
    """主入口 — 解析命令行参数，初始化工作目录，分发到对应子命令。/ Main entry — parse CLI args, init workspace, dispatch to subcommands."""
    parser = argparse.ArgumentParser(description="MyAgent - Personal Office Assistant")
    parser.add_argument("command", nargs="?", default="cli",
                        choices=["cli", "gateway", "status", "tools", "skills"])
    parser.add_argument("--port", type=int, default=5196)
    parser.add_argument("--config", type=str, default=None)
    parser.add_argument("--log", type=str, default="WARNING")
    args = parser.parse_args()

    setup_logging(args.log)
    config_path = args.config or str(ROOT_DIR / "config" / "default.yaml")
    config = load_config(config_path)

    # 初始化工作目录结构（记忆、会话、日志、技能）/ Init workspace dirs (memory, sessions, logs, skills)
    workspace = Path(config.workspace)
    if not workspace.is_absolute():
        workspace = ROOT_DIR / workspace
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    for sub in ["memory/core", "memory/episodic", "memory/semantic",
                "sessions", "logs/scheduler", "skills"]:
        (workspace / sub).mkdir(parents=True, exist_ok=True)

    if args.command == "cli":
        asyncio.run(run_cli(config))
    elif args.command == "gateway":
        print(f"🚀 MyAgent Gateway + Dashboard on http://127.0.0.1:{args.port}")
        asyncio.run(run_gateway(config, args.port))
    elif args.command == "status":
        agent = AgentOrchestrator(config)
        import json
        status = agent.get_status()
        print(json.dumps(status, indent=2, ensure_ascii=False))
    elif args.command == "tools":
        agent = AgentOrchestrator(config)
        print("🔧 Available Tools:")
        for t in agent.tools.list_tools():
            tool = agent.tools.get(t)
            schema = tool.get_schema()
            desc = schema["function"]["description"][:80]
            print(f"  • {t}: {desc}")
    elif args.command == "skills":
        agent = AgentOrchestrator(config)
        print(f"📦 {agent.get_status()['skills_count']} Skills loaded:")
        for name in sorted(agent.skills.keys()):
            skill = agent.skills[name]
            emoji = skill.meta.emoji or "📦"
            desc = skill.meta.description[:60]
            print(f"  {emoji} {name}: {desc}")


if __name__ == "__main__":
    main()
