# syntax=docker/dockerfile:1.7
FROM node:22-bookworm-slim AS web
WORKDIR /src/webui
COPY webui/package.json webui/package-lock.json ./
RUN npm ci
COPY webui/ ./
COPY pixel-office/ ../pixel-office/
RUN npm run build

FROM python:3.12-slim AS wheel
WORKDIR /src
RUN python -m pip install --no-cache-dir build
COPY pyproject.toml README.md LICENSE ./
COPY traderharness/ traderharness/
COPY examples/replays/ examples/replays/
COPY --from=web /src/traderharness/ui/static/ traderharness/ui/static/
RUN python -m build --wheel

FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRADERHARNESS_HOME=/data
RUN groupadd --system traderharness \
    && useradd --system --gid traderharness --home /app traderharness \
    && mkdir -p /data \
    && chown traderharness:traderharness /data
COPY --from=wheel /src/dist/*.whl /tmp/
RUN wheel="$(find /tmp -name 'traderharness-*.whl' -print -quit)" \
    && python -m pip install --no-cache-dir "${wheel}[llm,data,ui]" \
    && rm -f /tmp/*.whl
USER traderharness
WORKDIR /app
VOLUME ["/data"]
EXPOSE 8000
HEALTHCHECK --interval=20s --timeout=3s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2)"
CMD ["python", "-m", "uvicorn", "traderharness.server.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
