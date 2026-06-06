"""配置加载模块 / Configuration Loading Module"""

import os
from pathlib import Path
from dataclasses import dataclass, field
import yaml


PROJECT_ROOT = Path(__file__).parent.parent  # myagent 项目根目录 / Project root directory


def _resolve_workspace(path_str: str) -> str:
    """解析 workspace 路径 — 相对路径基于项目根目录 / Resolve workspace path — relative to project root"""
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return str(p)


def _resolve_path(path_str: str) -> Path:
    """解析路径 — 相对路径基于项目根目录 / Resolve path — relative to project root"""
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    return p


@dataclass
class ProviderConfig:
    """LLM 提供商配置 / LLM Provider Configuration"""
    base_url: str = ""
    api_key: str = ""
    model: str = ""


@dataclass
class ModelConfig:
    """模型路由配置 / Model Routing Configuration"""
    default: str = "ollama/qwen3.6:35b"
    routes: dict[str, str] = field(default_factory=dict)


@dataclass
class SkillConfig:
    """技能配置 / Skill Configuration"""
    roots: list[str] = field(default_factory=list)
    extra_dirs: list[str] = field(default_factory=list)


@dataclass
class MemoryConfig:
    """记忆配置 / Memory Configuration"""
    db_path: str = ""
    episodic_dir: str = ""
    core_dir: str = ""
    retention_days: int = 7


@dataclass
class FeishuConfig:
    """飞书通道配置 / Feishu Channel Configuration"""
    enabled: bool = False
    app_id: str = ""
    app_secret: str = ""
    verification_token: str = ""
    encrypt_key: str = ""


@dataclass
class TelegramConfig:
    """Telegram 通道配置 / Telegram Channel Configuration"""
    enabled: bool = False
    bot_token: str = ""
    admin_ids: str = ""        # 逗号分隔的管理员 Telegram user ID / Comma-separated admin Telegram user IDs
    allowed_groups: str = ""    # 逗号分隔的群组 chat ID / Comma-separated group chat IDs


@dataclass
class ChannelsConfig:
    """全部通道配置 / All Channels Configuration"""
    feishu: FeishuConfig = field(default_factory=FeishuConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)


@dataclass
class AgentConfig:
    """Agent 全局配置 / Agent Global Configuration"""
    name: str = "MyAgent"
    workspace: str = "./workspace"
    skill: SkillConfig = field(default_factory=SkillConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    providers: dict[str, ProviderConfig] = field(default_factory=dict)
    channels: ChannelsConfig = field(default_factory=ChannelsConfig)
    max_iterations: int = 10
    default_timeout: int = 30


def _resolve_env(value: str) -> str:
    """H-14: 解析 ${ENV_VAR} 格式的环境变量 / Parse ${ENV_VAR} env vars — supports embedded variables"""
    if not isinstance(value, str):
        return value
    import re
    def _replace(match):
        env_name = match.group(1)
        return os.environ.get(env_name, "")
    # 支持完整的 ${VAR} 替换 / Full ${VAR} substitution, including embedded in strings
    # Support full ${VAR} substitution, including embedded in strings
    # 例如: "https://api.example.com?key=${API_KEY}" → 正确替换 / e.g. correctly replaces embedded vars
    return re.sub(r'\$\{([^}]+)\}', _replace, value)


def load_config(config_path: str | None = None) -> AgentConfig:
    """加载配置文件 / Load configuration file"""
    # 加载 .env 文件（L-13: 更健壮的解析）/ Load .env file (L-13: more robust parsing)
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                # L-13: 支持引号包裹的值 / L-13: Support quoted values
                if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                    value = value[1:-1]
                if key and value:
                    os.environ.setdefault(key, value)

    if config_path is None:
        config_path = str(Path(__file__).parent.parent / "config" / "default.yaml")

    config_path = Path(config_path)
    if not config_path.exists():
        return AgentConfig()

    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    # 解析 Agent 配置 / Parse Agent config
    agent_raw = raw.get("agent", {})
    models_raw = raw.get("models", {})
    providers_raw = raw.get("providers", {})
    memory_raw = raw.get("memory", {})

    # 构建提供商配置 / Build provider config
    providers = {}
    for name, prov in providers_raw.items():
        providers[name] = ProviderConfig(
            base_url=prov.get("base_url", ""),
            api_key=_resolve_env(prov.get("api_key", "")),
            model=prov.get("model", ""),
        )

    # 构建 Skill 配置 / Build Skill config
    skill_roots = agent_raw.get("skill_roots", [])
    # 展开路径 / Expand paths
    skill_roots = [str(Path(p).expanduser()) for p in skill_roots]

    # 解析通道配置 / Parse channel config
    channels_raw = raw.get("channels", {})
    feishu_raw = channels_raw.get("feishu", {})
    telegram_raw = channels_raw.get("telegram", {})

    config = AgentConfig(
        name=agent_raw.get("name", "MyAgent"),
        workspace=_resolve_workspace(agent_raw.get("workspace", "./workspace")),
        max_iterations=agent_raw.get("max_iterations", 10),
        default_timeout=agent_raw.get("default_timeout", 30),
        skill=SkillConfig(roots=skill_roots),
        model=ModelConfig(
            default=models_raw.get("default", "ollama/qwen3.6:35b"),
            routes=models_raw.get("routes", {}),
        ),
        memory=MemoryConfig(
            db_path=str(_resolve_path(memory_raw.get("db_path", "./workspace/memory/semantic/vectors.db"))),
            episodic_dir=str(_resolve_path(memory_raw.get("episodic_dir", "./workspace/memory/episodic"))),
            core_dir=str(_resolve_path(memory_raw.get("core_dir", "./workspace/memory/core"))),
            retention_days=memory_raw.get("retention_days", 7),
        ),
        providers=providers,
        channels=ChannelsConfig(
            feishu=FeishuConfig(
                enabled=feishu_raw.get("enabled", False),
                app_id=_resolve_env(feishu_raw.get("app_id", "")),
                app_secret=_resolve_env(feishu_raw.get("app_secret", "")),
                verification_token=_resolve_env(feishu_raw.get("verification_token", "")),
                encrypt_key=_resolve_env(feishu_raw.get("encrypt_key", "")),
            ),
            telegram=TelegramConfig(
                enabled=telegram_raw.get("enabled", False),
                bot_token=_resolve_env(telegram_raw.get("bot_token", "")),
                admin_ids=telegram_raw.get("admin_ids", ""),
                allowed_groups=telegram_raw.get("allowed_groups", ""),
            ),
        ),
    )

    return config
