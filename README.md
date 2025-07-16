# STAC Collection Discovery API

A STAC API that aggregates collection search results from multiple STAC APIs into a single unified interface. This API provides collection discovery functionality only - it does not support item search operations.

## Features

- Combines collection search results from multiple STAC APIs
- Supports standard STAC collection search parameters (bbox, datetime, limit, fields, sortby, filter, free text)
- Token-based pagination across multiple APIs
- Health check endpoint for monitoring child API availability

## Usage

Set the required environment variable with comma-separated STAC API URLs:

```bash
export CHILD_API_URLS=https://stac.eoapi.dev,https://stac.maap-project.org
```

Run the server:

```bash
uv run uvicorn stac_fastapi.collection_discovery.app:app --host 0.0.0.0 --port 8080
```

## Development

Install dependencies:

```bash
uv sync
```

Install pre-commit hooks:

```bash
uv run pre-commit install
```

Run tests:

```bash
uv run pytest
```
