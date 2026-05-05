# ─── 构建阶段 ────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# 安装 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# 先复制依赖文件，利用 Docker 层缓存
COPY pyproject.toml uv.lock* ./

# 安装依赖到虚拟环境（不安装项目本身）
RUN uv sync --frozen --no-install-project --no-dev

# 安装 Playwright 浏览器
RUN uv run playwright install chromium

# ─── 运行阶段 ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# 安装 uv 和运行时系统依赖
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN apt-get update && apt-get install -y --no-install-recommends \
    # Playwright 运行时依赖
    libnss3 libnspr4 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 从构建阶段复制虚拟环境
COPY --from=builder /app/.venv ./.venv
COPY --from=builder /root/.cache/ms-playwright /root/.cache/ms-playwright

# 复制应用代码
COPY . .

# 激活虚拟环境路径
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

# 数据目录
RUN mkdir -p /app/data/annual_reports

EXPOSE 8000
