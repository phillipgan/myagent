[English](README.md) | **中文**

# 🤖 MyAgent — 自托管个人办公 AI 助手

**ReAct 智能体循环 · OpenClaw Skills 兼容 · 多通道消息 · 四层记忆系统 · 可扩展工具集**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)]()
[![Status](https://img.shields.io/badge/版本-v0.5.1-yellow.svg)]()

---

## 目录

- [✨ 功能特性](#-功能特性)
- [📋 环境要求](#-环境要求)
- [🚀 快速安装](#-快速安装)
- [⚙️ 配置说明](#️-配置说明)
- [🔌 通道配置](#-通道配置)
- [🧭 运行模式](#-运行模式)
- [🛠️ 内置工具](#️-内置工具)
- [🧠 记忆系统](#-记忆系统)
- [🎓 技能系统](#-技能系统)
- [🔐 安全体系](#-安全体系)
- [🏗️ 系统架构](#️-系统架构)
- [🐳 Docker 部署](#-docker-部署)
- [📖 常见问题](#-常见问题)

---

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| **ReAct 智能体循环** | 推理-行动迭代循环，支持多步工具调用（最多 60 轮） |
| **多模型路由** | 按任务类型自动路由：GLM-5 对话、DeepSeek 写代码、Qwen 分析、Gemini 深度研究 |
| **OpenClaw Skills 兼容** | 自动发现并执行社区技能（`SKILL.md` 格式），复用 OpenClaw 生态 |
| **多通道接入** | CLI 终端 / 飞书 / Telegram 三通道统一接入 |
| **12 个内置工具** | 文件读写、网页搜索/抓取、邮件收发、日历、数据分析、代码执行、深度搜索等 |
| **四层记忆系统** | 工作记忆 → 短期记忆(SQLite) → 长期记忆(向量库) → 用户画像(JSON) |
| **技能自学习** | 从复杂任务模式中自动提取新技能，供未来复用 |
| **通道看门狗** | 子进程崩溃自动重启，指数退避策略 |
| **生产级就绪** | systemd 服务、Docker 部署、健康检查、结构化日志 |

---

## 📋 环境要求

| 项目 | 版本 | 说明 |
|------|------|------|
| Python | ≥ 3.11 | 测试通过 3.11 / 3.12 |
| 操作系统 | Linux / macOS / WSL2 | — |
| Conda | 任意 | 推荐，环境隔离 |
| Git | 任意 | — |
| 内存 | ≥ 4GB | — |
| (可选) Docker | ≥ 20.x | 容器化部署 |
| (可选) Ollama | 任意 | 本地 LLM 推理 |

---

## 🚀 快速安装

### 第 1 步：克隆项目 & 创建环境

```bash
git clone https://github.com/your-username/myagent.git
cd myagent

# 创建 Conda 环境
conda create -n myagent python=3.12 -y
conda activate myagent
```

### 第 2 步：安装依赖

```bash
# 方式一：pip install -e .（推荐，同时注册命令行工具）
pip install -e .

# 方式二：requirements.txt
pip install -r requirements.txt
```

<details>
<summary>📦 完整依赖列表（18 个包）</summary>

| 包名 | 最低版本 | 用途 |
|------|---------|------|
| `openai` | ≥ 1.0 | LLM API 客户端（OpenAI 兼容） |
| `httpx` | ≥ 0.27 | 异步 HTTP 客户端 |
| `fastapi` | ≥ 0.110 | Gateway HTTP/WebSocket 服务器 |
| `uvicorn` | ≥ 0.29 | ASGI 服务器 |
| `pyyaml` | ≥ 6.0 | 配置文件解析 |
| `rich` | ≥ 13.0 | 终端美化输出 |
| `prompt_toolkit` | ≥ 3.0 | 交互式 CLI |
| `aiofiles` | ≥ 23.0 | 异步文件操作 |
| `aiosmtplib` | ≥ 1.1 | 异步邮件发送 |
| `apscheduler` | ≥ 3.10 | 定时任务调度 |
| `python-multipart` | ≥ 0.0.6 | FastAPI 文件上传 |
| `sqlite-vec` | ≥ 0.1 | 向量相似度搜索 |
| `lxml` | ≥ 5.0 | HTML/XML 解析 |
| `pandas` | ≥ 2.0 | 数据分析 |
| `openpyxl` | ≥ 3.1 | Excel 文件处理 |
| `lark-oapi` | ≥ 1.6 | 飞书 SDK |
| `aiogram` | ≥ 3.15 | Telegram Bot SDK |

</details>

### 第 3 步：配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key（详见下方配置说明）
```

### 第 4 步：启动

```bash
# CLI 交互模式
python -m src.main cli

# Gateway 网关模式（Web + 飞书 + Telegram）
python -m src.main gateway --port 5196 --log INFO
```

---

## ⚙️ 配置说明

MyAgent 采用**分层配置**：`.env`（敏感凭据）+ `config/default.yaml`（行为配置）。

### 环境变量清单（`.env`）

| 变量名 | 用途 | 必填 |
|--------|------|------|
| `MYAGENT_INTERNAL_SECRET` | 内部端点 HMAC 签名密钥 | ✅ 必须 |
| `ZAI_API_KEY` | 智谱 GLM API Key（默认模型） | ✅ 默认模型 |
| `GOOGLE_API_KEY` | Google/Gemini API Key | 可选 |
| `OPENAI_API_KEY` | OpenAI API Key | 可选 |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | 可选 |
| `BRAVE_SEARCH_API_KEY` | Brave 搜索 API Key | 可选（降级 DuckDuckGo） |
| `TAVILY_API_KEY` | Tavily 搜索 API Key | 可选 |
| `FEISHU_APP_ID` | 飞书应用 ID | 飞书通道 |
| `FEISHU_APP_SECRET` | 飞书应用密钥 | 飞书通道 |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | Telegram 通道 |
| `GMAIL_ADDRESS` | Gmail 邮箱地址 | 邮件功能 |
| `GMAIL_APP_PASSWORD` | Gmail 应用专用密码 | 邮件功能 |
| `MAIL_163_ADDRESS` | 163 邮箱地址 | 邮件功能（可选） |
| `163_IMAP_PASSWORD` | 163 邮箱 IMAP 授权码 | 邮件功能（可选） |

### `.env` 示例

```bash
# ═══ 必须配置 ═══
MYAGENT_INTERNAL_SECRET=你的随机密钥字符串
ZAI_API_KEY=你的智谱API密钥

# ═══ 搜索引擎 ═══
BRAVE_SEARCH_API_KEY=你的Brave搜索API密钥

# ═══ 飞书通道 ═══
FEISHU_APP_ID=cli_xxxxxxxxxxxxxxxx
FEISHU_APP_SECRET=你的飞书应用密钥

# ═══ Telegram 通道 ═══
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# ═══ 邮件功能 ═══
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

### 如何获取 API Key

<details>
<summary>🔑 智谱 GLM（默认 LLM 提供商）</summary>

1. 访问 [https://open.bigmodel.cn](https://open.bigmodel.cn)
2. 注册账号
3. 进入「API Keys」→ 创建新 Key
4. 将 Key 填入 `.env` 的 `ZAI_API_KEY`

</details>

<details>
<summary>🔍 Brave 搜索 API</summary>

1. 访问 [https://api.search.brave.com](https://api.search.brave.com)
2. 注册免费账号（每月 2,000 次免费查询）
3. 订阅 Search API
4. 将 API Key 填入 `.env` 的 `BRAVE_SEARCH_API_KEY`

</details>

<details>
<summary>🤖 Ollama（本地 LLM）</summary>

1. 安装 Ollama：`curl -fsSL https://ollama.com/install.sh | sh`
2. 拉取模型：`ollama pull qwen3.6:35b`
3. Ollama 运行在 `http://localhost:11434`，无需 API Key
4. 如需将 Ollama 设为默认模型，修改 `config/default.yaml`：

```yaml
models:
  default: "ollama/qwen3.6:35b"
```

</details>

<details>
<summary>🌍 Google/Gemini API</summary>

1. 访问 [Google AI Studio](https://aistudio.google.com/apikey)
2. 创建 API Key
3. 填入 `.env` 的 `GOOGLE_API_KEY`

</details>

### 模型路由配置（`config/default.yaml`）

```yaml
models:
  default: "zai/glm-5.1"           # 默认模型
  routes:
    chat: "zai/glm-5.1"            # 日常对话
    code: "deepseek/deepseek-coder" # 代码生成
    analysis: "ollama/qwen3.6:35b"  # 数据分析（本地）
    research: "google/gemini-2.5-pro" # 深度研究
    translation: "ollama/qwen3.6:27b" # 翻译
    classification: "ollama/qwen3.5:4b" # 快速分类
```

### 自动降级链

当某个提供商不可用时，自动降级：

```
zai/glm-5.1 → openrouter/auto → ollama/qwen3.5:4b
```

每个模型最多失败 3 次后跳过，`asyncio.Lock` 保证线程安全。

---

## 🔌 通道配置

### 飞书（飞书/Lark）通道

<details>
<summary>📱 详细配置步骤</summary>

**前提条件**：在[飞书开放平台](https://open.feishu.cn)创建企业自建应用

1. **创建应用**：飞书开放平台 → 创建企业自建应用
2. **开启机器人**：应用设置中开启「机器人」能力
3. **获取凭据**：复制 **App ID** 和 **App Secret**
4. **配置权限**：添加以下权限：
   - 发送消息（`im:message:send_as_bot`）
   - 接收消息（`im:message`）
   - 读取群信息（`im:chat:readonly`）
5. **配置 `.env`**：

```bash
FEISHU_APP_ID=cli_xxxxxxxxxxxxxxxx
FEISHU_APP_SECRET=你的飞书应用密钥
```

6. **启用配置**：

```yaml
channels:
  feishu:
    enabled: true
    app_id: "${FEISHU_APP_ID}"
    app_secret: "${FEISHU_APP_SECRET}"
```

**架构**：子进程运行 lark-oapi WebSocket 长连接，无需公网 IP 和 Webhook URL。

</details>

### Telegram 通道

<details>
<summary>✈️ 详细配置步骤</summary>

**前提条件**：通过 [@BotFather](https://t.me/BotFather) 创建 Bot

1. **创建 Bot**：在 Telegram 中向 `@BotFather` 发送 `/newbot`，按提示操作
2. **获取 Token**：复制 Bot Token（格式：`123456789:ABCdef...`）
3. **获取用户 ID**：向 `@userinfobot` 发消息获取你的数字用户 ID
4. **配置 `.env`**：

```bash
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

5. **启用配置**：

```yaml
channels:
  telegram:
    enabled: true
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    admin_ids: "123456789"          # 你的 Telegram 用户 ID（逗号分隔）
    allowed_groups: "-1001234567890" # 允许的群组 ID（逗号分隔，空=所有群组）
```

**Bot 命令**：`/start` `/help` `/status` `/skills` `/tools` `/history` `/reset`

**群组使用**：需要 @提及 Bot 或回复 Bot 的消息才会响应。

</details>

### 邮件功能配置

<details>
<summary>📧 Gmail 应用专用密码</summary>

1. 在 Google 账户中启用两步验证
2. 进入 [Google 账户安全设置](https://myaccount.google.com/security) → 应用密码
3. 生成新的应用密码（选择「邮件」→「其他」）
4. 复制 16 位密码（格式：`xxxx xxxx xxxx xxxx`）
5. 配置 `.env`：

```bash
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

</details>

### 通道看门狗

自动监控通道子进程，崩溃后自动重启：

```yaml
channels:
  watchdog:
    enabled: true            # 启用看门狗
    check_interval: 1800     # 检测间隔（秒，默认 30 分钟）
    max_retries: 5           # 最大连续重试次数
    backoff_base: 60         # 退避基数（秒）
    backoff_max: 3600        # 最大退避间隔（秒）
```

| 重试次数 | 等待时间 |
|---------|----------|
| 第 1 次 | 60 秒 |
| 第 2 次 | 120 秒 |
| 第 3 次 | 240 秒 |
| 第 4 次 | 480 秒 |
| 第 5 次 | 960 秒 |
| 超过 5 次 | 冷却，等下个周期 |

---

## 🧭 运行模式

### CLI 交互模式

```bash
python -m src.main cli
```

Rich 美化终端输出，支持命令历史和 Tab 补全。

```
💬 > 帮我查一下迪拜今天的天气
💬 > 分析 ~/data/sales.csv 文件
💬 > 发邮件给 test@163.com，主题"测试报告"
💬 > /status
💬 > /skills
💬 > quit
```

### Gateway 网关模式

```bash
python -m src.main gateway --port 5196 --log INFO
```

启动内容：
- **FastAPI 服务器** `127.0.0.1:5196`
- **WebSocket** 实时聊天 `/ws`
- **Web Dashboard** `http://127.0.0.1:5196/`
- **飞书 + Telegram** 通道子进程
- **通道看门狗** 自动重启

### 实用命令

```bash
python -m src.main status    # 查看 Agent 状态（JSON）
python -m src.main tools     # 列出所有注册工具
python -m src.main skills    # 列出所有已发现技能
```

---

## 🛠️ 内置工具

| 工具 | 功能 | 安全措施 |
|------|------|----------|
| `exec` | Shell 命令执行 | 21 种危险模式检查，超时自动 kill |
| `file_read` | 读取文件内容 | 路径沙箱白名单 |
| `file_write` | 写入/创建文件 | 路径沙箱 + 自动创建目录 |
| `file_edit` | 精确文本替换 | 路径沙箱 |
| `web_search` | Brave Search / DuckDuckGo | — |
| `web_fetch` | 抓取网页内容 | SSRF 防护（私有 IP + 元数据端点 + DNS 验证） |
| `email_read` | 读取邮件（IMAP） | 连接 finally 关闭，搜索注入防护 |
| `email_send` | 发送邮件（SMTP） | 环境变量凭据，连接 finally 关闭 |
| `calendar` | Google 日历（查询/搜索/创建） | HTTP 状态码检查 |
| `data_analysis` | CSV/Excel/JSON 分析 | 异步读取，pandas query() 安全化 |
| `feishu_api` | 飞书 API（消息/搜索/文档） | 环境变量凭据，Token 自动刷新 |
| `deep_search` | 多源并行搜索 | 交叉验证 + LLM 综合分析 |

---

## 🧠 记忆系统

MyAgent 实现了受人类认知启发的四层记忆架构：

```
┌─────────────────────────────────────────────────┐
│  L1: 工作记忆                                     │
│  内存对话缓冲区（40 条消息窗口）                     │
│  会话结束即清空                                     │
├─────────────────────────────────────────────────┤
│  L2: 短期记忆（情景记忆）                           │
│  SQLite + FTS5 全文搜索                            │
│  保留 7 天（高重要性条目永久保留）                    │
├─────────────────────────────────────────────────┤
│  L3: 长期记忆（语义记忆）                           │
│  向量嵌入（sqlite-vec）+ FTS5                      │
│  相似度搜索，永久保存                               │
├─────────────────────────────────────────────────┤
│  L4: 用户模型                                     │
│  JSON 文件持久化                                   │
│  结构化用户画像：身份、偏好、工作模式、沟通风格        │
└─────────────────────────────────────────────────┘
```

每次对话自动注入记忆上下文：用户画像 + 近期记忆 + 相关知识。

---

## 🎓 技能系统

MyAgent **兼容 OpenClaw Skills 格式**，自动发现并加载 `SKILL.md` 文件。

### 工作原理

1. **发现**：按优先级扫描配置的技能目录（高优先级覆盖低优先级）
2. **解析**：读取 YAML 前置元数据 + Markdown 正文
3. **注入**：将技能摘要列表注入 system prompt
4. **按需加载**：LLM 需要时才加载完整指令（节省 Token）

### 添加自定义技能

MyAgent 支持**三层技能体系**（优先级从高到低）：

1. **项目自带技能**（`./skills/`）— 15 个精选技能随项目发布（见下表）
2. **OpenClaw 技能**（`~/.openclaw/workspace/skills/` 等）— 已安装 OpenClaw 时自动发现
3. **自定义技能** — 在任意技能根目录下创建 `SKILL.md`

#### 项目自带技能（15 个）

| 技能 | 说明 |
|-------|------|
| **web-search-plus** | 多引擎统一搜索（Serper/Tavily/Exa/Perplexity） |
| **tavily-search** | Tavily AI 优化网页搜索 |
| **brave-images** | Brave 图像搜索 |
| **chart-image** | 出版级图表生成 |
| **diagram-maker** | SVG/HTML 架构图与流程图 |
| **summarize** | 摘要 URL/PDF/音频/YouTube |
| **translator** | 专业翻译（中↔英、中↔日、多语言） |
| **ai-writing-assistant-cn** | 中文写作助手（10 种风格） |
| **code-mentor** | AI 编程导师与代码审查 |
| **code-share** | 通过 GitHub Gist 分享代码 |
| **github** | GitHub CLI 操作（Issue/PR/CI） |
| **gh-issues** | GitHub Issue 处理与自动修复 |
| **ceo-advisor** | 高管决策与战略指导 |
| **autonomous-research** | 自主深度研究 |
| **weather** | 天气查询（无需 API Key） |

#### Docker 环境启用 OpenClaw 技能

如果宿主机已安装 OpenClaw，在 `docker-compose.yaml` 中取消注释挂载行：

```yaml
volumes:
  # ... 项目自带技能 ...
  # 取消注释以启用 OpenClaw 技能：
  # - ~/.openclaw/workspace/skills:/root/.openclaw/workspace/skills:ro
  # - ~/.npm-global/lib/node_modules/openclaw/skills:/root/.npm-global/lib/node_modules/openclaw/skills:ro
```

在任意技能根目录下创建 `SKILL.md`：

```yaml
---
name: my-custom-skill
description: "做些有用的事情"
metadata:
  openclaw:
    requires:
      - exec
      - file_read
---

# 我的自定义技能

当用户要求做 X 时，按以下步骤操作：

1. 首先，使用 file_read 读取配置...
2. 然后，使用 exec 执行...
3. 最后，生成报告...
```

### 技能自学习

MyAgent 自动从复杂任务中学习（3+ 次工具调用）。当任务复杂度足够高时，LLM 自动生成新的 `SKILL.md` 供未来复用。

---

## 🔐 安全体系

| 安全措施 | 说明 |
|---------|------|
| **HMAC 内部认证** | 子进程↔主进程通信签名验证（`MYAGENT_INTERNAL_SECRET`） |
| **路径沙箱** | 文件操作限制在白名单目录内（workspace、AIspace 等） |
| **SSRF 防护** | 阻止私有 IP、云元数据端点、DNS Rebinding 攻击 |
| **命令安全** | 拦截 21 种危险命令（rm -rf、Fork 炸弹、反弹 Shell 等） |
| **本地绑定** | Gateway 默认绑定 `127.0.0.1`，不暴露到网络 |
| **PII 脱敏** | 审计日志自动脱敏敏感信息 |
| **CORS 限制** | 仅允许 localhost |
| **XSS 防护** | Dashboard 使用 `textContent` + HTML 转义 |

---

## 🏗️ 系统架构

```
                    Gateway (FastAPI)
                   http://127.0.0.1:5196
  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │ Dashboard │  │ WebSocket│  │ REST API │  │ Webhook  │
  └──────────┘  └──────────┘  └──────────┘  └──────────┘
         ┌───────────────────────────────────────┐
         │         Agent 编排器 (ReAct 循环)        │
         │  ┌───────────┐  ┌──────────────────┐   │
         │  │ LLM 路由器  │  │ 降级链            │   │
         │  │ + Provider │  │ (自动降级)         │   │
         │  └───────────┘  └──────────────────┘   │
         │  ┌───────────┐  ┌──────────────────┐   │
         │  │ 12 个工具   │  │ 四层记忆系统        │   │
         │  └───────────┘  └──────────────────┘   │
         │  ┌───────────┐  ┌──────────────────┐   │
         │  │ 技能系统    │  │ 自学习引擎         │   │
         │  └───────────┘  └──────────────────┘   │
         └───────────────────────────────────────┘
                    │
    ┌───────────────┼───────────────┐
    │               │               │
  飞书           Telegram        CLI
  (子进程)        (子进程)       (主进程)
  WebSocket      Long Polling   Rich TUI
```

**子进程隔离**：飞书和 Telegram 作为独立子进程运行，SDK 崩溃不影响主服务。通过 HMAC 签名的 HTTP 回调通信。

---

## 🐳 Docker 部署

```bash
# 构建并启动
docker compose up -d

# 查看日志
docker compose logs -f myagent

# 停止
docker compose down
```

容器暴露端口 **5196**，通过 `./workspace` 目录持久化数据。

---

## 📖 常见问题

**Q：Gateway 启动报 `MYAGENT_INTERNAL_SECRET not set`？**
A：在 `.env` 中添加 `MYAGENT_INTERNAL_SECRET=<随机字符串>`。这是内部端点的 HMAC 签名密钥。

**Q：Telegram Bot 无响应？**
A：检查 `TELEGRAM_BOT_TOKEN` 是否正确，`admin_ids` 是否包含你的 Telegram 用户 ID。

**Q：飞书消息不回复？**
A：确认飞书应用已开启「机器人」能力，App ID 和 Secret 正确。

**Q：命令被安全模块拦截？**
A：这是预期行为。exec 工具会检查 21 种危险命令模式，确保命令不匹配安全规则。

**Q：Ollama 连接失败？**
A：运行 `ollama list` 确认 Ollama 正在运行。默认地址 `http://localhost:11434`。

**Q：如何添加新的 LLM 提供商？**
A：在 `.env` 中添加凭据，在 `config/default.yaml` 的 `providers:` 下添加提供商配置，可选在 `models.routes:` 添加路由。

**Q：FTS5 不可用？**
A：部分系统 Python 未编译 FTS5 支持。不影响运行，仅全文搜索功能降级。安装 `pysqlite3` 可解决。

**Q：workspace 目录在哪里？**
A：MyAgent 默认使用项目目录下的 `./workspace/` 文件夹保存所有运行时数据（记忆数据库、日志、搜索报告等）。

---

## 📄 许可证

MIT 许可证 — 详见 [LICENSE](LICENSE)。
