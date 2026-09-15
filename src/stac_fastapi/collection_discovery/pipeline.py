"""LLM-assisted collection search pipeline.

Orchestrates the full natural-language flow:

    query -> decompose (topic/location/date) -> date parse -> geocode
          -> query expansion -> federated search -> re-ranking

Each stage is independently optional: if the LLM yields no location or
date, that filter is simply skipped and the search proceeds.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from stac_fastapi.collection_discovery.llm.client import LLMClient
from stac_fastapi.collection_discovery.llm.date_parser import (
    DateParser,
    to_rfc3339_interval,
)
from stac_fastapi.collection_discovery.llm.expansion import QueryExpander
from stac_fastapi.collection_discovery.llm.location_parser import Geocoder
from stac_fastapi.collection_discovery.llm.query_parser import (
    DecomposedQuery,
    QueryDecomposer,
)
from stac_fastapi.collection_discovery.llm.reranker import (
    CollectionReranker,
    RankedCollection,
)
from stac_fastapi.collection_discovery.search import (
    CollectionMatch,
    federated_collection_search,
)
from stac_fastapi.collection_discovery.settings import Settings

logger = logging.getLogger(__name__)


@dataclass
class AssistedSearchResult:
    """Result of a full LLM-assisted collection search."""

    query: str
    """The original natural language query."""

    decomposed: DecomposedQuery | None = None
    """Structured fields extracted from the query."""

    datetime_range: str | None = None
    """Resolved RFC3339 datetime interval, or None."""

    bbox: list[float] | None = None
    """Resolved bounding box [west, south, east, north], or None."""

    resolved_place: str | None = None
    """Canonical place name from the geocoder, or None."""

    expanded_terms: list[str] = field(default_factory=list)
    """Topic plus LLM-expanded search terms used for `q`."""

    matches: list[RankedCollection] = field(default_factory=list)
    """Re-ranked collections, most relevant first."""

    candidate_count: int = 0
    """Number of collections found before re-ranking."""

    per_api_counts: dict[str, int] = field(default_factory=dict)
    """Raw result count per upstream API."""

    errors: list[str] = field(default_factory=list)
    """Non-fatal errors collected during the pipeline."""

    total_time_ms: float = 0.0
    """End-to-end pipeline time in milliseconds."""


class AssistedSearchPipeline:
    """LLM-assisted natural language collection search.

    Example:
        ```python
        pipeline = AssistedSearchPipeline(Settings())
        result = await pipeline.search("wildfires in California 2023")
        for m in result.matches:
            print(m.score, m.collection["id"])
        ```
    """

    def __init__(
        self,
        settings: Settings,
        llm_client: LLMClient | None = None,
    ):
        """Initialize the pipeline.

        Args:
            settings: Application settings (LLM config, geocoding, tuning)
            llm_client: Optional pre-configured LLM client; built from
                settings if omitted
        """
        self._settings = settings
        client = llm_client or LLMClient.from_settings(settings)

        self._decomposer = QueryDecomposer(client)
        self._date_parser = DateParser(client)
        self._expander = QueryExpander(client)
        self._reranker = CollectionReranker(client)
        self._geocoder = Geocoder(
            base_url=settings.geocoding_service_url
            or "https://nominatim.openstreetmap.org"
        )

    async def search(
        self,
        query: str,
        apis: list[str],
        limit: int = 10,
    ) -> AssistedSearchResult:
        """Run the full assisted-search pipeline.

        Args:
            query: Natural language search query
            apis: Upstream STAC API base URLs to federate over
            limit: Per-request result limit for upstream calls

        Returns:
            AssistedSearchResult with ranked matches and diagnostics
        """
        start_time = time.perf_counter()
        result = AssistedSearchResult(query=query)
        s = self._settings

        # 1. Decompose query into topic / location / date expression
        decomposed = await self._decomposer.decompose(query)
        result.decomposed = decomposed
        if decomposed.error:
            result.errors.append(f"decompose: {decomposed.error}")

        # 2. Resolve date expression -> RFC3339 interval
        if decomposed.date_expression:
            date_result = await self._date_parser.parse(
                decomposed.date_expression
            )
            if date_result.success:
                result.datetime_range = to_rfc3339_interval(
                    date_result.datetime_range  # type: ignore[arg-type]
                )
            else:
                result.errors.append(f"date parsing: {date_result.error}")

        # 3. Geocode location -> bbox
        if decomposed.location:
            geocode = await self._geocoder.geocode(
                decomposed.location,
                timeout=s.geocoding_timeout,
            )
            if geocode:
                result.bbox = geocode.bbox
                result.resolved_place = geocode.resolved_name
            else:
                result.errors.append(
                    f"geocoding failed for '{decomposed.location}'"
                )

        # 4. Expand topic into related search terms
        expansion = await self._expander.expand(
            decomposed.topic,
            max_terms=s.max_expansion_terms,
        )
        result.expanded_terms = expansion.terms
        if expansion.error:
            result.errors.append(f"expansion: {expansion.error}")

        # 5. Federated search (per-term fan-out, merged + deduped)
        search_result = await federated_collection_search(
            apis=apis,
            terms=result.expanded_terms or None,
            bbox=result.bbox,
            datetime_range=result.datetime_range,
            limit=limit,
        )
        result.per_api_counts = search_result.per_api_counts
        result.candidate_count = len(search_result.matches)
        for api, errs in search_result.errors.items():
            result.errors.extend(f"{api} {e}" for e in errs)

        # 6. Re-rank candidates against the original query
        if search_result.matches:
            rerank = await self._reranker.rerank(
                query,
                [m.collection for m in search_result.matches],
                max_candidates=s.rerank_candidate_count,
                top_k=s.rerank_return_count,
            )
            result.matches = rerank.ranked
            if rerank.error:
                result.errors.append(f"rerank: {rerank.error}")

        result.total_time_ms = (time.perf_counter() - start_time) * 1000

        logger.info(
            f"Assisted search '{query}' -> {len(result.matches)} results "
            f"({result.candidate_count} candidates)",
            extra={
                "query": query,
                "topic": decomposed.topic,
                "location": decomposed.location,
                "datetime_range": result.datetime_range,
                "bbox": result.bbox,
                "expanded_terms": result.expanded_terms,
                "candidate_count": result.candidate_count,
                "total_time_ms": round(result.total_time_ms, 2),
            },
        )

        return result


__all__ = [
    "AssistedSearchPipeline",
    "AssistedSearchResult",
    "CollectionMatch",
]
