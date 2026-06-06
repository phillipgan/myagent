FROM python:3.11-slim

LABEL maintainer="MyAgent"
LABEL description="MyAgent - Personal Office Assistant"

WORKDIR /app

# 系统依赖 / System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ripgrep \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖 / Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 应用代码 / Application code
COPY src/ ./src/
COPY config/ ./config/
COPY skills/ ./skills/
COPY pyproject.toml .

# workspace 数据目录 / Workspace data directories
RUN mkdir -p /app/workspace/memory/core \
    /app/workspace/memory/episodic \
    /app/workspace/memory/semantic \
    /app/workspace/sessions \
    /app/workspace/logs/scheduler \
    /app/workspace/skills \
    /app/workspace/search_reports

# 环境变量 / Environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 5196

# 默认启动 Gateway / Default: start Gateway mode
CMD ["python", "-m", "src.main", "gateway", "--port", "5196", "--log", "INFO"]
