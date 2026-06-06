**English** | [中文](README_CN.md)

# 🤖 MyAgent

**A self-hosted personal office assistant powered by LLMs.**

ReAct Agent Loop · OpenClaw Skills Compatible · Multi-Channel Messaging · Four-Layer Memory · Extensible Tools

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)]()
[![License](https://img.shields.io/badge/License-MIT-green.svg)]()
[![Status](https://img.shields.io/badge/Status-v0.5.1-yellow.svg)]()

---

## Table of Contents

- [✨ Features](#-features)
- [📋 Prerequisites](#-prerequisites)
- [🚀 Quick Start](#-quick-start)
- [⚙️ Configuration](#️-configuration)
- [🔌 Channel Setup](#-channel-setup)
- [🧭 Running Modes](#-running-modes)
- [🛠️ Built-in Tools](#️-built-in-tools)
- [🧠 Memory System](#-memory-system)
- [🎓 Skills System](#-skills-system)
- [🔐 Security](#-security)
- [🏗️ Architecture](#️-architecture)
- [🐳 Docker Deployment](#-docker-deployment)
- [📖 FAQ](#-faq)

---

## ✨ Features

| Feature | Description |
|---------|-------------|
| **ReAct Agent Loop** | Reason-Act iterative loop with multi-step tool calling (up to 60 iterations) |
| **Multi-LLM Routing** | Route tasks to the best model: GLM-5 for chat, DeepSeek for code, Qwen for analysis, Gemini for research |
| **OpenClaw Skills Compatible** | Auto-discover and execute community skills from `SKILL.md` files |
| **Multi-Channel** | Chat via CLI, Feishu (飞书/Lark), or Telegram |
| **12 Built-in Tools** | File I/O, web search/fetch, email, calendar, data analysis, code execution, deep search, and more |
| **Four-Layer Memory** | Working → Episodic (SQLite/FTS5) → Semantic (vector DB) → User Profile (persistent JSON) |
| **Skill Auto-Learning** | Automatically extracts new skills from complex task patterns |
| **Channel Watchdog** | Auto-restart crashed channels with exponential backoff |
| **Production Ready** | systemd service, Docker support, health checks, structured logging |

---

## 📋 Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Python | ≥ 3.11 | Tested on 3.11/3.12 |
| Conda | Any | Recommended for environment isolation |
| Git | Any | For cloning the repo |
| (Optional) Docker | ≥ 20.x | For containerized deployment |
| (Optional) Ollama | Any | For local LLM inference |

---

## 🚀 Quick Start

### 1. Clone & Set Up Environment

```bash
git clone https://github.com/your-username/myagent.git
cd myagent

# Create conda environment
conda create -n myagent python=3.12 -y
conda activate myagent
```

### 2. Install Dependencies

```bash
pip install -e .
```

Or using requirements.txt:

```bash
pip install -r requirements.txt
```

### 3. Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` and fill in your API keys (see [⚙️ Configuration](#️-configuration) for details).

### 4. Run It

```bash
# Interactive CLI mode
python -m src.main cli

# Gateway mode (Web Dashboard + Feishu + Telegram)
python -m src.main gateway --port 5196 --log INFO
```

---

## ⚙️ Configuration

MyAgent uses a layered config system: **`.env`** (secrets) + **`config/default.yaml`** (behavior).

### Environment Variables (`.env`)

| Variable | Purpose | Required |
|----------|---------|----------|
| `MYAGENT_INTERNAL_SECRET` | HMAC signing key for internal endpoints | ✅ |
| `ZAI_API_KEY` | Zhipu GLM API key (default model provider) | ✅ (default model) |
| `GOOGLE_API_KEY` | Google/Gemini API key | Optional |
| `OPENAI_API_KEY` | OpenAI API key | Optional |
| `DEEPSEEK_API_KEY` | DeepSeek API key | Optional |
| `BRAVE_SEARCH_API_KEY` | Brave Search API key | Optional (falls back to DuckDuckGo) |
| `TAVILY_API_KEY` | Tavily Search API key | Optional |
| `FEISHU_APP_ID` | Feishu App ID | Feishu channel |
| `FEISHU_APP_SECRET` | Feishu App Secret | Feishu channel |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token | Telegram channel |
| `GMAIL_ADDRESS` | Gmail address for email tools | Email feature |
| `GMAIL_APP_PASSWORD` | Gmail app-specific password | Email feature |

**Example `.env` file:**

```bash
# Required
MYAGENT_INTERNAL_SECRET=your_random_secret_string_here
ZAI_API_KEY=your_zhipu_api_key_here

# Search
BRAVE_SEARCH_API_KEY=your_brave_api_key_here

# Feishu
FEISHU_APP_ID=cli_xxxxxxxxxxxxxxxx
FEISHU_APP_SECRET=your_feishu_app_secret

# Telegram
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz

# Email
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

### How to Get API Keys

<details>
<summary>🔑 Zhipu GLM (Default LLM Provider)</summary>

1. Visit [https://open.bigmodel.cn](https://open.bigmodel.cn)
2. Register an account
3. Go to API Keys → Create new key
4. Copy the key to `ZAI_API_KEY` in `.env`

</details>

<details>
<summary>🔍 Brave Search API</summary>

1. Visit [https://api.search.brave.com](https://api.search.brave.com)
2. Sign up for a free account (2,000 queries/month free)
3. Subscribe to the Search API
4. Copy your API key to `BRAVE_SEARCH_API_KEY` in `.env`

</details>

<details>
<summary>🤖 Ollama (Local LLM)</summary>

1. Install Ollama: `curl -fsSL https://ollama.com/install.sh | sh`
2. Pull a model: `ollama pull qwen3.6:35b`
3. Ollama runs on `http://localhost:11434` — no API key needed
4. Update `config/default.yaml` to use `ollama/qwen3.6:35b` as default if desired

</details>

### Model Routing (`config/default.yaml`)

```yaml
models:
  default: "zai/glm-5.1"
  routes:
    chat: "zai/glm-5.1"               # General conversation
    code: "deepseek/deepseek-coder"    # Code generation
    analysis: "ollama/qwen3.6:35b"     # Data analysis (local)
    research: "google/gemini-2.5-pro"  # Deep research
    translation: "ollama/qwen3.6:27b"  # Translation
    classification: "ollama/qwen3.5:4b" # Fast classification
```

### Auto-Fallback Chain

If a provider fails, MyAgent automatically downgrades:

```
zai/glm-5.1 → openrouter/auto → ollama/qwen3.5:4b
```

Each model gets 3 strikes before being skipped. Thread-safe via `asyncio.Lock`.

---

## 🔌 Channel Setup

### Feishu (飞书/Lark) Channel

<details>
<summary>📱 Setup Guide</summary>

**Prerequisite**: Create a Feishu app at [https://open.feishu.cn](https://open.feishu.cn)

1. **Create App**: Go to Feishu Open Platform → Create Enterprise Self-built App
2. **Enable Bot**: In the app settings, enable the "Bot" (机器人) capability
3. **Get Credentials**: Copy the **App ID** and **App Secret**
4. **Configure Permissions**: Add the following permissions:
   - Send messages (`im:message:send_as_bot`)
   - Receive messages (`im:message`)
   - Read group info (`im:chat:readonly`)
5. **Configure `.env`**:

```bash
FEISHU_APP_ID=cli_xxxxxxxxxxxxxxxx
FEISHU_APP_SECRET=your_app_secret_here
```

6. **Enable in config**:

```yaml
channels:
  feishu:
    enabled: true
    app_id: "${FEISHU_APP_ID}"
    app_secret: "${FEISHU_APP_SECRET}"
```

**Architecture**: Runs as a subprocess with lark-oapi WebSocket long connection. No public IP or webhook URL needed.

</details>

### Telegram Channel

<details>
<summary>✈️ Setup Guide</summary>

**Prerequisite**: Create a Telegram Bot via [@BotFather](https://t.me/BotFather)

1. **Create Bot**: Message `@BotFather` on Telegram → `/newbot` → follow prompts
2. **Get Token**: Copy the Bot Token (format: `123456789:ABCdef...`)
3. **Get Your User ID**: Message `@userinfobot` to get your numeric user ID
4. **Configure `.env`**:

```bash
TELEGRAM_BOT_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
```

5. **Enable in config**:

```yaml
channels:
  telegram:
    enabled: true
    bot_token: "${TELEGRAM_BOT_TOKEN}"
    admin_ids: "123456789"          # Your Telegram user ID (comma-separated)
    allowed_groups: "-1001234567890" # Allowed group IDs (comma-separated, empty = all)
```

**Bot Commands**: `/start` `/help` `/status` `/skills` `/tools` `/history` `/reset`

**Group Usage**: The bot only responds when @mentioned or when replying to its messages.

</details>

### Email Setup

<details>
<summary>📧 Gmail App Password</summary>

1. Enable 2-Factor Authentication on your Google Account
2. Go to [Google Account Settings](https://myaccount.google.com) → Security → App Passwords
3. Generate a new app password (select "Mail" → "Other")
4. Copy the 16-character password (format: `xxxx xxxx xxxx xxxx`)
5. Configure `.env`:

```bash
GMAIL_ADDRESS=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx
```

</details>

---

## 🧭 Running Modes

### CLI Mode (Interactive Terminal)

```bash
python -m src.main cli
```

Rich-formatted terminal UI with command history and tab completion.

### Gateway Mode (API Server + Channels)

```bash
python -m src.main gateway --port 5196 --log INFO
```

Starts:
- **FastAPI server** on `127.0.0.1:5196`
- **WebSocket** endpoint at `/ws` for real-time chat
- **Web Dashboard** at `http://127.0.0.1:5196/`
- **Feishu + Telegram** channel subprocesses
- **Channel Watchdog** for auto-restart

### Utility Commands

```bash
python -m src.main status    # Show agent status (JSON)
python -m src.main tools     # List all registered tools
python -m src.main skills    # List all discovered skills
```

---

## 🛠️ Built-in Tools

| Tool | Description | Security |
|------|-------------|----------|
| `exec` | Execute shell commands | 21 dangerous pattern check, timeout kill |
| `file_read` | Read file contents | Path sandbox whitelist |
| `file_write` | Write/create files | Path sandbox + auto-mkdir |
| `file_edit` | Precise find-replace editing | Path sandbox |
| `web_search` | Brave Search + DuckDuckGo fallback | — |
| `web_fetch` | Fetch & extract web page content | SSRF protection (private IP + DNS validation) |
| `email_read` | Read emails via IMAP | Connection cleanup, search injection prevention |
| `email_send` | Send emails via SMTP | Env-var credentials, connection cleanup |
| `calendar` | Google Calendar (list/search/create) | HTTP status checking |
| `data_analysis` | CSV/Excel/JSON analysis | Async I/O, safe pandas query |
| `feishu_api` | Feishu docs & messages API | Env-var credentials, auto token refresh |
| `deep_search` | Multi-source parallel search | Cross-validation + LLM analysis |

---

## 🧠 Memory System

MyAgent implements a four-layer memory architecture inspired by human cognition:

```
┌─────────────────────────────────────────────────┐
│  L1: Working Memory                              │
│  In-memory session context (40-message window)    │
├─────────────────────────────────────────────────┤
│  L2: Episodic Memory                             │
│  SQLite + FTS5 full-text search                   │
│  Retention: 7 days (high-importance preserved)    │
├─────────────────────────────────────────────────┤
│  L3: Semantic Memory                             │
│  Vector embeddings (sqlite-vec) + FTS5            │
│  Long-term knowledge, similarity search           │
├─────────────────────────────────────────────────┤
│  L4: User Model                                  │
│  Persistent JSON profile & preferences            │
│  Deep understanding of the user                   │
└─────────────────────────────────────────────────┘
```

Memory context is automatically injected into every conversation — user profile, recent interactions, and relevant knowledge.

---

## 🎓 Skills System

MyAgent is **OpenClaw Skills Compatible**. Any `SKILL.md` file following the [agentskills.io](https://agentskills.io) format is auto-discovered and loaded.

### How It Works

1. **Discovery**: Scans configured `skill_roots` directories by priority
2. **Parsing**: Reads YAML frontmatter + markdown body
3. **Injection**: Skill summaries are injected into the system prompt
4. **On-Demand Loading**: Full instructions loaded when the LLM needs them

### Adding Custom Skills

MyAgent supports **three skill tiers** (priority high → low):

1. **Bundled Skills** (`./skills/`) — 15 curated skills shipped with the project (see below)
2. **OpenClaw Skills** (`~/.openclaw/workspace/skills/`, etc.) — auto-discovered if OpenClaw is installed
3. **Custom Skills** — add your own `SKILL.md` files anywhere in the skill roots

#### Bundled Skills (15)

| Skill | Description |
|-------|-------------|
| **web-search-plus** | Unified multi-engine search (Serper/Tavily/Exa/Perplexity) |
| **tavily-search** | AI-optimized web search via Tavily API |
| **brave-images** | Image search via Brave Search API |
| **chart-image** | Publication-quality chart generation |
| **diagram-maker** | SVG/HTML diagrams for architecture & flows |
| **summarize** | Summarize URLs, PDFs, audio, YouTube |
| **translator** | Professional translation (CN↔EN, CN↔JP, multi-lang) |
| **ai-writing-assistant-cn** | Chinese writing assistant (10 styles) |
| **code-mentor** | AI programming tutor & code review |
| **code-share** | Share code via GitHub Gist |
| **github** | GitHub CLI (issues, PRs, CI, API) |
| **gh-issues** | GitHub issue triage & auto-fix agents |
| **ceo-advisor** | Executive strategy & decision-making guidance |
| **autonomous-research** | Independent multi-source deep research |
| **weather** | Current weather & forecasts (no API key) |

#### Docker: Enable OpenClaw Skills

If OpenClaw is installed on the host, uncomment the mount lines in `docker-compose.yaml`:

```yaml
volumes:
  # ... bundled skills ...
  # Uncomment for OpenClaw skills:
  # - ~/.openclaw/workspace/skills:/root/.openclaw/workspace/skills:ro
  # - ~/.npm-global/lib/node_modules/openclaw/skills:/root/.npm-global/lib/node_modules/openclaw/skills:ro
```

Create a `SKILL.md` file in any skill root directory:

```yaml
---
name: my-custom-skill
description: "Does something useful"
metadata:
  openclaw:
    requires:
      - exec
      - file_read
---

# My Custom Skill

Step-by-step instructions for the agent to follow...

## Usage

When the user asks to do X, follow these steps:
1. First, ...
2. Then, ...
3. Finally, ...
```

### Skill Auto-Learning

MyAgent automatically learns from complex tasks (3+ tool calls). When a task is deemed complex enough, the LLM generates a new `SKILL.md` for future reuse.

---

## 🔐 Security

| Measure | Description |
|---------|-------------|
| **HMAC Authentication** | Internal endpoints signed with `MYAGENT_INTERNAL_SECRET` |
| **Path Sandbox** | File operations restricted to whitelisted directories |
| **SSRF Protection** | Blocks private IPs, cloud metadata endpoints, DNS rebinding |
| **Command Safety** | 21 dangerous command patterns blocked (rm -rf, fork bombs, reverse shells, etc.) |
| **Local Binding** | Gateway binds to `127.0.0.1` by default |
| **PII Redaction** | Audit logs automatically redact sensitive data |
| **CORS Lockdown** | Only localhost origins allowed |
| **XSS Prevention** | Dashboard uses `textContent` + HTML escaping |

---

## 🏗️ Architecture

```
                    Gateway (FastAPI)
                   http://127.0.0.1:5196
  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
  │ Dashboard │  │ WebSocket│  │ REST API │  │ Webhook  │
  └──────────┘  └──────────┘  └──────────┘  └──────────┘
         ┌───────────────────────────────────────┐
         │         Agent Orchestrator (ReAct)      │
         │  ┌───────────┐  ┌──────────────────┐   │
         │  │ LLM Router │  │ Fallback Chain    │   │
         │  │ + Provider │  │ (auto-downgrade)  │   │
         │  └───────────┘  └──────────────────┘   │
         │  ┌───────────┐  ┌──────────────────┐   │
         │  │ 12 Tools   │  │ 4-Layer Memory   │   │
         │  └───────────┘  └──────────────────┘   │
         │  ┌───────────┐  ┌──────────────────┐   │
         │  │ Skills     │  │ Auto-Learner     │   │
         │  └───────────┘  └──────────────────┘   │
         └───────────────────────────────────────┘
                    │
    ┌───────────────┼───────────────┐
    │               │               │
  Feishu         Telegram          CLI
  (subprocess)   (subprocess)    (main proc)
  WebSocket      Long Polling     Rich TUI
```

**Subprocess Isolation**: Feishu and Telegram run as isolated subprocesses. SDK crashes don't affect the main process. Communication via HMAC-signed HTTP callbacks.

**Channel Watchdog**: Monitors subprocess health every 30 minutes. Auto-restarts crashed channels with exponential backoff (60s → 120s → 240s → ... → 3600s max).

---

## 🐳 Docker Deployment

```bash
# Build & start
docker compose up -d

# View logs
docker compose logs -f myagent

# Stop
docker compose down
```

The container exposes port **5196** and mounts `./workspace` for persistent data.

---

## 📖 FAQ

**Q: Gateway startup error `MYAGENT_INTERNAL_SECRET not set`?**
A: Add `MYAGENT_INTERNAL_SECRET=<random_string>` to your `.env` file.

**Q: Telegram bot not responding?**
A: Check `TELEGRAM_BOT_TOKEN` is correct and `admin_ids` includes your Telegram user ID.

**Q: Feishu messages not getting replies?**
A: Verify the Feishu app has "Bot" capability enabled and credentials are correct.

**Q: Command blocked by security module?**
A: This is expected — the exec tool checks 21 dangerous command patterns. Ensure your command doesn't match any safety rule.

**Q: Ollama connection failed?**
A: Run `ollama list` to confirm Ollama is running. Default endpoint: `http://localhost:11434`.

**Q: How to add a new LLM provider?**
A: Add credentials to `.env`, add a provider entry in `config/default.yaml` under `providers:`, and optionally add a route in `models.routes:`.

---

## 🤝 Contributing

Contributions are welcome! Please read [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.
