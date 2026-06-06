"""技能注册表 / Skill Registry — Metadata, search and recommendation"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SkillRegistry:
    """技能注册表 / Skill Registry — search, categorize, recommend"""

    def __init__(self):
        self._skills: dict = {}  # name -> SkillDefinition

    def register(self, name: str, skill_definition):
        """注册技能 / Register skill"""
        self._skills[name] = skill_definition

    def get(self, name: str):
        """获取技能 / Get skill"""
        return self._skills.get(name)

    def list_all(self) -> list[str]:
        """列出所有技能名 / List all skill names"""
        return sorted(self._skills.keys())

    def count(self) -> int:
        return len(self._skills)

    def search(self, query: str, limit: int = 10) -> list[dict]:
        """关键词搜索技能 / Keyword search skills"""
        query_lower = query.lower()
        results = []
        for name, skill in self._skills.items():
            meta = skill.meta
            score = 0

            # 名称匹配 / Name match
            if query_lower in name.lower():
                score += 10

            # 描述匹配 / Description match
            desc = (meta.description or "").lower()
            if query_lower in desc:
                score += 5

            if score > 0:
                results.append({
                    "name": name,
                    "description": meta.description or "",
                    "emoji": meta.emoji or "📦",
                    "score": score,
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def by_category(self) -> dict[str, list[str]]:
        """按分类列出技能 / List skills by category"""
        cats = {}
        for name, skill in self._skills.items():
            cat = getattr(skill.meta, "category", "other") or "other"
            cats.setdefault(cat, []).append(name)
        return cats

    def recommend(self, context: str, limit: int = 5) -> list[dict]:
        """根据上下文推荐技能 / Recommend skills by context"""
        return self.search(context, limit)
