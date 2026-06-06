"""技能执行器 — 将 SKILL.md 指令转化为 Agent 可用的 prompt / Skill Executor — Convert SKILL.md to Agent-usable prompts"""

import logging
from .parser import OpenClawSkill

logger = logging.getLogger(__name__)

# 技能摘要最大注入数量 / Max skills injected into prompt
MAX_SKILLS_IN_PROMPT = 50


class SkillExecutor:
    """
    OpenClaw Skills Compatible 技能执行器
OpenClaw Skills Compatible Executor

    策略：
Strategy:
    - System prompt 只注入技能摘要 / Inject only skill summaries (name+desc) into system prompt
    - 按需加载完整指令 / Load full instructions on demand when LLM needs a skill
    """

    def build_skill_catalog(self, skills: dict[str, OpenClawSkill]) -> str:
        """构建技能目录 / Build skill catalog — name+desc only for system prompt"""
        if not skills:
            return ""

        lines = ["## Available Skills\n"]
        lines.append("The following skills are available. When a user request matches a skill, "
                      "use the corresponding tools to execute it.\n")

        count = 0
        for name, skill in sorted(skills.items()):
            if skill.meta.disable_model_invocation:
                continue
            emoji = skill.meta.emoji or "📦"
            desc = skill.meta.description[:80]
            lines.append(f"- **{emoji} {name}**: {desc}")
            count += 1
            if count >= MAX_SKILLS_IN_PROMPT:
                remaining = len(skills) - count
                if remaining > 0:
                    lines.append(f"\n... and {remaining} more skills")
                break

        return "\n".join(lines)

    def get_skill_prompt(self, skill: OpenClawSkill) -> str:
        """按需获取某个技能的完整指令 / Get full skill instructions on demand"""
        instructions = skill.instructions.replace(
            "{baseDir}", str(skill.skill_dir)
        )
        if not instructions:
            return f"# Skill: {skill.name}\n{skill.meta.description}"

        return f"# Skill: {skill.name}\n{skill.meta.description}\n\n{instructions}"

    def find_matching_skills(self, query: str, skills: dict[str, OpenClawSkill]) -> list[OpenClawSkill]:
        """简单关键词匹配 / Simple keyword matching for related skills"""
        query_lower = query.lower()
        matches = []
        for name, skill in skills.items():
            # 检查名称、描述、关键词 / Check name, description, keywords
            searchable = f"{name} {skill.meta.description}".lower()
            if any(word in searchable for word in query_lower.split()):
                matches.append(skill)
        return matches

    def get_skill_summary(self, skills: dict[str, OpenClawSkill]) -> list[dict]:
        """获取技能摘要列表 / Get skill summary list"""
        summaries = []
        for name, skill in skills.items():
            summaries.append({
                "name": name,
                "description": skill.meta.description,
                "emoji": skill.meta.emoji,
                "source": skill.source,
                "tool_name": skill.tool_name,
            })
        return summaries
