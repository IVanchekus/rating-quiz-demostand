FROM ghcr.io/astral-sh/uv:0.6.17 AS uv
FROM python:3.12-slim
COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
RUN groupadd --system quiz && useradd --system --gid quiz quiz
USER quiz
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
