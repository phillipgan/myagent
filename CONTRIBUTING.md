# Contributing to MyAgent | 贡献指南

Thank you for your interest in MyAgent! Contributions are warmly welcomed.

感谢你对 MyAgent 的关注！欢迎参与贡献。

---

## 🐛 Reporting Bugs | 报告 Bug

1. Search [existing Issues](../../issues) to avoid duplicates
2. Open a new Issue with the **Bug Report** template
3. Include:
   - Steps to reproduce the issue
   - Expected vs. actual behavior
   - Environment info (OS, Python version, MyAgent version)

## 💡 Suggesting Features | 功能建议

1. Open an Issue with the **Feature Request** label
2. Describe the use case and expected behavior
3- Mockups or examples are appreciated

## 🔧 Submitting Code | 提交代码

### Development Setup

```bash
# Clone your fork
git clone https://github.com/<your-username>/myagent.git
cd myagent

# Create conda environment
conda create -n myagent python=3.12 -y
conda activate myagent

# Install in editable mode
pip install -e .

# Copy config
cp .env.example .env
# Edit .env with your API keys
```

### Workflow

1. **Fork** the repository
2. **Create a branch** from `main`:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make changes** and commit:
   ```bash
   git commit -m "feat: add amazing feature"
   ```
4. **Push** to your fork:
   ```bash
   git push origin feature/your-feature-name
   ```
5. **Open a Pull Request** against `main`

### Commit Convention

| Prefix | Usage |
|--------|-------|
| `feat:` | New feature |
| `fix:` | Bug fix |
| `docs:` | Documentation only |
| `refactor:` | Code refactoring |
| `test:` | Adding or fixing tests |
| `chore:` | Build, CI, tooling changes |
| `security:` | Security improvements |

Example: `feat: add support for WhatsApp channel`

## 📝 Code Style | 代码风格

- **Python 3.11+** with type hints
- **Async-first**: use `async/await` for I/O operations
- **Docstrings**: every public function/class should have a docstring
- **Line length**: 100 characters max
- **Imports**: stdlib → third-party → local (isort style)

## 🧪 Testing | 测试

```bash
# Run tests (when available)
python -m pytest tests/ -v

# Quick smoke test
python -m src.main tools   # List all tools
python -m src.main skills  # List discovered skills
```

## 📦 Project Structure

```
src/
├── main.py              # Entry point
├── config.py            # Configuration loader
├── security.py          # Security module
├── agent/               # Agent core (planner, orchestrator, intent)
├── llm/                 # LLM providers + routing
├── memory/              # Four-layer memory system
├── tools/               # Built-in tools
├── skills/              # Skill discovery & execution
├── scheduler/           # Cron jobs
└── gateway/             # HTTP server + channels
```

## 🔄 Release Process

1. Update version in `pyproject.toml`
2. Update `CHANGELOG.md`
3. Create a git tag: `git tag v0.x.x`
4. Push tag: `git push origin v0.x.x`
5. GitHub will auto-create a Release

## 📄 License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).

---

Questions? Feel free to open an Issue or reach out.

有疑问？随时提 Issue 或联系维护者。
