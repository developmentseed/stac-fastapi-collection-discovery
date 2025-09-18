# STAC Collection Discovery API

![](./assets/logo.svg)

A collection-search-only STAC API that aggregates collection search results from multiple upstream STAC APIs. This API provides collection discovery functionality only - it does not support item search operations.

## Features

- Combines collection search results from multiple upstream STAC APIs
- Supports standard STAC collection search parameters (bbox, datetime, limit, fields, sortby, filter, free text)
- Token-based pagination across multiple APIs
- Health check endpoint for monitoring upstream API availability and collection-search capability

## Running it locally

### Run the server with uvicorn

Set the required environment variable with comma-separated STAC API URLs:

```bash
export UPSTREAM_API_URLS=https://stac.eoapi.dev,https://stac.maap-project.org
```

Run the server:

```bash
uv run python -m uvicorn stac_fastapi.collection_discovery.app:app --host 0.0.0.0 --port 8000
```

### Run the server with Docker

Run the docker network (STAC Collection Discovery API + STAC Browser)

```bash
docker compose up
```

This will bring the API up at `http://localhost:8000` and a STAC Browser instance at `http://localhost:8080`.
