#!/bin/bash
# MyAgent 启动脚本 — 自动使用 conda 环境的 Python
# L-10: 使用相对路径，适配不同部署环境

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 检测 conda 环境
if [ -n "$CONDA_PREFIX" ]; then
    PYTHON="$CONDA_PREFIX/bin/python"
elif [ -f "$HOME/miniconda3/envs/myagent/bin/python" ]; then
    PYTHON="$HOME/miniconda3/envs/myagent/bin/python"
else
    PYTHON="$(which python3 2>/dev/null || echo python)"
fi

cd "$SCRIPT_DIR"

case "${1:-cli}" in
  cli)
    exec "$PYTHON" -m src.main cli "${@:2}"
    ;;
  gateway)
    exec "$PYTHON" -m src.main gateway "${@:2}"
    ;;
  status)
    exec "$PYTHON" -m src.main status "${@:2}"
    ;;
  tools)
    exec "$PYTHON" -m src.main tools "${@:2}"
    ;;
  skills)
    exec "$PYTHON" -m src.main skills "${@:2}"
    ;;
  *)
    exec "$PYTHON" -m src.main "$@"
    ;;
esac
