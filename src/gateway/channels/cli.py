"""CLI 通道 — Rich TUI 交互界面 / CLI Channel — Rich TUI Interface"""

import asyncio
import logging
from typing import AsyncIterator

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

logger = logging.getLogger(__name__)


class CLIChannel:
    """命令行交互通道 / CLI Interactive Channel"""

    def __init__(self):
        self.console = Console()
        self.session = PromptSession(history=InMemoryHistory())
        self.conversation_history: list[dict] = []

    def print_banner(self, status: dict):
        """打印启动横幅 / Print startup banner"""
        banner = Text()
        banner.append("🤖 ", style="bold")
        banner.append(status["name"], style="bold blue")
        banner.append(" — Personal Office Assistant\n", style="dim")
        banner.append(f"   Skills: {status['skills_count']} loaded", style="green")
        banner.append(f"  |  Tools: {len(status['tools'])}", style="green")
        banner.append(f"  |  Model: {status['model_default']}\n", style="dim")
        banner.append("   Type your message (Ctrl+D or 'quit' to exit)", style="dim")

        self.console.print(Panel(banner, border_style="blue", padding=(1, 2)))

    async def run(self, orchestrator):
        """运行 CLI 交互循环 / Run CLI interaction loop"""
        status = orchestrator.get_status()
        self.print_banner(status)

        # 显示已加载的技能 / Show loaded skills
        if status["skills"]:
            skill_names = ", ".join(
                f"{s}" for s in sorted(status["skills"])[:20]
            )
            if len(status["skills"]) > 20:
                skill_names += f" ... (+{len(status['skills']) - 20} more)"
            self.console.print(f"   📦 Loaded skills: {skill_names}\n", style="dim")

        while True:
            try:
                # 获取用户输入 / Get user input
                user_input = await asyncio.to_thread(
                    self.session.prompt, "💬 > "
                )
                user_input = user_input.strip()

                if not user_input:
                    continue

                if user_input.lower() in ("quit", "exit", "q"):
                    self.console.print("👋 Bye!", style="bold blue")
                    break

                if user_input == "/status":
                    self.console.print_json(data=orchestrator.get_status())
                    continue

                if user_input == "/skills":
                    for name, skill in orchestrator.skills.items():
                        desc = skill.meta.description[:60]
                        self.console.print(f"  • {skill.meta.emoji} {name}: {desc}", style="dim")
                    continue

                # 处理消息 / Process message
                self.console.print()

                full_response = ""
                async for event in orchestrator.process_message(
                    user_input, self.conversation_history
                ):
                    if event["type"] == "tool_start":
                        args_str = str(event.get("args", {}))[:80]
                        self.console.print(
                            f"  🔧 {event['name']}({args_str}...)",
                            style="dim yellow",
                        )

                    elif event["type"] == "tool_result":
                        result_str = event["result"][:200].replace("\n", " ")
                        style = "dim green" if event.get("success", True) else "dim red"
                        self.console.print(f"  📋 {result_str}", style=style)

                    elif event["type"] == "text":
                        full_response = event["content"]

                # 打印最终回复 / Print final reply
                if full_response:
                    self.console.print()
                    self.console.print(Markdown(full_response))
                    self.console.print()

                    # 保存对话历史 / Save conversation history
                    self.conversation_history.append({"role": "user", "content": user_input})
                    self.conversation_history.append({"role": "assistant", "content": full_response})
                    # M-03: 限制对话历史大小 / Limit conversation history size
                    if len(self.conversation_history) > 100:
                        self.conversation_history = self.conversation_history[-60:]

            except KeyboardInterrupt:
                continue
            except EOFError:
                self.console.print("\n👋 Bye!", style="bold blue")
                break
            except Exception as e:
                self.console.print(f"❌ Error: {e}", style="bold red")
                logger.exception("CLI error")
