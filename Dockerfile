# Get version from git
FROM alpine/git as git
WORKDIR /app
COPY .git /app/.git
RUN git describe --tags --always --dirty 2>/dev/null > /version || echo "0.1.0" > /version

FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# Copy version from git stage
COPY --from=git /version /version

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
  --mount=type=bind,source=uv.lock,target=uv.lock \
  --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
  apt-get update && apt-get install -y git && \
  uv sync --locked --no-dev --no-install-project --extra server

COPY README.md pyproject.toml uv.lock src /app/

# Set version from git and sync the project
RUN --mount=type=cache,target=/root/.cache/uv \
  export PDM_BUILD_SCM_VERSION=$(cat /version) && \
  uv sync --extra server --locked

CMD ["uv", "run", "gunicorn", "-k", "uvicorn.workers.UvicornWorker", "stac_fastapi.collection_discovery.app:app", "--bind", "0.0.0.0:8000", "--workers", "1"]

