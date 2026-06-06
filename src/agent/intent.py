"""意图识别模块 / Intent Recognition Module

基于关键词匹配的轻量级意图分类器。
Lightweight keyword-based intent classifier.
Lightweight intent classifier based on keyword matching.
在 LLM 调用前执行，用于快速路由和上下文提示。
Executed before LLM calls for fast routing and context hints.
"""

import logging

logger = logging.getLogger(__name__)

# 意图分类映射 — 关键词到意图类型的映射表 / Intent mapping — keyword to intent type lookup table
INTENT_MAP = {
    "email": ["邮件", "email", "mail", "收件箱", "inbox", "发送邮件", "读取邮件"],
    "calendar": ["日程", "日历", "calendar", "会议", "安排", "提醒"],
    "weather": ["天气", "weather", "温度", "下雨"],
    "search": ["搜索", "search", "查找", "查询", "找一下"],
    "translate": ["翻译", "translate", "英文", "中文", "阿拉伯"],
    "data_analysis": ["分析", "数据", "CSV", "Excel", "统计"],
    "news": ["新闻", "news", "资讯", "头条"],
    "finance": ["股票", "汇率", "油价", "黄金", "财经"],
    "file": ["文件", "读取", "写入", "编辑"],
    "chat": [],  # 默认 / default
}


def classify_intent(text: str) -> dict:
    """
    简单关键词意图识别 / Simple keyword-based intent recognition

    通过匹配预定义关键词表，判断用户消息的意图类型。支持中英文关键词混合匹配。
Matches predefined keyword tables to classify user message intent. Supports CN/EN mixed keywords.
    Matches predefined keyword tables to determine user message intent. Supports mixed CN/EN keywords.

    Args:
        text: 用户输入文本 / User input text

    Returns:
        {"type": str, "confidence": float, "keywords_matched": list}
        type: 意图类型 / Intent type (email/calendar/weather/search/translate/...)
        confidence: 0.0-1.0，匹配关键词越多越高 / Higher with more matched keywords
        keywords_matched: 匹配到的关键词列表 / List of matched keywords
    """
    text_lower = text.lower()
    
    best_intent = "chat"
    best_score = 0
    matched = []
    
    for intent, keywords in INTENT_MAP.items():
        if not keywords:
            continue
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > best_score:
            best_score = score
            best_intent = intent
            matched = [kw for kw in keywords if kw in text_lower]
    
    confidence = min(best_score / 3.0, 1.0) if best_score > 0 else 0.3
    
    return {
        "type": best_intent,
        "confidence": confidence,
        "keywords_matched": matched,
    }
