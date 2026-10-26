# TerpScout backend: FastAPI server, scheduler/worker and sync pipeline in one process (one worker only).
# The web/ Next.js site is deployed on Vercel and is not part of this image.
FROM node:22-bookworm-slim AS node

FROM python:3.13-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \
    TERPSCOUT_PLAYWRIGHT_PATH=/opt/playwright/node_modules/playwright \
    TERPSCOUT_BROWSER_CHANNEL=chromium \
    TERPSCOUT_DB=/data/terpscout.db \
    TERPSCOUT_EVIDENCE=/data/evidence

# Node runtime for backend/browser_worker.cjs
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx

# Playwright + Chromium (with its system libraries), independent of web/node_modules.
# Keep this version in step with the browser the worker was tested against.
RUN mkdir -p /opt/playwright && cd /opt/playwright \
    && npm init -y >/dev/null && npm install playwright@1.56.1 \
    && npx playwright install --with-deps chromium \
    && rm -rf /var/lib/apt/lists/* /root/.npm

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY backend ./backend
COPY scripts ./scripts
COPY tests ./tests
COPY docs ./docs
COPY index.html ./

RUN useradd --create-home --uid 1000 terpscout && mkdir -p /data && chown terpscout /data
USER terpscout
VOLUME /data
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/docs', timeout=4)"

# Exactly one worker: a process lease prevents concurrent ingestion workers on one database.
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
