# STAC Collection Discovery API

![](./assets/logo.svg)

A collection-search-only STAC API that aggregates collection search results from multiple upstream STAC APIs. This API provides collection discovery functionality only - it does not support item search operations.

## Features

- Combines collection search results from multiple upstream STAC APIs
- Supports standard STAC collection search parameters (bbox, datetime, limit, fields, sortby, filter, free text)
- Token-based pagination across multiple APIs
- Health check endpoint for monitoring upstream API availability and collection-search capability
- Graceful handling of upstream API failures with the `strict` query parameter. When `strict=false` (default), failed upstream APIs are skipped and the problematic URLs are returned in the `X-Failed-Upstream-Apis` response header. When `strict=true`, the search fails fast if any upstream API errors.

## Running it locally

### Run the server with uvicorn

Set the required environment variable with comma-separated STAC API URLs:

```bash
export UPSTREAM_API_URLS=https://stac.eoapi.dev,https://stac.maap-project.org
```

Run the server:

```bash
uv run python -m uvicorn stac_fastapi.collection_discovery.app:app \
  --host 0.0.0.0 \
  --port 8000 \
  --reload
```

### Run the server with Docker

Run the docker network (STAC Collection Discovery API + STAC Browser)

```bash
docker compose up
```

This will bring the API up at `http://localhost:8000` and a STAC Browser instance at `http://localhost:8080`.

## LLM-assisted search

When `LLM_PROVIDER` and `LLM_API_KEY` are configured (and, for place names,
`GEOCODING_SERVICE_URL`), two helper endpoints are available. They are stateless;
the client performs the search itself. The provider SDKs are an optional extra:
install them with `uv sync --extra llm` (or
`pip install "stac-fastapi-collection-discovery[llm]"`); the Docker image already
includes them.

1. `POST /discovery/interpret` with `{"query": "wildfires in California 2023"}`
   returns `{"q": [...], "bbox": [...], "datetime": "...", "warnings": []}`.
2. For each term in `q`, `GET /collections?q=<term>&bbox=...&datetime=...&limit=100`,
   following `next` links for more. Merge the results, keeping each collection's
   `self` link as its `ref` and the list of terms that returned it as `matched_terms`.
3. `POST /discovery/rank` with the original query and the merged candidates
   (`{"ref", "id", "title", "matched_terms"}`; at most
   `RERANK_MAX_REQUEST_CANDIDATES`, default 200) returns them best first
   with a `score` (0-10) and a plain-text `reason`. The top
   `RERANK_CANDIDATE_COUNT` (default 50) candidates by term coverage are scored; the
   rest are returned after the scored ones with `score: null`.

See `streamlit_app.py` for a complete reference client.
