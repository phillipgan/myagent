"""自学习循环 — 从复杂任务中自动提炼 SKILL.md / Learning Loop — Auto-extract SKILL.md from complex tasks"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

SKILL_EXTRACTION_PROMPT = """You are a skill extraction engine. Analyze the following task execution and create an OpenClaw Skills Compatible SKILL.md file.

## Task
{task}

## Steps Taken
{steps}

## Outcome
{outcome}

## Requirements
Generate a SKILL.md file with:
1. YAML frontmatter (name, description, metadata with openclaw requires)
2. Clear step-by-step instructions in Markdown
3. Bash/Python code blocks where appropriate
4. The skill should be reusable for similar tasks

Output ONLY the SKILL.md content, starting with ---"""


class LearningLoop:
    """自学习循环 / Self-learning Loop"""

    def __init__(self, skill_output_dir: str, llm_router=None):
        self.skill_dir = Path(skill_output_dir)
        self.skill_dir.mkdir(parents=True, exist_ok=True)
        self.pending_dir = self.skill_dir / "_pending"
        self.pending_dir.mkdir(parents=True, exist_ok=True)
        self.llm = llm_router
        self.log_path = self.skill_dir / "learning_log.json"
        self.log: list[dict] = self._load_log()

    def _load_log(self) -> list[dict]:
        if self.log_path.exists():
            try:
                return json.loads(self.log_path.read_text())
            except Exception:
                pass
        return []

    def _save_log(self):
        # L-16: 原子写入（临时文件+重命名）/ Atomic write (temp + rename)
        import tempfile
        data = json.dumps(self.log[-100:], ensure_ascii=False, indent=2)
        try:
            fd, tmp_path = tempfile.mkstemp(dir=str(self.log_path.parent), suffix='.tmp')
            with os.fdopen(fd, 'w') as f:
                f.write(data)
            tmp = Path(tmp_path)
            tmp.replace(self.log_path)
        except Exception:
            # 降级：直接写入 / Fallback: direct write
            self.log_path.write_text(data)

    def _save_skill(self, path: Path, content: str):
        """原子写入技能文件 / Atomic write skill file"""
        import tempfile
        try:
            fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix='.tmp')
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(content)
            Path(tmp_path).replace(path)
        except Exception:
            path.write_text(content, encoding='utf-8')

    async def on_task_complete(
        self,
        task: str,
        tool_calls: list[dict],
        result: str,
        llm=None,
    ):
        """任务完成后触发学习 / Trigger learning after task completion"""
        # 1. 评估复杂度 / 1. Assess complexity
        complexity = self._assess_complexity(tool_calls, result)
        logger.info(f"Task complexity: {complexity:.2f} ({len(tool_calls)} tool calls)")

        # 2. 记录日志 / 2. Log entry
        entry = {
            "timestamp": datetime.now().isoformat(),
            "task": task[:200],
            "tool_calls": len(tool_calls),
            "complexity": complexity,
            "tools_used": [tc.get("name", "") for tc in tool_calls],
            "learned": False,
        }
        self.log.append(entry)
        # L-18: 内存中截断 / Truncate in memory, prevent unbounded growth
        if len(self.log) > 200:
            self.log = self.log[-100:]
        self._save_log()

        # 3. 如果足够复杂，尝试提炼技能 / 3. If complex enough, try to extract skill
        if complexity > 0.6 and len(tool_calls) >= 3 and (self.llm or llm):
            await self._try_extract_skill(task, tool_calls, result, llm)

    def _assess_complexity(self, tool_calls: list[dict], result: str) -> float:
        """评估任务复杂度 / Assess task complexity (0-1)"""
        score = 0.0

        # 工具调用数量 / Number of tool calls
        n_calls = len(tool_calls)
        if n_calls >= 5:
            score += 0.3
        elif n_calls >= 3:
            score += 0.2
        elif n_calls >= 2:
            score += 0.1

        # 工具多样性 / Tool diversity
        unique_tools = set(tc.get("name", "") for tc in tool_calls)
        if len(unique_tools) >= 3:
            score += 0.2
        elif len(unique_tools) >= 2:
            score += 0.1

        # 结果长度 / Result length
        if len(result) > 1000:
            score += 0.2
        elif len(result) > 500:
            score += 0.1

        # 是否包含数据分析/报告关键词 / Contains analysis/report keywords
        keywords = ["分析", "报告", "研究", "analyze", "report", "research", "统计", "比较"]
        for kw in keywords:
            if kw in result.lower():
                score += 0.1
                break

        return min(score, 1.0)

    async def _try_extract_skill(
        self, task: str, tool_calls: list[dict], result: str, llm=None
    ):
        """尝试提炼技能 / Try to extract skill"""
        router = llm or self.llm
        if not router:
            return

        try:
            # 格式化步骤 / Format steps
            steps_str = json.dumps(tool_calls, ensure_ascii=False, indent=2)[:2000]

            prompt = SKILL_EXTRACTION_PROMPT.format(
                task=task[:500],
                steps=steps_str,
                outcome=result[:500],
            )

            response = await router.chat(
                messages=[{"role": "user", "content": prompt}],
                model="zai/glm-5.1",
            )

            skill_content = response.content

            # 验证是有效的 SKILL.md / Validate it is a valid SKILL.md
            if skill_content.strip().startswith("---"):
                # 生成文件名 / Generate filename
                skill_name = f"learned_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                skill_path = self.pending_dir / skill_name / "SKILL.md"
                skill_path.parent.mkdir(parents=True, exist_ok=True)
                self._save_skill(skill_path, skill_content)

                logger.info(f"🎯 New skill extracted: {skill_name}")
                return skill_name

        except Exception as e:
            logger.error(f"Skill extraction failed: {e}")

        return None

    def get_pending_skills(self) -> list[Path]:
        """获取待审核的技能 / Get pending skills"""
        if not self.pending_dir.exists():
            return []
        return list(self.pending_dir.glob("*/SKILL.md"))

    def approve_skill(self, skill_name: str) -> bool:
        """审核通过 / Approved — move to official directory"""
        pending = self.pending_dir / skill_name
        target = self.skill_dir / skill_name
        if pending.exists():
            pending.rename(target)
            logger.info(f"Skill approved: {skill_name}")
            return True
        return False

    def reject_skill(self, skill_name: str) -> bool:
        """拒绝技能 / Reject skill"""
        pending = self.pending_dir / skill_name
        if pending.exists():
            import shutil
            shutil.rmtree(pending)
            return True
        return False
