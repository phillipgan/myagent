"""记忆巩固器 / Memory Consolidator — Promote L2 to L3 / Memory Consolidator — Promote L2 episodic to L3 semantic

定期扫描 L2 中高重要性条目，用 LLM 生成摘要。
Periodically scans L2 for high-importance entries, uses LLM for summaries.
Periodically scans L2 for high-importance entries, uses LLM to generate summaries and extract key facts,
然后存入 L3 语义记忆层。
Then stores in L3 semantic memory. Also generates embedding vectors.
then stores in L3 semantic memory. Also generates embedding vectors for similarity search.

触发方式：由 CronScheduler 定时调用。
Trigger: called periodically by CronScheduler, or after each conversation.
Trigger: called periodically by CronScheduler, or checked after each conversation.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from .episodic import EpisodicMemory
from .semantic import SemanticMemory

logger = logging.getLogger(__name__)


class MemoryConsolidator:
    """记忆巩固器 — 定期将重要短期记忆提升到长期存储 / Consolidator — periodically promotes important short-term memories to long-term storage"""
    
    def __init__(self, episodic: EpisodicMemory, semantic: SemanticMemory, llm_router=None):
        self.episodic = episodic
        self.semantic = semantic
        self.llm = llm_router
    
    async def consolidate(self, importance_threshold: float = 0.6):
        """执行记忆巩固 / Perform memory consolidation"""
        # V8-M19: semantic 为 None 时无法巩固，直接返回 / Cannot consolidate when semantic is None
        if self.semantic is None:
            logger.warning("SemanticMemory (L3) not available, skipping consolidation")
            return 0

        # 1. 获取短期记忆中值得巩固的条目 / 1. Get consolidation candidates from episodic
        candidates = self.episodic.get_consolidation_candidates(importance_threshold)
        
        if not candidates:
            logger.info("No consolidation candidates")
            return 0
        
        consolidated = 0
        for mem in candidates:
            # 2. 用 LLM 生成摘要（如果可用）/ 2. Summarize via LLM (if available)
            summary = await self._summarize(mem["content"]) if self.llm else mem["content"][:100]
            
            # 3. 存入长期记忆 / 3. Store in long-term memory
            self.semantic.store(
                content=mem["content"],
                summary=summary,
                metadata=mem.get("metadata", {}),
                importance=mem["importance"],
            )
            consolidated += 1
        
        # 4. 清理已巩固的短期记忆（降低重要度）/ 4. Demote consolidated memories / Don't delete; let natural expiry handle it
        # 不直接删除，让自然过期机制处理 / Don't delete; let natural expiry handle it
        
        logger.info(f"Consolidated {consolidated} memories to long-term storage")
        return consolidated
    
    async def _summarize(self, content: str) -> str:
        """用 LLM 生成记忆摘要 / Generate memory summary via LLM"""
        if not self.llm:
            return content[:100]
        
        try:
            response = await self.llm.chat(
                messages=[
                    {"role": "system", "content": "Summarize the following memory in one concise sentence. Preserve key facts, names, and numbers."},
                    {"role": "user", "content": content},
                ],
                model="zai/glm-5.1",
            )
            return response.content[:200]
        except Exception:
            return content[:100]
    
    async def update_user_model(self, user_model, recent_memories: list[dict]):
        """根据近期记忆更新用户模型 / Update user model based on recent memories"""
        if not self.llm or not recent_memories:
            return
        
        # 提取任务类型和工具使用模式 / Extract task types and tool usage patterns
        task_types = []
        tools_used = []
        for mem in recent_memories:
            meta = mem.get("metadata", {})
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}
            if meta.get("task_type"):
                task_types.append(meta["task_type"])
            if meta.get("tools"):
                tools_used.extend(meta["tools"])
        
        if task_types:
            patterns = user_model.get("work_patterns", {})
            freq = patterns.get("frequent_tasks", [])
            for t in task_types:
                if t not in freq:
                    freq.append(t)
            patterns["frequent_tasks"] = freq[-20:]
            user_model.set("work_patterns", patterns)
