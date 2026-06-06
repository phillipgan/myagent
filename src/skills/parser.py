"""OpenClaw Skills Compatible SKILL.md 解析器 / OpenClaw Skills Compatible SKILL.md Parser — 100% agentskills.io compatible"""

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

import yaml


@dataclass
class SkillDependency:
    """技能依赖 / Skill Dependencies"""
    bins: list[str] = field(default_factory=list)
    anyBins: list[str] = field(default_factory=list)
    env: list[str] = field(default_factory=list)
    config: list[str] = field(default_factory=list)
    pip: list[str] = field(default_factory=list)


@dataclass
class SkillMeta:
    """技能元数据 / Skill Metadata"""
    name: str = ""
    description: str = ""
    homepage: Optional[str] = None
    user_invocable: bool = True
    disable_model_invocation: bool = False
    command_dispatch: Optional[str] = None
    command_tool: Optional[str] = None
    emoji: str = ""
    os_filter: list[str] = field(default_factory=list)
    requires: SkillDependency = field(default_factory=SkillDependency)
    install: list[dict] = field(default_factory=list)
    primary_env: Optional[str] = None


@dataclass
class OpenClawSkill:
    """完整的 OpenClaw Skills Compatible 技能对象 / Complete OpenClaw Skills Compatible Skill Object"""
    meta: SkillMeta
    instructions: str
    skill_dir: Path
    source: str = ""

    @property
    def name(self) -> str:
        return self.meta.name

    @property
    def tool_name(self) -> str:
        return self.meta.name.replace("-", "_")


class SkillParser:
    """SKILL.md 解析器 / SKILL.md Parser"""

    def parse(self, skill_md_path: Path) -> OpenClawSkill:
        """解析 SKILL.md 文件 / Parse SKILL.md file"""
        content = skill_md_path.read_text(encoding="utf-8")

        # 分离 YAML frontmatter 和 Markdown body / Split YAML frontmatter and Markdown body
        frontmatter_str, instructions = self._split_frontmatter(content)

        fm = yaml.safe_load(frontmatter_str) if frontmatter_str else {}

        # 解析 metadata（支持 openclaw 和 clawdbot 格式）/ Parse metadata (supports openclaw and clawdbot formats)
        raw_meta = fm.get("metadata", {})
        oc_meta = raw_meta.get("openclaw", raw_meta.get("clawdbot", {}))

        requires_data = oc_meta.get("requires", {})
        requires = SkillDependency(
            bins=requires_data.get("bins", []),
            anyBins=requires_data.get("anyBins", []),
            env=requires_data.get("env", []),
            config=requires_data.get("config", []),
            pip=requires_data.get("pip", []),
        )

        meta = SkillMeta(
            name=fm.get("name", skill_md_path.parent.name),
            description=fm.get("description", ""),
            homepage=fm.get("homepage") or oc_meta.get("homepage"),
            user_invocable=fm.get("user-invocable", True),
            disable_model_invocation=fm.get("disable-model-invocation", False),
            command_dispatch=fm.get("command-dispatch"),
            command_tool=fm.get("command-tool"),
            emoji=oc_meta.get("emoji", ""),
            os_filter=oc_meta.get("os", []),
            requires=requires,
            install=oc_meta.get("install", []),
            primary_env=oc_meta.get("primaryEnv"),
        )

        return OpenClawSkill(
            meta=meta,
            instructions=instructions,
            skill_dir=skill_md_path.parent,
            source=self._detect_source(skill_md_path),
        )

    def _split_frontmatter(self, content: str) -> tuple[str, str]:
        """分离 YAML frontmatter 和 Markdown body / Split YAML frontmatter and Markdown body"""
        if not content.startswith("---"):
            return "", content

        # 找到第二个 --- / Find second ---
        end = content.find("---", 3)
        if end == -1:
            return "", content

        frontmatter = content[3:end].strip()
        body = content[end + 3:].strip()
        return frontmatter, body

    def _detect_source(self, path: Path) -> str:
        path_str = str(path)
        if "/workspace/skills/" in path_str:
            return "workspace"
        elif "/.openclaw/skills/" in path_str:
            return "managed"
        elif "/.agents/skills/" in path_str:
            return "personal"
        return "bundled"

    def extract_code_blocks(self, markdown: str) -> list[dict]:
        """提取 Markdown 中的代码块 / Extract code blocks from Markdown"""
        pattern = r'```(\w*)\n(.*?)```'
        blocks = []
        for match in re.finditer(pattern, markdown, re.DOTALL):
            blocks.append({
                "language": match.group(1) or "bash",
                "code": match.group(2).strip()
            })
        return blocks
