"""子代理框架 / Sub-Agent Framework — spawn + parallel execution + result aggregation"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional

from ..llm import LLMRouter

logger = logging.getLogger(__name__)


@dataclass
class SubAgentResult:
    """子代理执行结果 / Sub-Agent Execution Result"""
    task_id: str
    task: str
    result: str
    success: bool = True
    tools_used: list[str] = field(default_factory=list)
    error: str = ""


class SubAgent:
    """子代理 / Sub-Agent — Independent lightweight Agent for specific sub-tasks"""

    def __init__(self, llm: LLMRouter, tools_registry=None, model: str = ""):
        self.llm = llm
        self.tools = tools_registry
        self.model = model

    async def execute(self, task: str, context: str = "") -> SubAgentResult:
        """执行子任务 / Execute sub-task"""
        task_id = str(uuid.uuid4())[:8]

        system = f"""You are a specialized sub-agent executing a specific task.
Focus only on the assigned task. Be concise and return results directly.
{context}"""

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": task},
        ]

        tool_schemas = self.tools.get_schemas() if self.tools else None
        tools_used = []

        for iteration in range(5):  # 子代理最多5轮 / Sub-agent max 5 rounds
            try:
                response = await self.llm.chat(
                    messages=messages,
                    tools=tool_schemas,
                    model=self.model or None,
                )
            except Exception as e:
                return SubAgentResult(
                    task_id=task_id, task=task, result="",
                    success=False, error=str(e),
                )

            if not response.tool_calls:
                return SubAgentResult(
                    task_id=task_id, task=task,
                    result=response.content,
                    tools_used=tools_used,
                )

            # 执行工具 / Execute tool
            assistant_msg = {"role": "assistant", "content": response.content or ""}
            # H-16: 安全序列化 arguments / H-16: Safe serialize arguments
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id, "type": "function",
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

            for tc in response.tool_calls:
                tools_used.append(tc.name)
                # H-13: 检查 self.tools 是否可用 / Check if self.tools is available
                if not self.tools:
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": f"Error: tool registry not available",
                    })
                    continue
                # H-16: 确保 arguments 是 dict / Ensure arguments is dict
                # V8-M10: 字符串参数尝试 JSON 解析 / Try JSON parse for string params, not silent drop
                args = tc.arguments if isinstance(tc.arguments, dict) else {}
                if isinstance(tc.arguments, str):
                    try:
                        args = json.loads(tc.arguments)
                    except json.JSONDecodeError:
                        args = {}
                result = await self.tools.execute(tc.name, **args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result.to_text(),
                })

        return SubAgentResult(
            task_id=task_id, task=task,
            result="Max iterations reached",
            success=False, tools_used=tools_used,
        )


class MultiAgentOrchestrator:
    """多代理编排器 / Multi-Agent Orchestrator — Decompose + Parallel + Aggregate"""

    def __init__(self, llm: LLMRouter, tools_registry=None, model: str = ""):
        self.llm = llm
        self.tools = tools_registry
        self.model = model

    async def decompose(self, task: str) -> list[str]:
        """将复杂任务分解为子任务列表 / Decompose complex task into sub-task list"""
        response = await self.llm.chat(
            messages=[
                {"role": "system", "content": """You are a task decomposition engine.
Break down the given task into 2-5 independent sub-tasks that can be executed in parallel.
Return ONLY a JSON array of strings, each being a sub-task description.
Example: ["Sub-task 1 description", "Sub-task 2 description"]"""},
                {"role": "user", "content": task},
            ],
        )

        try:
            # M-07: 健壮 JSON 解析 / Robust JSON parsing
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()
            # 提取 JSON 数组 / Extract JSON array
            start = content.find('[')
            end = content.rfind(']')
            if start != -1 and end != -1 and end > start:
                content = content[start:end+1]
            subtasks = json.loads(content)
            if isinstance(subtasks, list):
                return [str(t) for t in subtasks]
        except (json.JSONDecodeError, IndexError) as e:
            logger.warning(f"Failed to parse subtask JSON: {e}")
            pass

        # 降级：返回原任务 / Fallback: return original task
        return [task]

    async def execute_parallel(self, subtasks: list[str]) -> list[SubAgentResult]:
        """并行执行多个子任务 / Execute sub-tasks in parallel (L-14: independent instances)"""
        tasks = []
        for task in subtasks:
            agent = SubAgent(self.llm, self.tools, self.model)
            tasks.append(agent.execute(task))
        results = await asyncio.gather(*tasks, return_exceptions=True)

        final = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                final.append(SubAgentResult(
                    task_id=str(uuid.uuid4())[:8],
                    task=subtasks[i],
                    result="",
                    success=False,
                    error=str(r),
                ))
            else:
                final.append(r)

        return final

    async def execute_complex(self, task: str) -> str:
        """完整的多代理流程 / Full multi-agent flow: Decompose → Parallel → Aggregate"""
        logger.info(f"Multi-agent task: {task[:100]}")

        # 1. 分解 / 1. Decompose
        subtasks = await self.decompose(task)
        logger.info(f"Decomposed into {len(subtasks)} sub-tasks")

        # 2. 并行执行 / 2. Parallel execution
        results = await self.execute_parallel(subtasks)

        # 3. 聚合 / 3. Aggregate
        if len(results) == 1:
            return results[0].result

        # 用 LLM 汇总 / Summarize with LLM
        summaries = []
        for r in results:
            status = "✅" if r.success else "❌"
            summaries.append(f"{status} {r.task}: {r.result[:500]}")

        response = await self.llm.chat(
            messages=[
                {"role": "system", "content": "You are a result aggregator. Combine the following sub-task results into a coherent, comprehensive response."},
                {"role": "user", "content": f"Original task: {task}\n\nSub-task results:\n" + "\n\n".join(summaries)},
            ],
        )

        return response.content
