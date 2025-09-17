FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  apt-get update && apt-get install -y git && \
  uv sync --locked --no-dev --no-install-project --extra server

COPY README.md pyproject.toml uv.lock src /app/

# Sync the project
RUN --mount=type=cache,target=/root/.cache/uv \
  uv sync --extra server --locked

CMD ["uv", "run", "gunicorn", "-k", "uvicorn.workers.UvicornWorker", "stac_fastapi.collection_discovery.app:app", "--bind", "0.0.0.0:8000", "--workers", "1"]

