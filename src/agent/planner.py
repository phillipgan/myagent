"""任务分解与规划 / Task Decomposition and Planning

TaskPlanner 利用 LLM 将复杂任务拆分为 2-5 个可执行的子步骤，
TaskPlanner uses LLM to decompose complex tasks into 2-5 executable sub-steps,
每个子步骤指定要使用的工具和参数。
Each sub-step specifies tools and parameters.
用于处理多步骤复杂任务（如"搜索 X 并发邮件给 Y"）。
Used for multi-step complex tasks (e.g., "search X and email Y").
"""

import json
import logging

logger = logging.getLogger(__name__)


class TaskPlanner:
    """任务分解器 / Task Decomposer — Break complex tasks into executable sub-steps"""
    
    def __init__(self, llm_router=None):
        self.llm = llm_router
    
    async def decompose(self, task: str) -> list[dict]:
        """
        分解任务为子步骤
Decompose task into sub-steps

        调用 LLM 分析任务，返回结构化的执行计划。
Calls LLM to analyze task, returns structured execution plan.
        如果 LLM 不可用或解析失败，返回单步骤回退方案。
If LLM unavailable or parsing fails, returns single-step fallback.

        Returns:
            [{"step": int, "description": str, "tool": str, "params": dict}]
        """
        if not self.llm:
            return [{"step": 1, "description": task, "tool": "auto", "params": {}}]
        
        response = await self.llm.chat(
            messages=[
                {"role": "system", "content": """Decompose this task into 2-5 executable steps.
Each step should specify which tool to use: exec, read, write, edit, web_search, web_fetch, email_read, email_send, calendar, data_analysis.
Return ONLY a JSON array: [{"step":1,"description":"...","tool":"...","params":{}}]"""},
                {"role": "user", "content": task},
            ],
        )
        
        try:
            content = response.content.strip()
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()
            # M-07: 提取 JSON 数组 / Extract JSON array (handle LLM adding text around JSON)
            start = content.find('[')
            end = content.rfind(']')
            if start != -1 and end != -1 and end > start:
                content = content[start:end+1]
            return json.loads(content)
        except (json.JSONDecodeError, IndexError) as e:
            logger.warning(f"Failed to parse plan JSON: {e}")
            return [{"step": 1, "description": task, "tool": "auto", "params": {}}]
    
    async def should_decompose(self, task: str) -> bool:
        """判断任务是否需要分解 / Check if task needs decomposition — detect multi-step indicators ("then"/"analyze"/"report")"""
        complex_indicators = [
            "然后", "并且", "之后", "同时", "and then", "also", "after that",
            "分析", "报告", "研究", "比较", "汇总", "analyze", "report", "compare",
        ]
        return any(ind in task.lower() for ind in complex_indicators)
