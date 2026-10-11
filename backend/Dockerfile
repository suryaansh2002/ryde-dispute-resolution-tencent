FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.7.12 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYDANTIC_AI_NO_BANNER=1

# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
# policy_rag reads data_generation/fixtures/policy_chunks.json at runtime.
COPY data_generation ./data_generation

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
# Render sets $PORT; default to 8000 for local runs.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers"]
