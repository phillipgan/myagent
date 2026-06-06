# MyAgent — 个人办公助手 Agent 高阶设计方案

> **版本**: v3.0  |  **日期**: 2026-06-02  |  **作者**: Author  |  **技术栈**: Python 3.12 + FastAPI + OpenClaw Skills

---

## 目录

1. [项目概述](#1-项目概述)
2. [系统架构](#2-系统架构)
3. [核心模块设计](#3-核心模块设计)
4. [LLM 多模型路由](#4-llm-多模型路由)
5. [四层记忆架构](#5-四层记忆架构)
6. [工具系统](#6-工具系统)
7. [技能系统（OpenClaw 兼容）](#7-技能系统openclaw-兼容)
8. [安全体系](#8-安全体系)
9. [通道架构](#9-通道架构)
10. [定时任务](#10-定时任务)
11. [自学习循环](#11-自学习循环)
12. [项目目录结构](#12-项目目录结构)
13. [技术选型决策](#13-技术选型决策)
14. [配置系统](#14-配置系统)
15. [开发路线图](#15-开发路线图)

---

## 1. 项目概述

**MyAgent** 是一个个人办公 AI Agent，核心设计理念：

- **OpenClaw Skills 兼容**：直接加载 `SKILL.md` 格式的技能文件，复用 OpenClaw 生态
- **多通道**：CLI / 飞书 / Telegram 三通道统一接入
- **多模型**：统一路由 + FallbackChain 自动降级
- **四层记忆**：工作记忆(L1) → 短期记忆(L2) → 长期记忆(L3) → 用户模型(L4)
- **安全第一**：HMAC 内部认证、路径沙箱、SSRF 防护、命令安全检查

### 技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| 语言 | Python | 3.12 |
| Web 框架 | FastAPI + Uvicorn | 0.110+ |
| LLM SDK | OpenAI Python SDK (AsyncOpenAI) | 1.0+ |
| 飞书 SDK | lark-oapi | 1.6+ |
| Telegram SDK | aiogram | 3.15+ |
| 数据库 | SQLite + FTS5 + sqlite-vec | 内置 |
| HTTP 客户端 | httpx | 0.27+ |
| 配置 | YAML + .env | PyYAML |
| 终端 UI | Rich + prompt_toolkit | 13.0+ |
| 运行环境 | Conda (`myagent`) | - |

---

## 2. 系统架构

### 2.1 整体架构图

```
┌──────────────────────────────────────────────────────────┐
│                    Gateway (FastAPI)                      │
│                   http://127.0.0.1:8765                   │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │ Dashboard │  │ WebSocket│  │ REST API │  │ Webhook  │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │
│  ┌───────────────────────────────────────────────────────┐│
│  │              Internal Auth (HMAC-SHA256)               ││
│  └───────────────────────────────────────────────────────┘│
└──────────┬──────────────┬──────────────┬─────────────────┘
           │              │              │
    ┌──────┴──────┐ ┌─────┴─────┐ ┌─────┴─────┐
    │  Feishu     │ │  Telegram  │ │   CLI     │
    │  子进程      │ │  子进程     │ │  (主进程)  │
    │ lark-oapi   │ │  aiogram   │ │  Rich TUI │
    │  WebSocket  │ │  Polling   │ │           │
    └──────┬──────┘ └─────┬─────┘ └─────┬─────┘
           │              │              │
           └──────┬───────┴──────────────┘
                  │ HTTP 回调 / 直接调用
           ┌──────┴──────┐
           │  Agent      │
           │  Orchestrator│
           │  (ReAct)     │
           ├──────────────┤
           │ ┌──────────┐ │
           │ │ LLM Router│ │──→ zai/glm-5.1 (默认)
           │ │ +Fallback │ │──→ openrouter/auto
           │ └──────────┘ │──→ ollama/qwen3.5:4b
           │ ┌──────────┐ │
           │ │   Tools   │ │──→ exec/read/write/edit/web_search...
           │ └──────────┘ │
           │ ┌──────────┐ │
           │ │  Memory   │ │──→ L1 Working + L2 Episodic + L3 Semantic + L4 UserModel
           │ └──────────┘ │
           │ ┌──────────┐ │
           │ │  Skills   │ │──→ OpenClaw SKILL.md 兼容
           │ └──────────┘ │
           │ ┌──────────┐ │
           │ │  Learner  │ │──→ 自学习循环
           │ └──────────┘ │
           └──────────────┘
```

### 2.2 子进程隔离架构

飞书和 Telegram 通道均采用「**子进程隔离 + HTTP 回调主进程**」模式：

```
主进程 (Gateway)                    子进程 (Channel)
┌──────────────────┐                ┌──────────────────┐
│  FastAPI Server  │                │  lark-oapi /      │
│  :8765           │◄─── HMAC ──────│  aiogram Bot      │
│                  │   签名 HTTP     │                   │
│  Agent           │   POST 回调    │  收到消息          │
│  Orchestrator    │                │  → POST 到主进程   │
└──────────────────┘                └──────────────────┘
```

**设计理由**：
- SDK 阻塞调用不冻结主进程事件循环
- SDK 崩溃不影响整体服务
- 子进程 `daemon=True`，主进程退出时自动清理

---

## 3. 核心模块设计

### 3.1 AgentOrchestrator（核心编排器）

文件：`src/agent/orchestrator.py`

**ReAct 循环 + 记忆 + 技能**：

```
用户消息
  ↓
构建 System Prompt（用户画像 + 记忆上下文 + 技能目录）
  ↓
ReAct 循环（最多 max_iterations 轮，总超时保护）
  │
  ├──→ LLM Chat（自动路由到合适的模型）
  │     ├── 无 tool_calls → 返回文本，存储记忆，触发学习
  │     └── 有 tool_calls → 执行工具，收集结果，继续循环
  │
  └──→ 超过最大迭代 → 请求中间总结
```

**关键特性**：
- **总超时保护**：`max_iterations × default_timeout` 秒后强制终止
- **记忆上下文注入**：将用户画像、近期记忆、相关记忆注入 system prompt
- **对话历史窗口**：保留最近 20 条对话历史
- **技能目录注入**：在 system prompt 中列出可用技能摘要

### 3.2 TaskPlanner（任务分解器）

文件：`src/agent/planner.py`

- 将复杂任务分解为 2-5 个子步骤
- 每个步骤指定使用哪个工具
- 健壮的 JSON 解析（自动提取 `[...]` 片段）

### 3.3 SubAgent + MultiAgentOrchestrator（子代理框架）

文件：`src/agent/subagent.py`

- **SubAgent**：独立轻量 Agent，执行特定子任务，最多 5 轮
- **MultiAgentOrchestrator**：分解 → 并行执行 → LLM 聚合
- 每个子任务使用独立 SubAgent 实例（避免并发冲突）

### 3.4 IntentClassifier（意图识别）

文件：`src/agent/intent.py`

- 基于关键词的简单意图分类
- 支持 10 种意图：email / calendar / weather / search / translate / data_analysis / news / finance / file / chat

---

## 4. LLM 多模型路由

### 4.1 LLMRouter

文件：`src/llm/router.py`

```
模型引用格式: "provider/model"
例: "zai/glm-5.1" → provider=zai, model=glm-5.1

路由逻辑:
  1. 解析 model_ref → (provider, model)
  2. 查找 provider 实例
  3. 未找到 → 降级到 ollama
  4. ollama 也不可用 → raise RuntimeError
```

**模型路由表**（config/default.yaml）：

| 任务类型 | 模型 |
|---------|------|
| 默认 / chat | zai/glm-5.1 |
| code | deepseek/deepseek-coder |
| analysis | ollama/qwen3.6:35b |
| research | google/gemini-2.5-pro |
| translation | ollama/qwen3.6:27b |
| classification | ollama/qwen3.5:4b |

### 4.2 FallbackChain

文件：`src/llm/fallback.py`

- 降级链：`zai/glm-5.1` → `openrouter/auto` → `ollama/qwen3.5:4b`
- 每个模型最多失败 3 次后跳过
- 使用 `asyncio.Lock`（线程安全懒初始化）防并发竞态

### 4.3 Provider 实现

| Provider | 文件 | 特点 |
|----------|------|------|
| OpenAICompatProvider | `openai_compat.py` | 通用 OpenAI SDK 兼容，覆盖 ZAI / DeepSeek / OpenAI |
| GeminiProvider | `gemini.py` | 通过 OpenAI 兼容接口访问 Gemini |
| OllamaProvider | `ollama.py` | 本地 Ollama，原生 API（/api/chat），复用 httpx 客户端 |
| ZhipuProvider | `zhipu.py` | 继承 OpenAICompatProvider，添加模型别名映射 |

**生命周期管理**：所有 Provider 实现 `async close()` 方法，应用关闭时通过 `router.close_all()` 统一释放连接池。

---

## 5. 四层记忆架构

```
┌─────────────────────────────────────────────────────┐
│                 MemoryManager                        │
├─────────────────────────────────────────────────────┤
│  L1 Working Memory   │ 内存对话缓冲区 (40 条窗口)    │
│  (WorkingMemory)     │ 每轮清空，用于上下文注入        │
├──────────────────────┤                              │
│  L2 Episodic Memory  │ SQLite + FTS5 全文搜索        │
│  (EpisodicMemory)    │ 保留 7 天，按重要性排序        │
├──────────────────────┤                              │
│  L3 Semantic Memory  │ SQLite + sqlite-vec 向量索引   │
│  (SemanticMemory)    │ LLM 摘要，长期保存             │
├──────────────────────┤                              │
│  L4 User Model       │ JSON 文件，结构化用户画像      │
│  (UserModel)         │ 深度合并默认值与保存值          │
└─────────────────────────────────────────────────────┘
```

### 5.1 工作记忆 (L1)

文件：`src/memory/working.py`

- 纯内存，`list[dict]` 格式
- 最大 40 条消息窗口
- 会话结束即清空

### 5.2 短期记忆 (L2)

文件：`src/memory/episodic.py`

- **存储**：SQLite + FTS5 虚拟表
- **自动过期**：7 天后清理低重要度条目（重要度 > 0.7 保留）
- **搜索**：FTS5 全文搜索 + 特殊字符清理
- **巩固**：高重要度条目可提升到 L3

### 5.3 长期语义记忆 (L3)

文件：`src/memory/semantic.py`

- **存储**：SQLite + sqlite-vec 向量索引 + FTS5
- **搜索**：向量余弦相似度 + FTS5 全文搜索双模式
- **预筛选优化**：向量搜索时先按重要性取 top-N 候选，避免全表扫描
- **可插拔 Embedding**：通过 `set_embedding_fn()` 注入

### 5.4 用户模型 (L4)

文件：`src/memory/user_model.py`

- JSON 文件持久化（`~/.myagent/memory/core/user_profile.json`）
- 深度合并默认值与保存值（`_deep_merge()`）
- 包含：身份信息、偏好设置、工作模式、兴趣、沟通风格

### 5.5 记忆巩固器

文件：`src/memory/consolidator.py`

- 定期将 L2 高重要度记忆提升到 L3
- LLM 生成摘要（如可用）
- L3 不可用时优雅降级

---

## 6. 工具系统

文件：`src/tools/`

### 6.1 内置工具清单

| 工具名 | 文件 | 功能 |
|--------|------|------|
| exec | `exec.py` | Shell 命令执行（安全检查 + 超时 kill） |
| read | `file_read.py` | 文件读取（路径沙箱） |
| write | `file_write.py` | 文件写入（路径沙箱 + 自动创建目录） |
| edit | `file_edit.py` | 精确文本替换（路径沙箱） |
| web_search | `web_search.py` | Brave Search API + DuckDuckGo 降级 |
| web_fetch | `web_fetch.py` | 网页抓取（SSRF 防护 + HTML 清理） |
| email_read | `email.py` | IMAP 读取邮件（连接 finally 关闭） |
| email_send | `email.py` | SMTP 发送邮件（环境变量凭据） |
| calendar | `calendar.py` | Google Calendar（list/search/create） |
| data_analysis | `data_analysis.py` | CSV/Excel/JSON 分析（异步读取 + query 安全化） |
| feishu_api | `feishu_api.py` | 飞书 API（发消息/搜索/文档） |
| deep_search | `deep_search.py` | 多源并行搜索 + 交叉验证 + LLM 综合分析 |

### 6.2 工具注册表

文件：`src/tools/__init__.py`

- `ToolRegistry` 管理所有工具的注册、Schema 生成、执行
- 所有工具继承 `BaseTool`，实现 `execute()` 和 `get_schema()`
- Schema 格式遵循 OpenAI function calling 标准

### 6.3 安全工具集

文件：`src/tools/_security_utils.py`

统一的安全检查逻辑，被 file_read / file_write / file_edit / web_fetch 共享：
- **文件沙箱**：`check_sandbox()` 白名单验证
- **SSRF 防护**：`is_safe_url()` 完整检查（IPv4/IPv6 私有地址、DNS 解析验证）

---

## 7. 技能系统（OpenClaw 兼容）

### 7.1 技能发现

文件：`src/skills/discovery.py`

按优先级扫描 5 个技能目录（高优先级覆盖低优先级）：

1. `~/.openclaw/workspace/skills` (最高)
2. `~/.openclaw/workspace/.agents/skills`
3. `~/.agents/skills`
4. `~/.openclaw/skills`
5. `~/.npm-global/lib/node_modules/openclaw/skills` (最低)

检查项：平台过滤、二进制依赖、pip 包依赖

### 7.2 SKILL.md 解析

文件：`src/skills/parser.py`

- 100% 兼容 agentskills.io 标准
- 解析 YAML frontmatter + Markdown body
- 支持 openclaw / clawdbot 两种 metadata 格式

### 7.3 技能执行

文件：`src/skills/executor.py`

- System prompt 只注入技能摘要列表（最多 50 个）
- 按需加载完整指令（避免 token 浪费）

### 7.4 技能注册表

文件：`src/skills/registry.py`

- 提供技能搜索、分类、推荐功能
- 在 Orchestrator 中初始化并注册所有已发现技能

---

## 8. 安全体系

### 8.1 命令安全

文件：`src/security.py`

`SecurityManager.check_command()` 在 exec 工具执行前检查 **21 种危险命令模式**：

```
rm -rf /, rm -rf ~, dd if=, mkfs, :(){ fork bomb
find / -delete, curl|sh, python -c subprocess, nc -e (reverse shell)
msfconsole, /etc/shadow, iptables -F, kill -9 1, chmod 777 /
```

### 8.2 内部端点认证

- HMAC-SHA256 签名验证（`MYAGENT_INTERNAL_SECRET` 环境变量）
- 子进程签名 → 主进程异步验证（`await request.body()`）
- 未设置 secret 时拒绝所有内部请求

### 8.3 路径沙箱

文件：`src/tools/_security_utils.py`

文件工具限制在以下目录内操作：

```
~/.myagent/     — Agent 数据目录
~/AIspace/      — 项目工作区
~/.openclaw/    — OpenClaw 配置
<cwd>/          — 当前工作目录（动态获取）
```

### 8.4 SSRF 防护

- 阻止私有 IP（IPv4 RFC 1918 全段 + IPv6）
- 阻止云元数据端点（169.254.169.254 等）
- DNS 解析后验证 IP（防 DNS rebinding）
- 只允许 HTTP/HTTPS 协议

### 8.5 其他安全措施

| 措施 | 说明 |
|------|------|
| CORS 收紧 | 仅允许 localhost:8765 |
| 默认绑定 127.0.0.1 | Gateway 不暴露到网络 |
| Dashboard XSS 防护 | `textContent` + HTML 转义 |
| PII 脱敏 | 审计日志中自动脱敏（保留内网 IP） |
| 凭据环境变量 | 所有密钥通过 `${ENV_VAR}` 引用 |
| 子进程凭据 | app_secret 通过环境变量传递，不暴露在 /proc |

---

## 9. 通道架构

### 9.1 飞书通道（lark-oapi）

文件：`src/gateway/channels/feishu.py`

```
子进程 (lark-oapi Channel WebSocket)
  ↓ 收到消息
  ↓ HTTP POST + HMAC 签名
主进程 (/internal/feishu_message)
  ↓ 验证签名
  ↓ Agent 处理
  ↓ 回复消息
```

- **Token 管理**：实例变量 + 过期检查 + 提前 5 分钟刷新 + 并发锁
- **发送消息**：文本、回复、Markdown 卡片
- **Webhook 兼容**：同时支持传统 HTTP 回调模式

### 9.2 Telegram 通道（aiogram 3.x）

文件：`src/gateway/channels/telegram.py`

```
子进程 (aiogram Long Polling)
  ↓ 收到消息
  ↓ HTTP POST + HMAC 签名
主进程 (/internal/telegram_message)
  ↓ 验证签名
  ↓ 权限检查（admin_ids / allowed_groups）
  ↓ Agent 处理
  ↓ 回复消息
```

- **命令**：/start /help /status /skills /tools /history /reset
- **群组**：只处理 @bot 或回复 bot 的消息
- **对话历史**：每个 chat_id 维护独立历史（最多 100 条，截断到 60）
- **消息分段**：超过 4096 字符自动分段发送

### 9.3 CLI 通道（Rich TUI）

文件：`src/gateway/channels/cli.py`

- Rich Console 美化输出 + Markdown 渲染
- prompt_toolkit 交互输入
- 对话历史窗口 100 条（超过截断到 60）
- 支持 /status /skills 命令

---

## 10. 定时任务

文件：`src/scheduler/cron.py` + `src/scheduler/jobs/default.py`

- 基于 APScheduler 的 Cron 调度器
- 时区：Asia/Dubai
- 日志写入加 `asyncio.Lock` 防并发
- 日志格式：JSONL（按日期分文件）
- 默认任务：天气查询 + 邮件检查

---

## 11. 自学习循环

文件：`src/skills/learner.py`

```
任务完成
  ↓ 评估复杂度（工具调用数 + 多样性 + 结果长度 + 关键词）
  ↓ 复杂度 > 0.6 且 ≥ 3 次工具调用
  ↓ LLM 提炼 SKILL.md
  ↓ 保存到 _pending/ 目录
  ↓ 人工审核 → approve/reject
```

- 学习日志原子写入（tempfile + rename）
- 内存中日志截断（>200 条 → 截断到 100）

---

## 12. 项目目录结构

```
myagent/
├── src/
│   ├── main.py                    # 入口：CLI / Gateway / Status / Tools / Skills
│   ├── config.py                  # 配置加载（YAML + .env + ${VAR} 解析）
│   ├── security.py                # 安全管理器（命令检查 + PII 脱敏 + 审计日志）
│   │
│   ├── agent/
│   │   ├── orchestrator.py        # 核心 ReAct 编排器
│   │   ├── planner.py             # 任务分解
│   │   ├── subagent.py            # 子代理 + 多代理并行
│   │   └── intent.py              # 意图分类
│   │
│   ├── llm/
│   │   ├── router.py              # 多模型路由 + close_all()
│   │   ├── fallback.py            # 降级链（asyncio.Lock 线程安全）
│   │   └── providers/
│   │       ├── base.py            # LLMProvider 基类 + LLMResponse + ToolCall
│   │       ├── openai_compat.py   # OpenAI 兼容（覆盖 ZAI/DeepSeek/OpenAI）
│   │       ├── gemini.py          # Google Gemini（OpenAI 兼容接口）
│   │       ├── ollama.py          # Ollama 本地（原生 API + embed）
│   │       └── zhipu.py           # 智谱 GLM（继承 OpenAICompat + 别名映射）
│   │
│   ├── gateway/
│   │   ├── server.py              # FastAPI Gateway + 路由 + HMAC 认证
│   │   ├── dashboard.py           # Web Dashboard HTML
│   │   └── channels/
│   │       ├── cli.py             # CLI 通道（Rich TUI）
│   │       ├── feishu.py          # 飞书通道（lark-oapi 子进程）
│   │       └── telegram.py        # Telegram 通道（aiogram 子进程）
│   │
│   ├── memory/
│   │   ├── manager.py             # 四层记忆管理器
│   │   ├── working.py             # L1 工作记忆（内存）
│   │   ├── episodic.py            # L2 短期记忆（SQLite + FTS5）
│   │   ├── semantic.py            # L3 长期记忆（SQLite + 向量 + FTS5）
│   │   ├── user_model.py          # L4 用户模型（JSON）
│   │   └── consolidator.py        # 记忆巩固器
│   │
│   ├── tools/
│   │   ├── __init__.py            # ToolRegistry 工具注册表
│   │   ├── base.py                # BaseTool + ToolResult 基类
│   │   ├── _security_utils.py    # 共享安全工具（沙箱 + SSRF）
│   │   ├── exec.py                # Shell 执行
│   │   ├── file_read.py           # 文件读取
│   │   ├── file_write.py          # 文件写入
│   │   ├── file_edit.py           # 文件编辑
│   │   ├── web_search.py          # 网络搜索
│   │   ├── web_fetch.py           # 网页抓取
│   │   ├── email.py               # 邮件读写
│   │   ├── calendar.py            # 日历
│   │   ├── data_analysis.py       # 数据分析
│   │   ├── feishu_api.py          # 飞书 API
│   │   ├── deep_search.py         # 深度搜索
│   │   └── search_engine.py       # 并行搜索引擎
│   │
│   ├── skills/
│   │   ├── discovery.py           # 技能发现器
│   │   ├── parser.py              # SKILL.md 解析器
│   │   ├── executor.py            # 技能执行器
│   │   ├── registry.py            # 技能注册表（搜索/分类/推荐）
│   │   └── learner.py             # 自学习循环
│   │
│   └── scheduler/
│       ├── cron.py                # Cron 调度器
│       └── jobs/
│           └── default.py         # 默认定时任务
│
├── config/
│   └── default.yaml               # 默认配置文件
├── docs/                          # 文档
├── .env.example                   # 环境变量模板
├── .gitignore                     # Git 忽略规则
├── pyproject.toml                 # 项目依赖（pip install -e .）
├── requirements.txt               # 依赖备用列表
├── docker-compose.yaml            # Docker 部署
├── run.sh                         # 启动脚本
└── Dockerfile                     # 容器构建
```

---

## 13. 技术选型决策

| 决策 | 选型 | 理由 |
|------|------|------|
| 飞书 SDK | lark-oapi | 官方 SDK，WebSocket 长连接，无需公网 |
| Telegram SDK | aiogram 3.x | MIT 协议，纯异步，轻量 |
| LLM 接口 | OpenAI SDK (AsyncOpenAI) | 兼容最广（ZAI/DeepSeek/Gemini/Ollama） |
| 数据库 | SQLite | 单用户场景无需外部数据库，支持 FTS5 + sqlite-vec |
| Web 框架 | FastAPI | 异步原生，自动 API 文档，WebSocket 支持 |
| 子进程 | multiprocessing.Process | 简单可靠，daemon=True 自动清理 |
| 配置格式 | YAML + .env | 结构化配置 + 敏感信息分离 |

---

## 14. 配置系统

### 14.1 配置加载流程

```
.env 文件 → os.environ（支持引号值）
  ↓
default.yaml → yaml.safe_load
  ↓
${ENV_VAR} → _resolve_env() 正则替换
  ↓
dataclass 类型化 → AgentConfig
```

### 14.2 环境变量

```bash
# .env 文件（必须设置的关键变量）
MYAGENT_INTERNAL_SECRET=***       # 内部端点 HMAC 签名密钥
ZAI_API_KEY=***                   # 智谱 API
GOOGLE_API_KEY=***                # Google/Gemini API
BRAVE_SEARCH_API_KEY=***          # Brave Search
TAVILY_API_KEY=***                # Tavily 搜索
FEISHU_APP_ID=***                 # 飞书 App ID
FEISHU_APP_SECRET=***             # 飞书 App Secret
TELEGRAM_BOT_TOKEN=***            # Telegram Bot Token
GMAIL_ADDRESS=***                 # Gmail 邮箱
GMAIL_APP_PASSWORD=***            # Gmail 应用专用密码
MAIL_163_ADDRESS=***              # 163 邮箱
163_IMAP_PASSWORD=***             # 163 IMAP 授权码
OPENAI_API_KEY=***                # OpenAI API
DEEPSEEK_API_KEY=***              # DeepSeek API
```

---

## 15. 开发路线图

### ✅ 已完成（v0.4.2）

- [x] 核心 ReAct Agent + LLM 多模型路由
- [x] 四层记忆架构（Working + Episodic + Semantic + UserModel）
- [x] 12 个内置工具
- [x] OpenClaw Skills 兼容（SKILL.md 解析 + 发现 + 执行）
- [x] 三通道接入（CLI + 飞书 + Telegram）
- [x] 子进程隔离架构
- [x] HMAC 内部认证
- [x] 安全加固（命令检查、路径沙箱、SSRF 防护、XSS 防护）
- [x] 自学习循环
- [x] 定时任务
- [x] Web Dashboard
- [x] 三轮代码审查 69 项修复

### 🔲 规划中

- [ ] 多用户支持（用户隔离、会话管理）
- [ ] OAuth 集成（Google Calendar、飞书权限）
- [ ] 向量 Embedding 接入（Ollama embed / OpenAI embed）
- [ ] Agent-to-Agent 通信协议
- [ ] 语音输入输出
- [ ] RAG 知识库（文档上传 + 检索增强）
- [ ] 插件市场（社区技能共享）

---

> **设计**: MyAgent 🤖 | **审核**: Author | **日期**: 2026-06-02（v3.0）
>
> 工作目录：`~/AIspace/myagent/`
