"""记忆管理器 / Memory Manager — 统一管理四层记忆"""

import logging
from pathlib import Path

from .working import WorkingMemory
from .episodic import EpisodicMemory
from .semantic import SemanticMemory
from .user_model import UserModel

logger = logging.getLogger(__name__)


class MemoryManager:
    """四层记忆管理器 / 4-Tier Memory Manager"""
    
    def __init__(self, db_path: str, episodic_dir: str, core_dir: str, retention_days: int = 7):
        # L1: 工作记忆 / L1: Working memory（内存）/ L1: Working Memory (in-memory)
        self.working = WorkingMemory()
        
        # L2: 短期记忆（SQLite + FTS5）/ L2: Episodic (SQLite + FTS5)
        self.episodic = EpisodicMemory(db_path, retention_days)
        
        # L3: 长期语义记忆 / L3: Semantic Memory (M-05: added SemanticMemory)
        try:
            semantic_db = str(Path(db_path).parent / "semantic.db")
            self.semantic = SemanticMemory(semantic_db)
            logger.info("Memory Manager initialized (L1+L2+L3+L4)")
        except Exception as e:
            self.semantic = None
            logger.warning(f"SemanticMemory (L3) unavailable: {e}")
            logger.info("Memory Manager initialized (L1+L2+L4)")
        
        # L4: 用户模型（JSON）/ L4: User Model (JSON)
        self.user_model = UserModel(core_dir)
    
    def store_interaction(self, user_msg: str, assistant_msg: str, 
                          tools_used: list[str] | None = None,
                          task_type: str = "chat"):
        """存储一次交互 / Store an interaction"""
        # L1: 工作记忆 / L1: Working memory
        self.working.add("user", user_msg)
        self.working.add("assistant", assistant_msg)
        
        # L2: 短期记忆（存储摘要）/ L2: Episodic (store summaries)
        summary = assistant_msg[:200] if len(assistant_msg) > 200 else assistant_msg
        importance = self._assess_importance(user_msg, assistant_msg, tools_used)
        self.episodic.store(
            content=f"User: {user_msg[:100]}\nAssistant: {summary}",
            metadata={"task_type": task_type, "tools": tools_used or []},
            importance=importance,
        )
        
        # L4: 更新用户模式 / L4: Update user patterns
        if tools_used:
            self.user_model.update_patterns(task_type, tools_used)
    
    def get_context(self, current_message: str, max_chars: int = 3000) -> str:
        """构建上下文 / Build context: Working + Episodic + User Profile"""
        parts = []
        
        # 用户画像 / User profile
        parts.append(self.user_model.get_context_for_prompt())
        
        # 最近的短期记忆 / Recent episodic memories
        recent = self.episodic.get_recent(hours=24, limit=5)
        if recent:
            parts.append("## Recent Activity")
            for mem in recent:
                parts.append(f"- [{mem['timestamp'][:16]}] {mem['content'][:100]}")
        
        # 相关记忆搜索 / Related memory search
        try:
            related = self.episodic.search(current_message, limit=3)
            if related:
                parts.append("## Related Memories")
                for mem in related:
                    parts.append(f"- {mem['content'][:120]}")
        except Exception:
            pass
        
        context = "\n\n".join(parts)
        if len(context) > max_chars:
            context = context[:max_chars]
        
        return context
    
    def _assess_importance(self, user_msg: str, assistant_msg: str, 
                           tools_used: list | None) -> float:
        """评估记忆重要度 / Assess memory importance"""
        importance = 0.3
        
        # 有工具调用 → 更重要 / Tool calls → higher importance
        if tools_used and len(tools_used) > 0:
            importance += 0.2
        
        # 长回复 → 更重要 / Long replies → higher importance
        if len(assistant_msg) > 500:
            importance += 0.1
        
        # 包含关键词 / Contains keywords
        keywords = ["记住", "重要", "决定", "remember", "important", "分析", "报告"]
        for kw in keywords:
            if kw in user_msg.lower():
                importance += 0.15
                break
        
        return min(importance, 1.0)
    
    def get_working_messages(self) -> list[dict]:
        """获取工作记忆消息列表 / Get working memory messages (for LLM conversation)"""
        return self.working.messages.copy()
