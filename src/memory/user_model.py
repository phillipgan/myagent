"""L4 用户模型 / L4 User Model — Structured Profile / L4 User Model — Structured User Profile

持久化用户的偏好、习惯、工作上下文，每次对话自动注入 system prompt。
Persists user preferences, habits, work context; auto-injected into system prompt.
Persists user preferences, habits, work context; auto-injected into system prompt each conversation.
存储格式：JSON 文件
Storage: JSON file (workspace/memory/core/user_model.json).

包含信息 / Contains:
  - 基本信息（姓名、语言、报告格式偏好）/ Basic info (name, language, report format prefs)
  - 工作上下文（行业、兴趣领域）/ Work context (industry, interest areas)
  - 沟通偏好（风格、详细程度）/ Communication prefs (style, detail level)
  - 技术设置（模型偏好、报告是否含技术细节）/ Tech settings (model prefs, tech detail toggle)

安全设计 / Safety Design:
  - H-15: save() 添加错误处理和日志 / save() error handling and logging
  - M-04: 使用 deepcopy 避免 DEFAULT_PROFILE 共享引用 / deepcopy to prevent shared refs
"""

import json
import copy
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_PROFILE = {
    "name": "User",
    "timezone": "Asia/Dubai",
    "language": "zh-CN",
    "email": "",
    "work": "",
    "preferences": {
        "response_language": "auto",
        "response_style": "professional_warm",
        "report_format": "html_email",
        "detail_level": "detailed",
    },
    "work_patterns": {
        "active_hours": "06:00-23:00",
        "quiet_hours": "23:00-06:00",
        "frequent_tasks": [],
        "preferred_tools": [],
    },
    "interests": [],
    "communication_style": {
        "likes_technical_details": True,
        "prefers_data_driven": True,
        "formal_reports_no_tech": True,
    }
}


class UserModel:
    """用户模型 — 持久化到 JSON 文件 / User Model — persisted to JSON file"""

    def __init__(self, core_dir: str):
        self.core_dir = Path(core_dir)
        self.core_dir.mkdir(parents=True, exist_ok=True)
        self.profile_path = self.core_dir / "user_profile.json"
        self.profile: dict = self._load()

    @staticmethod
    def _deep_merge(base: dict, override: dict) -> dict:
        """深度合并字典 / Deep merge dictionaries"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = UserModel._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _load(self) -> dict:
        """加载用户画像 / Load user profile"""
        if self.profile_path.exists():
            try:
                with open(self.profile_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                merged = self._deep_merge(DEFAULT_PROFILE, saved)
                return merged
            except Exception as e:
                logger.warning(f"Failed to load user profile: {e}")
        # M-04: 使用 deepcopy 避免共享引用 / M-04: Use deepcopy to avoid shared references
        return copy.deepcopy(DEFAULT_PROFILE)

    def save(self):
        """H-15: 保存用户画像 — 添加错误处理 / H-15: Save user profile — with error handling"""
        try:
            with open(self.profile_path, "w", encoding="utf-8") as f:
                json.dump(self.profile, f, ensure_ascii=False, indent=2)
        except (OSError, IOError) as e:
            logger.error(f"Failed to save user profile: {e}")
        except Exception as e:
            logger.error(f"Unexpected error saving user profile: {e}")

    def get(self, key: str, default: Any = None) -> Any:
        """获取属性（支持点号路径）/ Get property (supports dot notation)"""
        keys = key.split(".")
        value = self.profile
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k, default)
            else:
                return default
        return value

    def set(self, key: str, value: Any):
        """设置属性 / Set property"""
        keys = key.split(".")
        target = self.profile
        for k in keys[:-1]:
            if k not in target or not isinstance(target[k], dict):
                target[k] = {}
            target = target[k]
        target[keys[-1]] = value
        self.save()

    def update_patterns(self, task_type: str, tools_used: list[str]):
        """更新工作模式 / Update work patterns"""
        patterns = self.profile.setdefault("work_patterns", {})

        freq = patterns.setdefault("frequent_tasks", [])
        if task_type not in freq:
            freq.append(task_type)
            if len(freq) > 20:
                freq.pop(0)

        tools = patterns.setdefault("preferred_tools", [])
        for t in tools_used:
            if t not in tools:
                tools.append(t)
                if len(tools) > 15:
                    tools.pop(0)

        self.save()

    def get_context_for_prompt(self) -> str:
        """生成用于 system prompt 的用户画像摘要 / Generate user profile summary for system prompt"""
        prefs = self.profile.get("preferences", {})
        lang = prefs.get("response_language", "auto")
        style = prefs.get("response_style", "professional_warm")
        interests = self.profile.get("interests", [])

        return f"""## User Profile
- Name: {self.profile.get('name', 'User')}
- Timezone: {self.profile.get('timezone', 'UTC')}
- Language preference: {lang}
- Response style: {style}
- Key interests: {', '.join(interests[:5])}"""
