FROM python:3.14-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY spider ./spider
RUN uv sync --frozen --no-dev

FROM python:3.14-slim
RUN useradd --create-home app && mkdir /secrets && chown app /secrets
WORKDIR /app
COPY --from=build /app /app
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/healthz', timeout=2)"
CMD ["uvicorn", "spider.main:app", "--host", "0.0.0.0", "--port", "8000"]
