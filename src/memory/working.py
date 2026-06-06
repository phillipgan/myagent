"""L1 工作记忆 / L1 Working Memory — 当前会话的对话缓冲区"""

from dataclasses import dataclass, field


@dataclass
class WorkingMemory:
    """工作记忆 / Working Memory — Current conversation context (in-memory)"""
    
    messages: list[dict] = field(default_factory=list)
    max_messages: int = 40  # 保留最近40条消息 / Keep last 40 messages
    
    def add(self, role: str, content: str, **meta):
        """添加消息 / Add message"""
        msg = {"role": role, "content": content}
        msg.update(meta)
        self.messages.append(msg)
        
        # 保持窗口大小 / Maintain window size
        if len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages:]
    
    def get_recent(self, n: int = 10) -> list[dict]:
        """获取最近n条消息 / Get last n messages"""
        return self.messages[-n:]
    
    def get_context(self, max_chars: int = 4000) -> list[dict]:
        """获取适合注入 prompt 的上下文 / Get context suitable for prompt injection"""
        result = []
        total = 0
        for msg in reversed(self.messages):
            total += len(msg.get("content", ""))
            if total > max_chars:
                break
            result.insert(0, msg)
        return result
    
    def clear(self):
        """清空 / Clear"""
        self.messages.clear()
