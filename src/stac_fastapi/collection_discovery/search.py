"""Federated collection search with per-term fan-out for free-text queries.

Upstream STAC catalogs implement the collection-search `q` parameter
inconsistently:

- NASA CMR ANDs comma-separated terms (multi-term q returns nothing)
- openveda accepts at most one multi-word phrase per request
- pgstac deployments (maap, eoapi) support comma-OR phrases
- many catalogs ignore `q` entirely

Issuing one request per term and merging results normalizes OR semantics
across all of them.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 10
REQUEST_TIMEOUT = 30.0


@dataclass
class CollectionMatch:
    """A collection returned by an upstream API, with provenance."""

    collection: dict[str, Any]
    """The STAC collection object."""

    source_api: str
    """Upstream API base URL that returned this collection."""

    matched_term: str | None
    """The search term that surfaced this collection (None if unfiltered)."""


@dataclass
class FederatedSearchResult:
    """Result of a federated collection search."""

    matches: list[CollectionMatch] = field(default_factory=list)
    """Merged, deduplicated collections across all upstream APIs."""

    per_api_counts: dict[str, int] = field(default_factory=dict)
    """Raw result count per upstream API (before dedupe)."""

    errors: dict[str, list[str]] = field(default_factory=dict)
    """Per-API error messages for failed term requests."""


async def _fetch_term(
    client: httpx.AsyncClient,
    api: str,
    term: str | None,
    base_params: dict[str, Any],
) -> tuple[str, str | None, list[dict[str, Any]], str | None]:
    """Fetch collections for a single search term from one upstream API.

    Multi-word phrases are retried wrapped in double quotes on failure
    (openveda rejects unquoted phrases; CMR rejects quoted ones).
    """
    params = dict(base_params)
    if term:
        params["q"] = term

    try:
        response = await client.get(f"{api}/collections", params=params)

        if response.status_code >= 400 and term and " " in term:
            params["q"] = f'"{term}"'
            response = await client.get(f"{api}/collections", params=params)

        response.raise_for_status()
        return api, term, response.json().get("collections", []), None
    except Exception as e:
        logger.warning(f"Upstream term search failed: {api} q={term}: {e}")
        return api, term, [], str(e)


async def federated_collection_search(
    apis: list[str],
    terms: list[str] | None = None,
    bbox: list[float] | None = None,
    datetime_range: str | None = None,
    limit: int = DEFAULT_LIMIT,
    timeout: float = REQUEST_TIMEOUT,
) -> FederatedSearchResult:
    """Search collections across multiple upstream STAC APIs.

    Issues one request per term per API (normalizing OR semantics across
    catalogs with divergent `q` implementations), then merges and dedupes
    by (api, collection id).

    Args:
        apis: Upstream STAC API base URLs
        terms: Free-text search terms; None/empty means one unfiltered
            request per API
        bbox: Bounding box [west, south, east, north]
        datetime_range: RFC3339 interval "start/end"
        limit: Per-request result limit
        timeout: HTTP timeout in seconds

    Returns:
        FederatedSearchResult with merged matches and per-API diagnostics
    """
    base_params: dict[str, Any] = {"limit": limit}
    if bbox:
        base_params["bbox"] = ",".join(str(c) for c in bbox)
    if datetime_range:
        base_params["datetime"] = datetime_range

    term_list: list[str | None] = list(terms) if terms else [None]

    async with httpx.AsyncClient(timeout=timeout) as client:
        responses = await asyncio.gather(
            *[
                _fetch_term(client, api, term, base_params)
                for api in apis
                for term in term_list
            ]
        )

    result = FederatedSearchResult()
    seen: set[tuple[str, str]] = set()

    for api, term, collections, error in responses:
        if error:
            result.errors.setdefault(api, []).append(f"q={term}: {error}")
            continue
        result.per_api_counts[api] = result.per_api_counts.get(api, 0) + len(
            collections
        )
        for c in collections:
            key = (api, c.get("id", ""))
            if key in seen:
                continue
            seen.add(key)
            c["_source_api"] = api
            c["_matched_term"] = term
            result.matches.append(
                CollectionMatch(
                    collection=c,
                    source_api=api,
                    matched_term=term,
                )
            )

    return result
