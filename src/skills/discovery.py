"""技能发现器 — OpenClaw Skills Compatible 多层级技能加载 / Skill Discovery — OpenClaw Skills Compatible Multi-tier Loading"""

import platform
import shutil
import importlib.util
import logging
from pathlib import Path

from .parser import SkillParser, OpenClawSkill

logger = logging.getLogger(__name__)


class SkillDiscovery:
    """
    按优先级扫描技能目录，与 OpenClaw Skills Compatible 完全一致：
Scan skill directories by priority, fully OpenClaw Skills Compatible:
Scan skill directories by priority, fully OpenClaw Skills Compatible:
    1. Workspace skills (highest)
    2. Project agent skills
    3. Personal agent skills
    4. Managed/local skills
    5. Bundled skills (lowest)
    """

    def __init__(self, skill_roots: list[str] | None = None, extra_dirs: list[str] | None = None):
        self.parser = SkillParser()
        self.default_roots = [
            Path.home() / ".openclaw/workspace/skills",
            Path.home() / ".openclaw/workspace/.agents/skills",
            Path.home() / ".agents/skills",
            Path.home() / ".openclaw/skills",
            Path.home() / ".npm-global/lib/node_modules/openclaw/skills",
        ]
        self.skill_roots = [Path(p) for p in (skill_roots or [])]
        self.extra_dirs = [Path(d) for d in (extra_dirs or [])]

    def discover_all(self) -> dict[str, OpenClawSkill]:
        """发现所有可用技能 / Discover all available skills, higher priority overrides"""
        skills: dict[str, OpenClawSkill] = {}

        # 合并所有根目录 / Merge all roots: custom + default + extra dirs
        all_roots = self.skill_roots + self.default_roots + self.extra_dirs

        # 从低优先级到高优先级扫描（高优先级后覆盖）/ Scan low-to-high priority (high overrides)
        for root in reversed(all_roots):
            if not root.exists():
                continue
            count_before = len(skills)
            for skill_md in root.rglob("SKILL.md"):
                try:
                    skill = self.parser.parse(skill_md)
                    if self._is_eligible(skill):
                        skills[skill.name] = skill
                except Exception as e:
                    logger.warning(f"Failed to parse {skill_md}: {e}")
            count_after = len(skills)
            if count_after > count_before:
                logger.info(f"Loaded {count_after - count_before} skills from {root}")

        logger.info(f"Total {len(skills)} skills discovered")
        return skills

    def _is_eligible(self, skill: OpenClawSkill) -> bool:
        """检查技能是否满足运行条件 / Check if skill meets runtime requirements"""
        meta = skill.meta

        # 平台过滤 / Platform filter
        if meta.os_filter:
            # M-04: 修复 Windows 平台检测 / Fix Windows platform detection
            os_map = {"darwin": "macos", "linux": "linux", "windows": "windows"}
            current_os = os_map.get(platform.system().lower(), "")
            if current_os not in meta.os_filter:
                return False

        # 二进制依赖检查 / Binary dependency check
        for bin_name in meta.requires.bins:
            if not shutil.which(bin_name):
                return False

        # anyBins: at least one exists
        if meta.requires.anyBins:
            if not any(shutil.which(b) for b in meta.requires.anyBins):
                return False

        # pip 包检查 / pip package check
        for pkg_spec in meta.requires.pip:
            pkg_name = pkg_spec.split(">=")[0].split("==")[0].split("<")[0].split("[")[0].strip()
            if not importlib.util.find_spec(pkg_name.replace("-", "_")):
                # 也试试原始名称 / Also try original name
                if not importlib.util.find_spec(pkg_name):
                    return False

        return True
