# MyAgent 安装配置指导书

> **版本**: v2.1  |  **日期**: 2026-06-04  |  **适用于**: MyAgent v0.5.1+

---

## 目录

1. [环境要求](#1-环境要求)
2. [快速安装](#2-快速安装)
3. [配置说明](#3-配置说明)
4. [启动方式](#4-启动方式)
5. [通道配置](#5-通道配置)
6. [使用方式](#6-使用方式)
7. [内置工具](#7-内置工具)
8. [记忆系统](#8-记忆系统)
9. [安全加固](#9-安全加固)
10. [Docker 部署](#10-docker-部署)
11. [常见问题](#11-常见问题)
12. [通道看门狗](#12-通道看门狗)
13. [项目结构](#13-项目结构)

---

## 1. 环境要求

| 项目 | 要求 |
|------|------|
| Python | 3.11+ |
| 操作系统 | Linux / macOS / WSL2 |
| Conda | 推荐（环境隔离） |
| 内存 | ≥ 4GB |
| 磁盘 | ≥ 2GB（代码 + 模型缓存） |

### 依赖包（18 个）

```
openai>=1.0, httpx>=0.27, fastapi>=0.110, uvicorn>=0.29,
pyyaml>=6.0, rich>=13.0, prompt_toolkit>=3.0, aiofiles>=23.0,
aiosmtplib>=1.1, apscheduler>=3.10, python-multipart>=0.0.6,
sqlite-vec>=0.1, lxml>=5.0, pandas>=2.0, openpyxl>=3.1,
lark-oapi>=1.6, aiogram>=3.15
```

---

## 2. 快速安装

```bash
# 1. 克隆项目
cd ~/AIspace
git clone <repo-url> myagent
cd myagent

# 2. 创建 Conda 环境
conda create -n myagent python=3.12 -y
conda activate myagent

# 3. 安装依赖
pip install -e .

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env，填入实际的 API Key

# 5. 启动
python -m src.main gateway --port 5196
```

---

## 3. 配置说明

### 3.1 配置文件结构

```
config/default.yaml    # 主配置（模型、通道、记忆）
.env                   # 敏感凭据（API Key，不提交 Git）
```

### 3.2 环境变量清单

| 变量名 | 用途 | 必填 |
|--------|------|------|
| `MYAGENT_INTERNAL_SECRET` | 内部端点 HMAC 签名密钥 | ✅ |
| `ZAI_API_KEY` | 智谱 GLM API | ✅（默认模型） |
| `FEISHU_APP_ID` | 飞书应用 ID | 飞书通道 |
| `FEISHU_APP_SECRET` | 飞书应用密钥 | 飞书通道 |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | Telegram 通道 |
| `GOOGLE_API_KEY` | Google/Gemini API | 可选 |
| `BRAVE_SEARCH_API_KEY` | Brave 搜索 API | 可选（降级 DuckDuckGo） |
| `OPENAI_API_KEY` | OpenAI API | 可选 |
| `DEEPSEEK_API_KEY` | DeepSeek API | 可选 |
| `GMAIL_ADDRESS` | Gmail 邮箱 | 邮件功能 |
| `GMAIL_APP_PASSWORD` | Gmail 应用专用密码 | 邮件功能 |
| `MAIL_163_ADDRESS` | 163 邮箱 | 邮件功能 |
| `163_IMAP_PASSWORD` | 163 IMAP 授权码 | 邮件功能 |

### 3.3 default.yaml 关键配置

```yaml
agent:
  name: "MyAgent"
  workspace: "~/.myagent"
  max_iterations: 60       # ReAct 最大迭代
  default_timeout: 30      # 工具超时（秒）

models:
  default: "zai/glm-5.1"   # 默认模型
  routes:                    # 按任务类型路由
    chat: "zai/glm-5.1"
    code: "deepseek/deepseek-coder"
    analysis: "ollama/qwen3.6:35b"

channels:
  feishu:
    enabled: true
    app_id: "${FEISHU_APP_ID}"
    app_secret: "${FEISHU_APP_SECRET}"
  telegram:
    enabled: true
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    admin_ids: ""            # 管理员 Telegram ID，逗号分隔
    allowed_groups: ""       # 允许的群组 ID，逗号分隔
  watchdog:
    enabled: true
    check_interval: 1800     # 检测间隔（秒，默认 30 分钟）
    max_retries: 5           # 单通道最大连续重试
    backoff_base: 60         # 退避基数（秒）
    backoff_max: 3600        # 最大退避（秒）

memory:
  db_path: "~/.myagent/memory/semantic/vectors.db"
  retention_days: 7
```

---

## 4. 启动方式

```bash
# CLI 交互模式（终端 TUI）
python -m src.main cli

# Gateway 模式（Web + 飞书 + Telegram）
python -m src.main gateway --port 5196

# 查看状态
python -m src.main status

# 列出工具
python -m src.main tools

# 列出技能
python -m src.main skills

# 使用启动脚本（自动检测 Conda 环境）
./run.sh gateway --port 5196
```

---

## 5. 通道配置

### 5.1 飞书通道

**前置条件**：在飞书开放平台创建企业自建应用

1. 开启「机器人」能力
2. 获取 App ID 和 App Secret
3. 配置事件订阅（可选，WebSocket 模式无需）

```yaml
channels:
  feishu:
    enabled: true
    app_id: "${FEISHU_APP_ID}"
    app_secret: "${FEISHU_APP_SECRET}"
```

**架构**：子进程运行 lark-oapi WebSocket 长连接 → 收到消息后 HTTP 回调主进程

### 5.2 Telegram 通道

**前置条件**：通过 @BotFather 创建 Bot

1. 获取 Bot Token
2. 获取你的 Telegram user ID（可通过 @userinfobot）
3. 如需群组使用，获取群组 chat ID

```yaml
channels:
  telegram:
    enabled: true
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    admin_ids: "123456,789012"       # 管理员 ID（空=所有人）
    allowed_groups: "-1001234567890"  # 允许的群组（空=所有群组）
```

**架构**：子进程运行 aiogram Long Polling → 收到消息后 HTTP 回调主进程

**Bot 命令**：/start /help /status /skills /tools /history /reset

---

## 6. 使用方式

### CLI 模式

```
💬 > 帮我查一下迪拜今天的天气
💬 > 分析 ~/data/sales.csv 文件
💬 > 发邮件给 test@163.com，主题"测试"
💬 > /status
💬 > /skills
💬 > quit
```

### 飞书 / Telegram

直接发消息给 Bot 即可。群组中需要 @bot 或回复 Bot 的消息。

---

## 7. 内置工具

| 工具 | 功能 | 安全措施 |
|------|------|----------|
| **exec** | Shell 命令执行 | 21 种危险模式检查，超时自动 kill |
| **read** | 读取文件内容 | 路径沙箱白名单 |
| **write** | 写入文件 | 路径沙箱 + 自动创建目录 |
| **edit** | 精确文本替换 | 路径沙箱 |
| **web_search** | Brave Search / DuckDuckGo | - |
| **web_fetch** | 抓取网页内容 | SSRF 防护（私有 IP + 元数据端点 + DNS 验证） |
| **email_read** | 读取邮件（IMAP） | 连接 finally 关闭，搜索注入防护 |
| **email_send** | 发送邮件（SMTP） | 环境变量凭据，连接 finally 关闭 |
| **calendar** | Google Calendar | HTTP 状态码检查 |
| **data_analysis** | CSV/Excel/JSON 分析 | 异步读取，pandas query() 安全化 |
| **feishu_api** | 飞书 API 调用 | 环境变量凭据，Token 自动刷新 |
| **deep_search** | 多源并行搜索 | LLM 综合分析 + 交叉验证 |

---

## 8. 记忆系统

| 层级 | 类型 | 存储 | 保留期 |
|------|------|------|--------|
| L1 工作记忆 | 对话缓冲 | 内存 | 会话内 |
| L2 短期记忆 | 事件摘要 | SQLite + FTS5 | 7 天（高重要性永久） |
| L3 长期记忆 | 语义知识 | SQLite + 向量 + FTS5 | 永久 |
| L4 用户模型 | 结构化画像 | JSON 文件 | 永久 |

**记忆上下文注入**：每次对话自动注入用户画像 + 近期记忆 + 相关记忆到 system prompt。

---

## 9. 安全加固

### 核心安全措施

| 措施 | 说明 |
|------|------|
| HMAC 内部认证 | 子进程↔主进程通信签名验证 |
| 路径沙箱 | 文件操作限制在白名单目录内 |
| SSRF 防护 | 阻止私有 IP + 云元数据端点 + DNS 解析验证 |
| 命令安全 | 21 种危险命令模式拦截 |
| CORS 收紧 | 仅 localhost |
| 默认绑定 127.0.0.1 | 不暴露到网络 |
| XSS 防护 | Dashboard 使用 textContent + HTML 转义 |
| PII 脱敏 | 审计日志自动脱敏 |
| 凭据保护 | 所有密钥通过环境变量引用 |
| 资源泄漏防护 | IMAP/SMTP 连接 finally 关闭，Provider close() 生命周期 |

### 降级链

```
zai/glm-5.1 → openrouter/auto → ollama/qwen3.5:4b
（每模型失败 3 次后跳过，asyncio.Lock 防并发）
```

---

## 10. Docker 部署

```bash
# 构建镜像
docker-compose build

# 启动（前台）
docker-compose up

# 启动（后台）
docker-compose up -d

# 查看日志
docker-compose logs -f
```

---

## 11. 常见问题

**Q1: 启动报 `lark-oapi not installed`**
```bash
pip install lark-oapi>=1.6
```

**Q2: Telegram Bot 无响应**
- 检查 `TELEGRAM_BOT_TOKEN` 是否正确
- 检查 `admin_ids` 是否包含你的 Telegram ID
- 检查网络是否能访问 Telegram API

**Q3: 飞书消息不回复**
- 检查 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 是否正确
- 确认飞书应用已开启「机器人」能力
- 查看日志中 WebSocket 连接状态

**Q4: Gateway 启动报 `MYAGENT_INTERNAL_SECRET not set`**
- 在 `.env` 中添加 `MYAGENT_INTERNAL_SECRET=<随机字符串>`
- 这是内部端点的 HMAC 签名密钥，不设置将拒绝所有内部请求

**Q5: 命令被安全模块拦截**
- 这是预期行为 — exec 工具会检查 21 种危险命令模式
- 如需执行特殊命令，确认命令不匹配任何安全规则

**Q6: Ollama 连接失败**
- 确认 Ollama 正在运行：`ollama list`
- 默认地址：`http://localhost:11434/v1`
- FallbackChain 会自动降级到下一个可用模型

**Q7: FTS5 不可用**
- 部分系统 Python 未编译 FTS5 支持
- 不影响运行，仅全文搜索功能降级
- 安装 `pysqlite3` 可解决

---

## 12. 通道看门狗

MyAgent v0.5.1+ 内置**通道看门狗**（Channel Watchdog），自动监控飞书和 Telegram 子进程的存活状态，崩溃后自动重启。

### 工作原理

- 每 **30 分钟** 检测一次所有通道子进程的 `is_alive()` 状态
- 发现通道已死 → 自动执行 `stop()` → `start()` 重启
- 采用**指数退避**策略，避免 DNS 持续故障时疯狂重连
- 状态暴露到 `/api/status` 端点

### 退避序列

| 重试次数 | 等待时间 |
|---------|----------|
| 第1次 | 60 秒 |
| 第2次 | 120 秒 |
| 第3次 | 240 秒 |
| 第4次 | 480 秒 |
| 第5次 | 960 秒 |
| 超过5次 | 进入冷却，等下个 30 分钟周期 |

### 配置（config/default.yaml）

```yaml
channels:
  watchdog:
    enabled: true            # 启用看门狗
    check_interval: 1800     # 检测间隔（秒）
    max_retries: 5           # 最大连续重试
    backoff_base: 60         # 退避基数（秒）
    backoff_max: 3600        # 最大退避（秒）
```

### 查看状态

```bash
# 通过 API 查看看门狗状态
curl http://localhost:5196/api/status | python -m json.tool
```

返回示例：
```json
{
  "watchdog": {
    "enabled": true,
    "check_interval": 1800,
    "channels": {
      "feishu": { "alive": true, "total_restarts": 0 },
      "telegram": { "alive": true, "total_restarts": 2 }
    }
  }
}
```

---

## 13. 项目结构

```
src/
├── main.py                 # 入口
├── config.py               # 配置加载
├── security.py             # 安全管理
├── agent/                  # Agent 核心
│   ├── orchestrator.py     # ReAct 编排器
│   ├── planner.py          # 任务分解
│   ├── subagent.py         # 子代理 + 多代理并行
│   └── intent.py           # 意图分类
├── llm/                    # LLM 路由
│   ├── router.py           # 多模型路由
│   ├── fallback.py         # 降级链
│   └── providers/          # 4 个 Provider
├── gateway/                # 通道
│   ├── server.py           # FastAPI Gateway
│   ├── watchdog.py         # 通道看门狗
│   ├── dashboard.py        # Web Dashboard
│   └── channels/           # CLI + 飞书 + Telegram
├── memory/                 # 四层记忆
│   ├── manager.py          # 记忆管理器
│   ├── working.py          # L1 工作记忆
│   ├── episodic.py         # L2 短期记忆
│   ├── semantic.py         # L3 长期记忆
│   ├── user_model.py       # L4 用户模型
│   └── consolidator.py     # 记忆巩固
├── tools/                  # 12 个内置工具
│   ├── __init__.py         # 工具注册表
│   ├── base.py             # 基类
│   ├── _security_utils.py  # 安全工具（沙箱 + SSRF）
│   └── ...                 # 各工具实现
├── skills/                 # OpenClaw 技能
│   ├── discovery.py        # 技能发现
│   ├── parser.py           # SKILL.md 解析
│   ├── executor.py         # 技能执行
│   ├── registry.py         # 技能注册表
│   └── learner.py          # 自学习
└── scheduler/              # 定时任务
    ├── cron.py             # Cron 调度器
    └── jobs/               # 任务定义
```

---

> **Generated by** MyAgent 🤖 | 2026年6月4日 | v2.1 — 基于 MyAgent v0.5.1 源码更新
