# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

# Pin the installer as well as the application dependencies in uv.lock.
COPY --from=ghcr.io/astral-sh/uv:0.11.0 /uv /uvx /usr/local/bin/

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1 \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app/backend \
    ARBITER_DB=/data/arbiter.sqlite3 \
    ARBITER_DEMO_DATA_DIR=/data

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# The two ignore files allow Python source and public seed fixtures only.
# Editable installation retains app.py's parents[2] == /app resource root.
COPY backend/ ./backend/
RUN uv sync --frozen --no-dev

# Explicit runtime assets; no personal state, reports, videos, or uploads.
COPY frontend/index.html frontend/landing.html frontend/app.js frontend/styles.css frontend/landing.css ./frontend/
COPY frontend/download.html frontend/download.js ./frontend/
COPY frontend/downloads/culture-fit-source.zip frontend/downloads/culture-fit-skill.zip ./frontend/downloads/
COPY experiments/results/latest/summary.json ./experiments/results/latest/summary.json
COPY slack-app-manifest.json ./slack-app-manifest.json

# Railway must attach its persistent volume at /data at runtime.
RUN mkdir -p /data/visitors
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8080') + '/api/health', timeout=3).read()"

# The shell expands Railway's runtime PORT, then exec forwards shutdown signals.
CMD ["sh", "-c", "exec uvicorn arbiter.deployment:app --host 0.0.0.0 --port \"${PORT:-8080}\" --workers 1"]
