# Changelog

All notable changes to MyAgent will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.5.2] - 2026-06-06

### Added
- 15 bundled skills (web-search-plus, chart-image, code-mentor, code-share, summarize, weather, brave-images, github, gh-issues, diagram-maker, tavily-search, translator, ceo-advisor, autonomous-research, ai-writing-assistant-cn)
- Three-tier skill system: bundled → OpenClaw → custom
- Docker hybrid mode: bundled skills by default + optional OpenClaw mount
- CHANGELOG.md
- CONTRIBUTING.md

### Fixed
- Version number unified to 0.5.1+ across all files
- .gitignore: added *.pem, *.key, *.crt, *.p12, *.pfx, credentials.json
- systemd service: added EnvironmentFile for .env loading
- LICENSE: updated copyright holder
- README: added Contributing section

## [0.5.1] - 2026-06-05

### Added
- ReAct Agent Loop with multi-step tool calling (up to 60 iterations)
- Multi-LLM routing: GLM-5 for chat, DeepSeek for code, Qwen for analysis, Gemini for research
- OpenClaw Skills compatible engine — auto-discover and execute `SKILL.md` files
- Multi-channel messaging: CLI, Feishu (飞书/Lark), Telegram
- 12 built-in tools: file I/O, web search/fetch, email, calendar, data analysis, code execution, deep search, Feishu API, and more
- Four-layer memory architecture: Working → Episodic (SQLite/FTS5) → Semantic (vector DB) → User Profile
- Skill auto-learning from complex task patterns
- Channel Watchdog with exponential backoff auto-restart
- Docker deployment with health checks
- systemd service support
- Web Dashboard with real-time WebSocket chat
- SSRF protection (private IP + DNS rebinding validation)
- HMAC authentication for internal endpoints
- Path sandbox for file operations
- 21 dangerous command pattern blocking for shell execution

### Changed
- Upgraded from v0.4.2 to v0.5.1 with full architecture redesign

## [0.4.2] - 2026-04-XX

### Added
- Initial pre-release version
- Basic agent loop and tool framework
