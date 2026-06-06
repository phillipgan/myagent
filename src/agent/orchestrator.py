"""Agent 核心编排器 / Agent Core Orchestrator — ReAct Loop + Memory + OpenClaw Skills Compatible"""

import json
import logging
from pathlib import Path
from typing import AsyncGenerator

from ..config import AgentConfig
from ..llm import LLMRouter
from ..skills import SkillDiscovery, SkillExecutor, LearningLoop
from ..skills.registry import SkillRegistry
from ..tools import ToolRegistry
from ..memory import MemoryManager

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """You are {name}, a personal office assistant AI agent built with Python.
You are compatible with OpenClaw Skills format and can use various tools.

## Core Tools
- exec: Execute shell commands
- read: Read file contents
- write: Write files
- edit: Make precise file edits
- web_search: Search the web
- web_fetch: Fetch web page content

## Rules
- Be concise, professional, and helpful
- Use tools when needed
- Respond in the user's language (Chinese for Chinese input, English for English)
- For weather, use exec to run: curl -s "wttr.in/City?format=3"
- For system info, use exec to run appropriate commands

## Cross-Platform Compatibility
- Detect the OS before running platform-specific commands
- On Windows: use 'type' instead of 'cat', 'findstr' instead of 'grep', 'dir' instead of 'ls'
- On Windows: use 'NUL' instead of '/dev/null', no 'head'/'tail'/'wc' commands
- On Windows: avoid pipes with Unix-only commands; PowerShell can be used as fallback
- Prefer cross-platform commands when possible (curl, python, git work on both)

{user_context}

{skill_catalog}
"""


class AgentOrchestrator:
    """Agent 核心编排器 / Agent Core Orchestrator"""

    def __init__(self, config: AgentConfig):
        self.config = config
        self.llm = LLMRouter(config)
        self.tools = ToolRegistry(llm_router=self.llm)
        self.memory = MemoryManager(
            db_path=config.memory.db_path,
            episodic_dir=config.memory.episodic_dir,
            core_dir=config.memory.core_dir,
            retention_days=config.memory.retention_days,
        )
        self.skill_discovery = SkillDiscovery(
            skill_roots=config.skill.roots,
        )
        self.skill_executor = SkillExecutor()

        # 自学习 / Self-learning
        skill_output = str(Path(config.workspace) / "skills")
        self.learner = LearningLoop(skill_output, llm_router=self.llm)

        # 发现并缓存技能 / Discover and cache skills
        self.skills = self.skill_discovery.discover_all()
        # L-04: 使用 SkillRegistry 管理技能元数据 / Use SkillRegistry for skill metadata
        self.skill_registry = SkillRegistry()
        for name, skill in self.skills.items():
            self.skill_registry.register(name, skill)
        logger.info(f"Agent initialized with {len(self.skills)} skills, {len(self.tools.list_tools())} tools, memory + learning enabled")

    def _build_system_prompt(self) -> str:
        """构建 system prompt / Build system prompt"""
        skill_catalog = self.skill_executor.build_skill_catalog(self.skills)
        user_context = self.memory.user_model.get_context_for_prompt()
        return SYSTEM_PROMPT_TEMPLATE.format(
            name=self.config.name,
            user_context=user_context,
            skill_catalog=skill_catalog,
        )

    async def process_message(
        self,
        user_message: str,
        conversation_history: list | None = None,
    ) -> AsyncGenerator[dict, None]:
        """处理用户消息 / Process user message — ReAct Loop + Memory"""
        system_prompt = self._build_system_prompt()
        tool_schemas = self.tools.get_schemas()

        # 获取记忆上下文 / Get memory context
        memory_context = self.memory.get_context(user_message)

        # 构建消息列表 — V8-M09 / Build message list — merge into single system message
        system_content = system_prompt
        if memory_context:
            system_content += "\n\n" + memory_context
        messages = [{"role": "system", "content": system_content}]

        # 对话历史：优先使用 CLI 传入的，否则从工作记忆获取 / Conversation history: prefer CLI input, fallback to working memory
        if conversation_history:
            messages.extend(conversation_history[-20:])
        else:
            working = self.memory.get_working_messages()
            if working:
                messages.extend(working[-20:])

        messages.append({"role": "user", "content": user_message})

        # 记录使用的工具 / Record tools used
        tools_used = []
        # L-12: ReAct 总超时保护 / L-12: ReAct total timeout protection
        import time as _time
        _loop_start = _time.monotonic()
        _loop_timeout = self.config.max_iterations * self.config.default_timeout

        # ReAct 循环 / ReAct loop
        for iteration in range(self.config.max_iterations):
            logger.debug(f"ReAct iteration {iteration + 1}")

            # L-12: 检查总超时 / L-12: Check total timeout
            if _time.monotonic() - _loop_start > _loop_timeout:
                logger.warning(f"ReAct total timeout exceeded ({_loop_timeout}s)")
                tools_str = ", ".join(tools_used) if tools_used else "none"
                yield {"type": "text", "content": f"Task timed out after {_loop_timeout}s. Tools used: {tools_str}"}
                return

            try:
                response = await self.llm.chat(
                    messages=messages,
                    tools=tool_schemas if tool_schemas else None,
                )
            except Exception as e:
                logger.error(f"LLM error: {e}")
                yield {"type": "text", "content": f"抱歉，模型调用出错：{e}"}
                return

            if not response.tool_calls:
                # 存储到记忆 / Store to memory
                self.memory.store_interaction(
                    user_message, response.content,
                    tools_used=tools_used,
                )
                # 触发学习 / Trigger learning
                tool_call_records = [{"name": t} for t in tools_used]
                await self.learner.on_task_complete(
                    user_message, tool_call_records, response.content
                )
                yield {"type": "text", "content": response.content}
                return

            # Assistant 消息 / Assistant message
            # H-16: 安全序列化 arguments / H-16: Safe serialize arguments / Safe serialize arguments (handle string params)
            assistant_msg = {"role": "assistant", "content": response.content or ""}
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": (
                            json.dumps(tc.arguments, ensure_ascii=False)
                            if isinstance(tc.arguments, dict)
                            else str(tc.arguments)
                        ),
                    },
                }
                for tc in response.tool_calls
            ]
            messages.append(assistant_msg)

            # 执行工具 / Execute tool
            for tc in response.tool_calls:
                tools_used.append(tc.name)
                yield {"type": "tool_start", "name": tc.name, "args": tc.arguments}

                result = await self.tools.execute(tc.name, **tc.arguments)

                yield {
                    "type": "tool_result",
                    "name": tc.name,
                    "result": result.to_text(),
                    "success": result.success,
                }

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result.to_text(),
                })

        # 达到最大迭代 — 尝试让 LLM 给出中间总结 / Max iterations reached — ask LLM for intermediate summary
        logger.warning(f"ReAct loop exhausted after {self.config.max_iterations} iterations, requesting summary")
        summary_messages = messages + [
            {
                "role": "user",
                "content": (
                    f"[系统提示] 你已经进行了 {self.config.max_iterations} 轮工具调用，"
                    "请根据目前收集到的信息，给出一个完整的回复。"
                    "如果任务未完成，说明已完成的部分和剩余步骤。"
                ),
            }
        ]
        try:
            summary_response = await self.llm.chat(messages=summary_messages, tools=None)
            self.memory.store_interaction(user_message, summary_response.content, tools_used=tools_used)
            yield {"type": "text", "content": summary_response.content}
        except Exception as e:
            logger.error(f"Summary generation failed: {e}")
            yield {
                "type": "text",
                "content": (
                    f"⚠️ 任务进行了 {self.config.max_iterations} 轮工具调用后达到了步数上限。\n"
                    f"已使用工具：{', '.join(tools_used) or '无'}\n"
                    "回复 \"继续\" 我会从当前进度继续执行。"
                ),
            }

    def get_status(self) -> dict:
        """获取 Agent 状态 / Get Agent status"""
        return {
            "name": self.config.name,
            "skills_count": len(self.skills),
            "skills": list(self.skills.keys()),
            "tools": self.tools.list_tools(),
            "model_default": self.config.model.default,
            "memory": {
                "working_messages": len(self.memory.working.messages),
                "user_name": self.memory.user_model.get("name"),
            },
        }
