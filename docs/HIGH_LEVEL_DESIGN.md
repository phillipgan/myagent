<h1 align="center">
  📐 MyAgent High-Level Design
</h1>

<p align="center">
  <strong>Architecture & Design Specification</strong><br>
  Version 0.5.1 · June 2026
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Status-Active-green.svg" alt="Status: Active">
  <img src="https://img.shields.io/badge/Python-3.11+-blue.svg" alt="Python">
</p>

---

## Table of Contents

- [1. Executive Summary](#1-executive-summary)
- [2. Design Goals](#2-design-goals)
- [3. System Architecture](#3-system-architecture)
- [4. Core Subsystems](#4-core-subsystems)
  - [4.1 Agent Orchestrator (ReAct Loop)](#41-agent-orchestrator-react-loop)
  - [4.2 LLM Router & Fallback Chain](#42-llm-router--fallback-chain)
  - [4.3 Tool Registry](#43-tool-registry)
  - [4.4 Skill System](#44-skill-system)
  - [4.5 Four-Layer Memory](#45-four-layer-memory)
  - [4.6 Multi-Agent Orchestration](#46-multi-agent-orchestration)
  - [4.7 Gateway & Channel Integration](#47-gateway--channel-integration)
  - [4.8 Channel Watchdog](#48-channel-watchdog)
  - [4.9 Scheduler](#49-scheduler)
  - [4.10 Security Module](#410-security-module)
- [5. Data Flow](#5-data-flow)
- [6. Deployment Topology](#6-deployment-topology)
- [7. Configuration Model](#7-configuration-model)
- [8. Security Architecture](#8-security-architecture)
- [9. Extension Points](#9-extension-points)
- [10. Design Decisions & Trade-offs](#10-design-decisions--trade-offs)

---

## 1. Executive Summary

**MyAgent** is a self-hosted, personal office AI assistant built in Python. It combines a **ReAct (Reason-Act) agent loop** with **OpenClaw-compatible skill discovery**, **multi-LLM routing**, a **four-layer memory system**, and **multi-channel messaging** (CLI, Feishu, Telegram) into a single deployable unit.

The system is designed for a **single power user** — not multi-tenant SaaS — which simplifies auth, data isolation, and scaling requirements while enabling deep personalization through long-term memory and skill learning.

### Key Metrics

| Metric | Value |
|---|---|
| Built-in Tools | 12 |
| Discovered Skills | 200+ (OpenClaw ecosystem) |
| Memory Layers | 4 (working → episodic → semantic → user profile) |
| LLM Providers | 5 (Zhipu, DeepSeek, Google, OpenAI, Ollama/local) |
| Message Channels | 3 (CLI, Feishu, Telegram) |
| Channel Watchdog | Auto-restart with exponential backoff |
| Max ReAct Iterations | 60 |
| Default Port | 5196 |

---

## 2. Design Goals

| # | Goal | How |
|---|---|---|
| **G1** | **Local-first & Private** | Default bind `127.0.0.1`; PII detection/redaction; audit logging; secrets in `.env` |
| **G2** | **Model Agnostic** | `provider/model` routing; fallback chain; any OpenAI-compatible API |
| **G3** | **Skill Ecosystem** | OpenClaw `SKILL.md` format; priority-ordered discovery; auto-learning |
| **G4** | **Always Available** | systemd service; Docker with health check; auto-restart on failure |
| **G5** | **Deeply Personal** | Four-layer memory; user model persistence; context-aware responses |
| **G6** | **Secure by Default** | HMAC-protected internal endpoints; dangerous command blocking; no external exposure |

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Message Channels                            │
│   ┌──────────┐    ┌──────────────┐    ┌───────────────┐            │
│   │   CLI    │    │    Feishu    │    │   Telegram    │            │
│   │(prompt_  │    │ (lark-oapi  │    │  (aiogram     │            │
│   │ toolkit) │    │  WebSocket) │    │   polling)    │            │
│   └────┬─────┘    └──────┬───────┘    └──────┬────────┘            │
│        │                 │ (subprocess)  │ (subprocess)             │
│        │                 ▼               ▼                          │
│        │          ┌──────────────────────────┐                      │
│        └─────────►│    Gateway (FastAPI)      │◄── REST / WS        │
│                   │  ┌────────────────────┐  │                      │
│                   │  │  HMAC Verification  │  │                      │
│                   │  └────────────────────┘  │                      │
│                   │  ┌────────────────────┐  │                      │
│                   │  │  Scheduler (cron)   │  │                      │
│                   │  └────────────────────┘  │                      │
│                   └────────────┬─────────────┘                      │
└────────────────────────────────┼────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Agent Orchestrator                              │
│                                                                      │
│   ┌──────────────────────────────────────────────────────────┐      │
│   │                    ReAct Loop                             │      │
│   │                                                           │      │
│   │   System Prompt ──► LLM ──► Tool Calls? ──► Execute ──┐ │      │
│   │        ▲                                │             │  │      │
│   │        └────────── Observe ◄────────────┘             │  │      │
│   │                                                       │  │      │
│   │   Max: 60 iterations | Timeout: sum(timeout × 60)     │  │      │
│   └───────────────────────────────────────────────────────┘  │      │
│                                                               │      │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │      │
│   │  LLM Router   │  │Tool Registry │  │  Skill Executor  │  │      │
│   │  ┌──────────┐ │  │  (12 tools)  │  │  (200+ skills)   │  │      │
│   │  │ Fallback │ │  │              │  │                  │  │      │
│   │  │  Chain   │ │  │ exec         │  │  Discovery       │  │      │
│   │  └──────────┘ │  │ file_read    │  │  Parser          │  │      │
│   │               │  │ file_write   │  │  Registry        │  │      │
│   │ zai/glm-5.1   │  │ file_edit    │  │  Learner         │  │      │
│   │ deepseek/coder │  │ web_search   │  │                  │  │      │
│   │ ollama/qwen3.6 │  │ web_fetch    │  └──────────────────┘  │      │
│   │ google/gemini  │  │ email        │                        │      │
│   └──────────────┘  │ calendar     │                        │      │
│                      │ data_analysis│                        │      │
│   ┌──────────────┐  │ deep_search  │                        │      │
│   │   Memory      │  │ feishu_api   │                        │      │
│   │   Manager     │  └──────────────┘                        │      │
│   │               │                                          │      │
│   │ L1: Working   │  ┌──────────────┐                        │      │
│   │ L2: Episodic  │  │  Security    │                        │      │
│   │ L3: Semantic  │  │  Manager     │                        │      │
│   │ L4: User Model│  │              │                        │      │
│   └──────────────┘  │ PII Detect   │                        │      │
│                      │ Cmd Block    │                        │      │
│                      │ Audit Log    │                        │      │
│                      └──────────────┘                        │      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 4. Core Subsystems

### 4.1 Agent Orchestrator (ReAct Loop)

The orchestrator is the heart of MyAgent. It implements the **ReAct (Reason + Act)** pattern — an iterative loop where the LLM reasons about a problem, selects and invokes tools, observes results, and continues until the task is complete.

**Flow:**

```
User Message
     │
     ▼
┌─────────────────────────┐
│ Build System Prompt      │  ← user context + skill catalog + memory
│ Load Tool Schemas        │
└────────────┬────────────┘
             │
             ▼
      ┌─────────────┐
      │  LLM Call    │◄──────────────────────┐
      └──────┬──────┘                         │
             │                                │
      ┌──────▼──────┐                         │
      │ Tool Calls?  │                        │
      └──┬───────┬──┘                         │
         │       │                            │
     No  │       │ Yes                        │
         │       ▼                            │
         │  ┌────────────┐                    │
         │  │ Execute     │                   │
         │  │ Tool(s)     │                   │
         │  └─────┬──────┘                    │
         │        │                           │
         │        ▼                           │
         │  ┌────────────┐                    │
         │  │ Append to   │                   │
         │  │ Messages    │───────────────────┘
         │  └────────────┘
         │
         ▼
  ┌──────────────┐
  │ Store to      │
  │ Memory        │
  │ Trigger       │
  │ Learning      │
  └──────────────┘
```

**Key behaviors:**

| Aspect | Detail |
|---|---|
| **Max iterations** | 60 (configurable via `max_iterations`) |
| **Global timeout** | `max_iterations × default_timeout` seconds |
| **Iteration exhaustion** | Requests a summary from the LLM instead of failing silently |
| **Conversation history** | Last 20 messages injected for context |
| **Memory integration** | Context retrieved before each conversation; interaction stored after completion |
| **Learning trigger** | After task completion, `LearningLoop.on_task_complete()` evaluates complexity |

**System Prompt Assembly:**

```
┌─────────────────────────────────────┐
│         System Prompt               │
│                                     │
│  1. Role & Rules (static)           │
│  2. User Context (from L4 memory)   │
│  3. Skill Catalog (summaries only)  │
│  4. Memory Context (episodic recall)│
│                                     │
└─────────────────────────────────────┘
```

---

### 4.2 LLM Router & Fallback Chain

#### LLM Router

The router maps `provider/model` references to concrete LLM provider clients. It supports **task-type routing** — different task categories are sent to different models.

**Routing Resolution Order:**

```
1. Explicit model parameter?         → Use it
2. Task type in routes table?        → Use routed model
3. Default model                     → Fallback
```

**Model Reference Format:**

All model references use the `provider/model` convention:

```
zai/glm-5.1          →  Zhipu AI → GLM-5.1
deepseek/deepseek-coder  →  DeepSeek → Coder
ollama/qwen3.6:35b   →  Local Ollama → Qwen 3.6 (35B)
google/gemini-2.5-pro →  Google → Gemini 2.5 Pro
```

**Provider Initialization:**

```
┌──────────────────────────────────────────┐
│           Provider Registry              │
│                                          │
│  ┌─────────┐  ┌──────────┐  ┌────────┐  │
│  │  Zhipu   │  │ DeepSeek │  │ Google │  │
│  │ (ZAI)    │  │          │  │        │  │
│  └─────────┘  └──────────┘  └────────┘  │
│  ┌─────────┐  ┌──────────────────────┐  │
│  │ OpenAI  │  │ Ollama (always init) │  │
│  │         │  │ localhost:11434      │  │
│  └─────────┘  └──────────────────────┘  │
└──────────────────────────────────────────┘
```

> Ollama is always initialized as a local fallback, even if not explicitly configured.

#### Fallback Chain

The `FallbackChain` provides **automatic degradation** when the primary model fails. It implements a **three-strike rule**: after 3 consecutive failures, a model is temporarily removed from rotation.

```
Request → zai/glm-5.1 ──── fail ──► openrouter/auto ──── fail ──► ollama/qwen3.5:4b
              │                          │                            │
              └── strike += 1            └── strike += 1              └── last resort
              └── strike < 3: retry      └── strike < 3: retry
              └── strike ≥ 3: skip       └── strike ≥ 3: skip
```

**Thread safety:** Uses `asyncio.Lock` with lazy initialization guarded by `threading.Lock` to prevent race conditions in multi-threaded contexts.

---

### 4.3 Tool Registry

All tools implement a common `BaseTool` interface and return results in OpenAI function-calling format.

**Tool Interface:**

```python
class BaseTool(ABC):
    @abstractmethod
    def get_schema(self) -> dict:
        """Return OpenAI function-calling schema."""

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given arguments."""

@dataclass
class ToolResult:
    success: bool
    output: str
    error: str = ""
```

**Built-in Tools:**

| Tool | Input | Output | Security Notes |
|---|---|---|---|
| `exec` | Shell command string | stdout/stderr | Blocked by dangerous command patterns |
| `file_read` | File path | File contents | — |
| `file_write` | Path + content | Write confirmation | — |
| `file_edit` | Path + old/new text | Edit confirmation | — |
| `web_search` | Query string | Search results | API key required |
| `web_fetch` | URL | Extracted text/markdown | — |
| `email` | To/subject/body | Send confirmation | App password required |
| `calendar` | Date/query | Events list | — |
| `data_analysis` | Data + question | Analysis results | — |
| `deep_search` | Topic | Multi-source report | Aggregates multiple searches |
| `feishu_api` | Doc/message ID | Content/message | App credentials required |

---

### 4.4 Skill System

The skill system provides **dynamic extensibility** through OpenClaw-compatible `SKILL.md` files. Skills are discovered at startup, injected as summaries into the system prompt, and loaded fully on demand.

#### 4.4.1 Skill Discovery

Skills are scanned from multiple directory roots in **reverse priority order** (lowest first), so higher-priority roots override by name:

```
Priority (High → Low):
  ~/.openclaw/workspace/skills        ← User custom (overrides all)
  ~/.openclaw/workspace/.agents/skills
  ~/.agents/skills
  ~/.openclaw/skills
  ~/.npm-global/lib/node_modules/openclaw/skills  ← Bundled (base)
```

**Eligibility checks:**

```
For each SKILL.md found:
  ├── Platform filter (os: macos, linux, windows)
  ├── Binary dependencies (requires.bins → shutil.which)
  ├── Any-binary check (requires.anyBins → at least one exists)
  └── Python packages (requires.pip → importlib.util.find_spec)
```

#### 4.4.2 Skill Parser

Parses the OpenClaw `SKILL.md` format with YAML frontmatter:

```yaml
---
name: my-skill
description: "What this skill does"
metadata:
  openclaw:
    emoji: "🔧"
    os: [linux, macos]
    requires:
      bins: [ffmpeg, curl]
      pip: [pandas>=2.0]
---

# Skill Instructions

Step-by-step instructions for the agent...
```

**Parsed into:**

```
OpenClawSkill
  ├── meta: SkillMeta (name, description, emoji, os_filter, requires...)
  ├── instructions: str (Markdown body)
  ├── skill_dir: Path (directory containing SKILL.md)
  └── source: str (workspace | managed | personal | bundled)
```

#### 4.4.3 Skill Executor

**Two-phase loading** to minimize token consumption:

| Phase | When | What |
|---|---|---|
| **Catalog** | Startup → system prompt | Name + emoji + one-line description (max 50 skills) |
| **Full load** | On demand (when LLM matches a skill) | Complete markdown instructions injected into conversation |

#### 4.4.4 Skill Learner (Self-Learning)

The learning loop automatically extracts new skills from complex task patterns:

```
Task Complete
     │
     ▼
Assess Complexity (0-1)
  ├── Tool call count (≥5: +0.3)
  ├── Tool diversity (≥3 unique: +0.2)
  ├── Result length (>1000 chars: +0.2)
  └── Keywords (analyze/report/research: +0.1)
     │
     ▼
Complexity > 0.6 AND tool_calls ≥ 3?
     │
  Yes│          No → Log only
     ▼
LLM extracts SKILL.md
     │
     ▼
Save to _pending/ (awaiting human review)
```

Pending skills can be approved (moved to skill directory) or rejected (deleted).

---

### 4.5 Four-Layer Memory

Inspired by human cognition, the memory system operates in four layers with distinct storage, retrieval, and retention characteristics:

```
┌────────────────────────────────────────────────────────────┐
│                     Memory Manager                          │
│                                                             │
│  L1: Working Memory          L2: Episodic Memory           │
│  ┌───────────────────┐      ┌───────────────────────┐      │
│  │ Storage: In-memory │      │ Storage: SQLite + FTS5 │      │
│  │ Content: Messages  │      │ Content: Summaries     │      │
│  │ Retention: Session │      │ Retention: 7 days      │      │
│  │ Capacity: Last 20  │      │ Search: Full-text      │      │
│  │ Access: FIFO       │      │ Access: FTS5 + recency │      │
│  └───────────────────┘      └───────────────────────┘      │
│                                                             │
│  L3: Semantic Memory         L4: User Model                 │
│  ┌───────────────────┐      ┌───────────────────────┐      │
│  │ Storage: sqlite-vec│      │ Storage: JSON files    │      │
│  │ Content: Vectors   │      │ Content: User profile  │      │
│  │ Retention: Infinite│      │ Retention: Infinite    │      │
│  │ Search: Cosine sim │      │ Access: Key-value      │      │
│  │ Embeddings: bge-m3 │      │ Patterns, preferences  │      │
│  └───────────────────┘      └───────────────────────┘      │
│                                                             │
└────────────────────────────────────────────────────────────┘
```

**Memory Operations:**

| Operation | Layers Involved | Flow |
|---|---|---|
| **Store** | L1, L2, L4 | Working ← messages; Episodic ← summary + importance score; UserModel ← patterns |
| **Recall** | L2, L3 | Episodic FTS5 search + recent items; Semantic vector similarity |
| **Context Build** | All | User profile + recent episodic + related memories → injected into system prompt |
| **Consolidation** | L2 → L3 | High-importance episodic entries become vector embeddings |

**Importance Scoring (L2):**

```
base = 0.3
+ 0.2  if tool calls present
+ 0.1  if response > 500 chars
+ 0.15 if keywords found (remember, important, decide, analyze...)
= min(score, 1.0)
```

**Retention Policy:**

- L1: Session-scoped, cleared on restart
- L2: 7 days default; entries with importance ≤ 0.7 cleaned up; importance > 0.7 retained indefinitely
- L3: Infinite retention (vector embeddings)
- L4: Infinite retention (JSON files)

---

### 4.6 Multi-Agent Orchestration

For complex tasks, MyAgent can spawn **sub-agents** that run in parallel:

```
Complex Task
     │
     ▼
Task Decomposition (LLM)
     │
     ├── "Sub-task 1"
     ├── "Sub-task 2"
     └── "Sub-task 3"
          │
          ▼
  ┌────────────────────────────┐
  │   asyncio.gather()         │
  │                            │
  │  SubAgent1  SubAgent2  SubAgent3   ← Independent instances
  │  (5 iter)  (5 iter)   (5 iter)    ← Limited iterations
  │    │          │          │
  └────┼──────────┼──────────┘
       │          │          │
       ▼          ▼          ▼
  Result Aggregation (LLM)
       │
       ▼
  Coherent Final Response
```

**Key design choices:**
- Each `SubAgent` is a **fresh instance** — no shared state between sub-agents
- Sub-agents are limited to **5 iterations** (vs. 60 for the main agent)
- Results are aggregated by a dedicated LLM call that synthesizes all sub-results
- If decomposition fails, falls back to executing the original task as-is

---

### 4.7 Gateway & Channel Integration

The gateway is a **FastAPI** application that serves as the central message dispatcher. Channels run as **independent subprocesses** that communicate with the gateway via internal HTTP endpoints.

```
┌─────────────────────────────────────────────────────────┐
│                    Gateway (FastAPI)                      │
│                                                          │
│  Endpoints:                                              │
│  ├── GET  /              → Dashboard (SPA HTML)          │
│  ├── WS   /ws            → WebSocket real-time chat      │
│  ├── GET  /api/status    → Agent status (local only)     │
│  ├── GET  /api/scheduler → Cron job status               │
│  ├── POST /webhook/feishu       → Feishu webhook         │
│  ├── POST /internal/feishu_message   → HMAC-protected    │
│  └── POST /internal/telegram_message → HMAC-protected    │
│                                                          │
│  Security:                                               │
│  ├── CORS (localhost only)                               │
│  ├── HMAC signature on internal endpoints                │
│  └── Local bind (127.0.0.1)                             │
└─────────────────────────────────────────────────────────┘
         ▲                              ▲
         │ HTTP (HMAC signed)           │ HTTP (HMAC signed)
    ┌────┴─────┐                  ┌─────┴──────┐
    │  Feishu  │                  │  Telegram   │
    │  Subproc │                  │  Subproc    │
    │          │                  │             │
    │lark-oapi │                  │  aiogram    │
    │WebSocket │                  │  polling    │
    └──────────┘                  └─────────────┘
```

**Why subprocesses?**

- Channel SDKs (lark-oapi, aiogram) have their own event loops and lifecycle
- Subprocess isolation prevents a channel crash from taking down the entire gateway
- Each subprocess posts messages to the gateway's internal endpoint, which dispatches to the `AgentOrchestrator`

**Initialization Guard:**

The `AgentOrchestrator` is initialized **lazily** on first request, protected by `asyncio.Lock` with double-check pattern. Initialization runs in `asyncio.to_thread()` to avoid blocking the event loop during SQLite setup and skill scanning.

---

### 4.8 Channel Watchdog

The Channel Watchdog is a **background supervisor** that monitors all registered channel subprocesses and automatically restarts them on failure. It addresses a critical operational gap: when a channel subprocess crashes (e.g., due to DNS resolution failures, network outages, or SDK errors), the gateway previously had no mechanism to detect or recover from the failure.

**Architecture:**

```
┌─────────────────────────────────────────────────────────────┐
│                    ChannelWatchdog                            │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Background asyncio.Task (every 30 min)               │   │
│  │                                                       │   │
│  │  for each registered channel:                         │   │
│  │    ├── is_alive()?                                    │   │
│  │    │   ├── Yes → reset failure counter                │   │
│  │    │   └── No  → check backoff window                 │   │
│  │    │       ├── In backoff → skip                      │   │
│  │    │       ├── Over max_retries → cooldown            │   │
│  │    │       └── Eligible → stop() → start() → restart │   │
│  │    └── Update next_retry_after (exponential backoff)  │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
│  Registered Channels:                                        │
│  ├── Feishu:  lark-oapi WebSocket subprocess                 │
│  └── Telegram: aiogram polling subprocess                    │
│                                                              │
│  Exponential Backoff:                                        │
│  Retry 1: 60s  | Retry 2: 120s | Retry 3: 240s              │
│  Retry 4: 480s | Retry 5: 960s → cooldown (30 min cycle)    │
└─────────────────────────────────────────────────────────────┘
```

**Key Parameters:**

| Parameter | Default | Description |
|---|---|---|
| `check_interval` | 1800s (30 min) | How often to poll channel health |
| `max_retries` | 5 | Max consecutive restart attempts before cooldown |
| `backoff_base` | 60s | Base delay for exponential backoff |
| `backoff_max` | 3600s (1 hour) | Ceiling for backoff delay |

**Backoff Sequence:**

``
Failure 1 → wait 60s   → restart
Failure 2 → wait 120s  → restart
Failure 3 → wait 240s  → restart
Failure 4 → wait 480s  → restart
Failure 5 → wait 960s  → restart
Failure 6 → cooldown (next 30-min cycle, counter reset)
```

**Status Reporting:**

The watchdog exposes its state via `/api/status`:

```json
{
  "watchdog": {
    "enabled": true,
    "check_interval": 1800,
    "channels": {
      "feishu": { "alive": true, "consecutive_failures": 0, "total_restarts": 1 },
      "telegram": { "alive": false, "consecutive_failures": 3, "total_restarts": 5, "next_retry_in": 240 }
    }
  }
}
```

**Registration:**

Channels are registered during `_init_agent()` via `watchdog.register(name, start_fn, stop_fn, is_alive_fn)`. The watchdog starts after all channels have been launched in `Gateway.start()`.

**Configuration (`config/default.yaml`):**

```yaml
channels:
  watchdog:
    enabled: true
    check_interval: 1800   # 30 minutes
    max_retries: 5
    backoff_base: 60
    backoff_max: 3600
```

---

### 4.9 Scheduler

Built on **APScheduler** (AsyncIO mode), supporting standard cron expressions.

```
┌──────────────────────────────────────┐
│          CronScheduler               │
│                                      │
│  register_job(name, cron, handler)   │
│         │                            │
│         ▼                            │
│  CronTrigger.from_crontab(cron)      │
│         │                            │
│         ▼                            │
│  APScheduler.add_job(_run_job)       │
│         │                            │
│    ┌────▼────┐                        │
│    │ Execute │                        │
│    │ handler │                        │
│    └────┬────┘                        │
│         ▼                            │
│  Write to JSONL log (async safe)     │
└──────────────────────────────────────┘
```

- Log writes use `asyncio.to_thread()` to avoid blocking
- File writes are protected by `asyncio.Lock` (lazy-initialized, thread-safe)
- Misfire grace time: 300 seconds

---

### 4.10 Security Module

The security module operates at three levels:

```
┌─────────────────────────────────────────────────────┐
│                 SecurityManager                      │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │  PII Detection & Redaction                     │  │
│  │                                                │  │
│  │  Patterns: email, phone, credit_card, SSN,     │  │
│  │            IP address, API keys                │  │
│  │                                                │  │
│  │  Redaction: partial mask or full replacement   │  │
│  │  Exceptions: internal IPs preserved (10.x,     │  │
│  │             172.16-31.x, 192.168.x, 127.x)    │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │  Dangerous Command Blocking                    │  │
│  │                                                │  │
│  │  rm -rf /, dd, mkfs, fork bomb,               │  │
│  │  curl|sh, reverse shell, iptables -F,          │  │
│  │  /etc/shadow, kill -9 1, metasploit            │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ┌────────────────────────────────────────────────┐  │
│  │  Audit Logging                                 │  │
│  │                                                │  │
│  │  Format: JSONL (one entry per line)            │  │
│  │  Path: ~/.myagent/logs/audit_YYYY-MM-DD.jsonl  │  │
│  │  Content: timestamp + action + redacted details│  │
│  └────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

---

## 5. Data Flow

### 5.1 Request Lifecycle (Gateway Mode)

```
User sends message (Feishu/Telegram/CLI)
     │
     ▼
Channel receives message
     │
     ▼ (subprocess)
HTTP POST to /internal/{channel}_message
     │
     ▼
HMAC signature verification
     │
     ├── Fail → 401 Unauthorized
     │
     ▼ (pass)
Lazy-init AgentOrchestrator (once)
     │
     ▼
agent.process_message(text)
     │
     ├── Build system prompt (user context + skills + memory)
     ├── Load tool schemas
     │
     ▼
ReAct Loop (up to 60 iterations)
     │
     ├── LLM call (routed to appropriate model)
     │   ├── Tool calls → execute → append results → continue loop
     │   └── No tool calls → final response
     │
     ▼
Store interaction to memory (L1 + L2 + L4)
Trigger learning assessment
     │
     ▼
Return response to channel
     │
     ▼
Channel sends reply to user
```

### 5.2 Context Assembly

```
┌──────────────────────────────────────────────────────────┐
│                Context Assembly for LLM                   │
│                                                           │
│  ┌────────────────────┐  ┌──────────────────────────┐    │
│  │ System Prompt       │  │ Conversation History     │    │
│  │                     │  │ (last 20 messages)       │    │
│  │ • Role definition   │  │                          │    │
│  │ • Tool descriptions │  │ [user, assistant, tool]  │    │
│  │ • User context (L4) │  │                          │    │
│  │ • Skill catalog     │  └──────────────────────────┘    │
│  │ • Memory context    │                                   │
│  │   - Recent (L2)     │  ┌──────────────────────────┐    │
│  │   - Related (L2/L3) │  │ Current User Message     │    │
│  └────────────────────┘  └──────────────────────────┘    │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

---

## 6. Deployment Topology

### Option A: Bare Metal (systemd)

```
┌──────────────────────────────────────────────┐
│              Linux Host (DGX Spark)           │
│                                              │
│  systemd: myagent-gateway.service            │
│    └── python -m src.main gateway            │
│        ├── Agent (in-process)                │
│        ├── Feishu subprocess                 │
│        ├── Telegram subprocess               │
│        ├── Watchdog (background task)        │
│        └── Scheduler (in-process)            │
│                                              │
│  Data: ~/.myagent/                           │
│    ├── memory/                               │
│    │   ├── episodic/   (SQLite)              │
│    │   ├── semantic/   (sqlite-vec)          │
│    │   └── core/       (JSON user model)     │
│    ├── logs/                                 │
│    │   ├── gateway.log                       │
│    │   ├── scheduler/                        │
│    │   └── audit_*.jsonl                     │
│    ├── skills/                               │
│    └── sessions/                             │
│                                              │
│  Network: 127.0.0.1:5196                     │
└──────────────────────────────────────────────┘
```

### Option B: Docker

```
┌──────────────────────────────────────────────┐
│           Docker Container                    │
│                                              │
│  Image: python:3.11-slim                     │
│  App: /app                                   │
│  Port: 5196                                  │
│                                              │
│  Volumes:                                    │
│    ./config      → /app/config               │
│    myagent-data → /root/.myagent             │
│    ./skills     → /root/.myagent/skills/custom│
│                                              │
│  Health Check: curl http://localhost:5196/    │
│  Restart: unless-stopped                     │
│  Timezone: Asia/Dubai                        │
└──────────────────────────────────────────────┘
```

### Option C: CLI (Development)

```
┌──────────────────────────────────────────────┐
│         Terminal (interactive)                │
│                                              │
│  $ conda activate myagent                    │
│  $ python -m src.main cli                    │
│                                              │
│  No gateway, no channels.                    │
│  Direct stdin/stdout interaction.            │
│  Memory and skills still active.             │
└──────────────────────────────────────────────┘
```

---

## 7. Configuration Model

```
.env                          config/default.yaml
(strongly typed secrets)      (behavioral parameters)
─────────────────────         ──────────────────────────
ZAI_API_KEY=***               agent:
DEEPSEEK_API_KEY=***            name: "MyAgent"
GOOGLE_API_KEY=***              workspace: "~/.myagent"
FEISHU_APP_ID=cli_xxx           max_iterations: 60
FEISHU_APP_SECRET=xxx           default_timeout: 30
TELEGRAM_BOT_TOKEN=xxx
GMAIL_APP_PASSWORD=xxx        models:
MYAGENT_INTERNAL_SECRET=xxx     default: "zai/glm-5.1"
                                 routes: { ... }
                              providers:
                                zai: { base_url, api_key }
                                ollama: { base_url }
                              channels:
                                feishu: { enabled, app_id, ... }
                                telegram: { enabled, bot_token, ... }
                              memory:
                                db_path, retention_days, ...
                              logging:
                                level: "INFO"
```

**Resolution chain:**

1. `.env` loaded into environment variables
2. `config/default.yaml` loaded
3. `${ENV_VAR}` references in YAML resolved via `_resolve_env()`
4. Final `AgentConfig` dataclass produced

---

## 8. Security Architecture

### Threat Model

| Threat | Mitigation |
|---|---|
| **Network exposure** | Default bind `127.0.0.1`; CORS restricted to localhost |
| **Internal endpoint abuse** | HMAC-SHA256 signature required on all `/internal/*` endpoints |
| **Shell injection** | 17 dangerous command patterns blocked by regex |
| **PII leakage** | 6 PII pattern detectors with automatic redaction in audit logs |
| **Credential exposure** | `.env` is `.gitignore`d; secrets never in YAML |
| **Subprocess compromise** | Channels run in isolated subprocesses |
| **Model failure** | Three-strike fallback chain across providers |

### Defense in Depth

```
Layer 1: Network      → localhost bind, CORS whitelist
Layer 2: Transport    → HMAC signature on internal communication
Layer 3: Application  → PII detection, command blocking
Layer 4: Data         → Audit logging with automatic redaction
Layer 5: Process      → Subprocess isolation for channels
Layer 6: Resilience   → Channel watchdog with auto-restart
Layer 7: LLM          → Fallback chain for resilience
```

---

## 9. Extension Points

| Extension | How | Where |
|---|---|---|
| **New LLM Provider** | Add `OpenAICompatProvider` config in `providers` section | `config/default.yaml` |
| **New Tool** | Implement `BaseTool`, register in `ToolRegistry.__init__` | `src/tools/` |
| **New Skill** | Create `SKILL.md` in any `skill_roots` directory | Any skill directory |
| **New Channel** | Implement channel class with `start/stop/set_handler` + register to watchdog | `src/gateway/channels/` |
| **New Memory Layer** | Add to `MemoryManager`, integrate into `store_interaction` / `get_context` | `src/memory/` |
| **New Cron Job** | Register with `CronScheduler.register_job()` | `src/scheduler/jobs/` |
| **Custom Prompt** | Modify `SYSTEM_PROMPT_TEMPLATE` | `src/agent/orchestrator.py` |

---

## 10. Design Decisions & Trade-offs

| Decision | Rationale | Trade-off |
|---|---|---|
| **Single-user design** | Eliminates multi-tenant complexity; enables deep personalization | Cannot serve multiple users simultaneously |
| **Subprocess channels** | Isolates SDK crashes; clean lifecycle management | Slight overhead; requires HMAC for internal auth |
| **Two-phase skill loading** | Keeps system prompt small (~50 skill summaries) | Full skill instructions loaded mid-conversation, adding latency |
| **SQLite for memory** | Zero-config; file-based; FTS5 built-in | Not suitable for high-concurrency or distributed deployment |
| **ReAct loop over plan-then-execute** | More flexible; handles unexpected tool results naturally | Can be token-expensive for simple tasks; no global plan visibility |
| **Three-strike fallback** | Simple; auto-recovers when provider comes back | May be too aggressive for transient failures |
| **Channel watchdog (30-min)** | Self-healing without manual intervention; exponential backoff prevents aggressive reconnects | 30-min polling means up to 30-min detection latency |
| **Lazy agent initialization** | Fast gateway startup; no blocking on first request | First request has cold-start latency (skill scanning, DB init) |
| **YAML + .env config** | Familiar; separation of secrets and behavior | Two files to manage; no hot-reload |
| **asyncio throughout** | Native async for HTTP, WebSocket, LLM calls | Requires careful lock management; mixing sync/async code |
| **Skill auto-learning** | Reduces manual skill creation over time | Learned skills need human review; quality varies |

---

<p align="center">
  <em>Document version 0.5.1 · Last updated June 2026</em>
</p>
