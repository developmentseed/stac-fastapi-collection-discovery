"""LLM-assisted search endpoints: POST /discovery/interpret, /discovery/search
and /discovery/rank.

All three are stateless. /discovery/search runs the per-term collection search
and merge; a client may instead search GET /collections itself
(see dev-docs/specs/discovery-endpoints.md).
"""

import asyncio
import logging
from collections import Counter
from typing import Annotated, Any
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from stac_fastapi.collection_discovery.llm.client import (
    LLMClient,
    LLMConfigurationError,
)
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
    RankCandidate,
    RankedItem,
)

logger = logging.getLogger(__name__)

MAX_QUERY_LENGTH = 1000
DEFAULT_MAX_TERMS = 10
DEFAULT_MAX_SCORED = 50
DEFAULT_SEARCH_LIMIT = 100
DEFAULT_MAX_PAGES = 2
MAX_SEARCH_LIMIT = 1000
# Terms searched at once by /discovery/search; each search federates to every
# upstream, so this bounds concurrent upstream requests per call.
SEARCH_TERM_CONCURRENCY = 4
DISCOVERY_DOCS_BASE = "https://developmentseed.org/stac-fastapi-collection-discovery"
# Must not contain "collection-search": core.conformance_classes intersects
# every such class with the upstream APIs' and would drop ours.
DISCOVERY_CONFORMANCE_CLASS = f"{DISCOVERY_DOCS_BASE}/conformance/discovery/v1"
DISCOVERY_INTERPRET_REL = f"{DISCOVERY_DOCS_BASE}/rel/discovery-interpret"
DISCOVERY_RANK_REL = f"{DISCOVERY_DOCS_BASE}/rel/discovery-rank"
DISCOVERY_SEARCH_REL = f"{DISCOVERY_DOCS_BASE}/rel/discovery-search"


def discovery_enabled(settings) -> bool:
    """Discovery endpoints exist only when an LLM provider and key are set."""
    return bool(settings.llm_provider and settings.llm_api_key)


def geocoding_enabled(settings) -> bool:
    """Place names resolve to a bbox only when a geocoder URL is set."""
    return bool(settings.geocoding_service_url)


def discovery_conformance_classes(settings) -> list[str]:
    return [DISCOVERY_CONFORMANCE_CLASS] if discovery_enabled(settings) else []


def discovery_links(base_url: str) -> list[dict]:
    """Landing-page links advertising the discovery endpoints."""
    base = base_url if base_url.endswith("/") else base_url + "/"
    return [
        {
            "rel": DISCOVERY_INTERPRET_REL,
            "type": "application/json",
            "title": "Interpret a natural language query into q, bbox and datetime",
            "href": f"{base}discovery/interpret",
            "method": "POST",
        },
        {
            "rel": DISCOVERY_SEARCH_REL,
            "type": "application/json",
            "title": "Search collections for each term and merge the results",
            "href": f"{base}discovery/search",
            "method": "POST",
        },
        {
            "rel": DISCOVERY_RANK_REL,
            "type": "application/json",
            "title": "Rank candidate collections by relevance to a query",
            "href": f"{base}discovery/rank",
            "method": "POST",
        },
    ]


class _QueryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: Annotated[
        str,
        Field(
            min_length=1,
            max_length=MAX_QUERY_LENGTH,
            description=(
                "Natural language query describing the desired collections. "
                "May include a topic, location, and time period. Leading and "
                "trailing whitespace is removed; blank queries are rejected."
            ),
            examples=["Sentinel-2 imagery over Kenya during 2023"],
        ),
    ]

    @field_validator("query")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value


def _effective_limit(requested: int | None, default: int, ceiling: int, name: str) -> int:
    """Resolve a client-chosen limit; 422 (never clamp) above the ceiling."""
    if requested is None:
        return min(default, ceiling)
    if requested > ceiling:
        raise HTTPException(
            status_code=422,
            detail=f"{name} {requested} exceeds the maximum of {ceiling}",
        )
    return requested


class InterpretRequest(_QueryModel):
    """Natural language query to interpret."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"query": "Sentinel-2 imagery over Kenya during 2023", "max_terms": 5}
            ]
        }
    )

    max_terms: Annotated[
        int | None,
        Field(
            ge=1,
            description=(
                "Maximum number of search terms to return, including the "
                f"original topic. Omit or set to null to use {DEFAULT_MAX_TERMS}, "
                "capped by the server's configured maximum. Explicit values "
                "above that maximum return HTTP 422."
            ),
            examples=[5],
        ),
    ] = None


class InterpretResponse(BaseModel):
    """Suggested /collections parameters for a natural language query."""

    q: list[str]
    bbox: list[float] | None = None
    datetime: str | None = None
    warnings: list[str] = []


class RankCandidateIn(BaseModel):
    """A slim candidate collection. Full collection objects are rejected."""

    model_config = ConfigDict(extra="forbid")

    id: Annotated[str, Field(min_length=1, max_length=500, description="Collection id.")]
    ref: Annotated[
        str | None,
        Field(
            min_length=1,
            max_length=2000,
            description=(
                "Unique reference echoed back in the result, e.g. the "
                "collection's self link. Defaults to `id`; must be unique "
                "across candidates."
            ),
        ),
    ] = None
    title: Annotated[
        str | None, Field(max_length=1000, description="Collection title.")
    ] = None
    matched_terms: Annotated[
        list[str],
        Field(
            max_length=50,
            description=(
                "Search terms that returned this collection. Candidates matched "
                "by more terms are scored first."
            ),
        ),
    ] = Field(default_factory=list)


class RankRequest(_QueryModel):
    """Original query plus the candidate collections to rank."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "query": "Sentinel-2 imagery over Kenya during 2023",
                    "candidates": [
                        {
                            "id": "sentinel-2-l2a",
                            "ref": "https://stac.example.com/collections/sentinel-2-l2a",
                            "title": "Sentinel-2 Level-2A",
                            "matched_terms": ["Sentinel-2", "multispectral imagery"],
                        }
                    ],
                    "max_scored": 50,
                }
            ]
        }
    )

    candidates: Annotated[
        list[RankCandidateIn],
        Field(
            description=(
                "Candidate collections to rank, merged from the client's "
                "searches. More than the server's configured maximum returns "
                "HTTP 422."
            ),
        ),
    ]
    max_scored: Annotated[
        int | None,
        Field(
            ge=1,
            description=(
                "Number of candidates, by term coverage, scored by the LLM; "
                "the rest are returned unscored. Omit or set to null to use "
                f"{DEFAULT_MAX_SCORED}, capped by the server's configured "
                "maximum. Explicit values above that maximum return HTTP 422."
            ),
            examples=[50],
        ),
    ] = None


class SearchRequest(BaseModel):
    """Terms and filters to search, typically copied from /discovery/interpret."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "q": ["Sentinel-2", "multispectral imagery"],
                    "bbox": [33.9, -4.7, 41.9, 5.0],
                    "datetime": "2023-01-01T00:00:00Z/2023-12-31T23:59:59Z",
                    "limit": 100,
                    "max_pages": 2,
                }
            ]
        },
    )

    q: Annotated[
        list[Annotated[str, Field(min_length=1, max_length=500)]],
        Field(
            description=(
                "Search terms; each is searched separately. Empty means one "
                "search without `q`. Repeated terms are searched once. More "
                "terms than the server's configured maximum returns HTTP 422."
            ),
        ),
    ] = Field(default_factory=list)
    bbox: Annotated[
        list[float] | None,
        Field(
            min_length=4,
            max_length=6,
            description="Bounding box passed to every search.",
        ),
    ] = None
    datetime: Annotated[
        str | None,
        Field(max_length=200, description="Datetime interval passed to every search."),
    ] = None
    apis: Annotated[
        list[str] | None,
        Field(
            description="Upstream STAC APIs to search. Defaults to the configured ones."
        ),
    ] = None
    limit: Annotated[
        int,
        Field(
            ge=1,
            le=MAX_SEARCH_LIMIT,
            description="Page size requested from each upstream API.",
        ),
    ] = DEFAULT_SEARCH_LIMIT
    max_pages: Annotated[
        int | None,
        Field(
            ge=1,
            description=(
                "Pages followed per term via `next` links. Omit or set to null "
                f"to use {DEFAULT_MAX_PAGES}, capped by the server's configured "
                "maximum. Explicit values above that maximum return HTTP 422."
            ),
        ),
    ] = None
    include_collections: Annotated[
        bool,
        Field(
            description=(
                "Also return the full collection objects, keyed by `ref`. They "
                "can be large; leave false if only ranking is needed."
            ),
        ),
    ] = False

    @field_validator("q")
    @classmethod
    def _strip_terms(cls, value: list[str]) -> list[str]:
        terms = [t.strip() for t in value]
        if not all(terms):
            raise ValueError("q must not contain blank terms")
        return list(dict.fromkeys(terms))

    @field_validator("bbox")
    @classmethod
    def _bbox_length(cls, value: list[float] | None) -> list[float] | None:
        if value is not None and len(value) not in (4, 6):
            raise ValueError("bbox must have 4 or 6 numbers")
        return value


class FailedSearch(BaseModel):
    """An upstream API that failed while searching one term."""

    api: str
    term: str | None


class SearchResponse(BaseModel):
    candidates: Annotated[
        list[RankCandidateIn],
        Field(
            description=(
                "Merged candidates, ordered by term coverage; send to "
                "/discovery/rank as is."
            )
        ),
    ]
    found_count: Annotated[
        int, Field(description="Unique collections found, before truncation.")
    ]
    failed: list[FailedSearch] = []
    collections: Annotated[
        dict[str, dict[str, Any]] | None,
        Field(description="Full collection objects by `ref`, if requested."),
    ] = None
    warnings: list[str] = []


class RankResponse(BaseModel):
    ranked: list[RankedItem]
    scored_count: int
    unscored_count: int
    warnings: list[str] = []


def get_llm(request: Request) -> LLMClient:
    """Build the LLM client from app settings; 503 if not configured."""
    try:
        return LLMClient.from_settings(request.app.state.settings)
    except LLMConfigurationError as e:
        logger.warning("LLM not available: %s", e)
        raise HTTPException(
            status_code=503, detail="LLM is not available or not configured"
        ) from e


def get_search_client(request: Request):
    """The app's federated collection search client (core.CollectionSearchClient)."""
    return request.app.state.search_client


def get_geocoder(request: Request) -> Geocoder | None:
    """App-wide geocoder (shares its cache across requests), or None if no
    geocoding service is configured."""
    geocoder = getattr(request.app.state, "discovery_geocoder", None)
    if geocoder is None:
        url = request.app.state.settings.geocoding_service_url
        if not url:
            return None
        geocoder = Geocoder(base_url=url)
        request.app.state.discovery_geocoder = geocoder
    return geocoder


async def _expand(
    llm: LLMClient, topic: str, max_terms: int
) -> tuple[list[str], list[str]]:
    """Expand ``topic`` into at most ``max_terms`` search terms (topic included)."""
    if not topic:
        return [], ["no topic found in query"]
    if max_terms <= 1:
        return [topic], []
    try:
        result = await QueryExpander(llm).expand(topic, max_expansions=max_terms - 1)
    except Exception:
        logger.exception("query expansion failed unexpectedly")
        return [topic], ["expansion failed"]
    if result.error:
        logger.warning("query expansion failed: %s", result.error)
        return result.terms, ["expansion failed"]
    return result.terms, []


async def _resolve_datetime(
    llm: LLMClient, decomposed: DecomposedQuery
) -> tuple[str | None, list[str]]:
    if not decomposed.date_expression:
        return None, []
    try:
        result = await DateParser(llm).parse(decomposed.date_expression)
        if not result.success:
            logger.warning("date parsing failed: %s", result.error)
            return None, ["date parsing failed"]
        return to_rfc3339_interval(result.datetime_range), []  # type: ignore[arg-type]
    except Exception:
        logger.exception("date parsing failed unexpectedly")
        return None, ["date parsing failed"]


async def _resolve_bbox(
    geocoder: Geocoder | None, decomposed: DecomposedQuery, timeout: float
) -> tuple[list[float] | None, list[str]]:
    if not decomposed.location:
        return None, []
    if geocoder is None:
        return None, [
            f"geocoding is not configured; could not resolve '{decomposed.location}'"
        ]
    try:
        result = await geocoder.geocode(decomposed.location, timeout=timeout)
    except Exception:
        logger.exception("geocoding failed unexpectedly")
        return None, [f"geocoding failed for '{decomposed.location}'"]
    if result is None:
        return None, [f"geocoding failed for '{decomposed.location}'"]
    return result.bbox, []


def _self_ref(collection: dict[str, Any]) -> str:
    """Source-qualified ref: the collection's own self link, else its id."""
    for link in collection.get("links", []):
        if link.get("rel") == "self" and link.get("href"):
            return link["href"]
    return collection["id"]


def _next_token(links: list[dict[str, Any]]) -> str | None:
    href = next((link["href"] for link in links if link.get("rel") == "next"), None)
    if not href:
        return None
    return parse_qs(urlparse(href).query).get("token", [None])[0]


async def _search_term(
    search_client, request: Request, term: str | None, body: SearchRequest, max_pages: int
) -> tuple[list[dict[str, Any]], list[str]]:
    """All pages (up to ``max_pages``) of one federated search, plus the
    upstream APIs that failed on any page."""
    found: list[dict[str, Any]] = []
    failed: list[str] = []
    token = None
    for _ in range(max_pages):
        if token:
            result = await search_client.all_collections(request=request, token=token)
        else:
            result = await search_client.all_collections(
                request=request,
                apis=body.apis,
                bbox=body.bbox,
                datetime=body.datetime,
                limit=body.limit,
                q=[term] if term is not None else None,
            )
        found.extend(result.collections["collections"])
        failed.extend(a for a in result.failed_apis if a not in failed)
        token = _next_token(result.collections["links"])
        if not token:
            break
    return found, failed


def _merge_search_results(
    terms: list[str | None],
    per_term: list[tuple[list[dict[str, Any]], list[str]]],
    max_candidates: int,
    include_collections: bool,
) -> SearchResponse:
    """Merge per-term results by ref, recording the terms that returned each
    collection, then order by term coverage and keep the first
    ``max_candidates``."""
    merged: dict[str, tuple[dict[str, Any], list[str]]] = {}
    failed: list[FailedSearch] = []
    skipped = 0
    for term, (collections, failed_apis) in zip(terms, per_term, strict=True):
        failed.extend(FailedSearch(api=a, term=term) for a in failed_apis)
        for collection in collections:
            if not collection.get("id"):
                skipped += 1
                continue
            _, matched = merged.setdefault(_self_ref(collection), (collection, []))
            if term is not None and term not in matched:
                matched.append(term)

    # Stable sort: first-seen order breaks ties
    ordered = sorted(merged.items(), key=lambda kv: -len(kv[1][1]))
    candidates: dict[str, RankCandidateIn] = {}
    truncated = False
    for ref, (collection, matched) in ordered:
        if len(candidates) == max_candidates:
            truncated = True
            break
        try:
            candidates[ref] = RankCandidateIn(
                ref=ref,
                id=collection["id"],
                title=collection.get("title"),
                matched_terms=matched,
            )
        except ValidationError:
            skipped += 1

    warnings = []
    if skipped:
        warnings.append(
            f"skipped {skipped} collection(s) with an invalid id, ref or title"
        )
    if truncated:
        warnings.append(
            f"returned the {len(candidates)} candidates with the most matched "
            f"terms of {len(merged)} found (maximum {max_candidates})"
        )
    return SearchResponse(
        candidates=list(candidates.values()),
        found_count=len(merged),
        failed=failed,
        collections=(
            {ref: merged[ref][0] for ref in candidates} if include_collections else None
        ),
        warnings=warnings,
    )


def build_discovery_router() -> APIRouter:
    """Router for the /discovery endpoints."""
    router = APIRouter(prefix="/discovery")

    @router.post(
        "/interpret",
        response_model=InterpretResponse,
        summary="Interpret a natural language query",
        description=(
            "Translate natural language into suggested `q`, `bbox` and `datetime` "
            "parameters for `GET /collections`. Performs no collection search. "
            "Steps that fail (date parsing, geocoding, expansion) are reported in "
            "`warnings`; an unavailable LLM returns 503."
        ),
    )
    async def interpret(
        body: InterpretRequest,
        request: Request,
        llm: Annotated[LLMClient, Depends(get_llm)],
        geocoder: Annotated[Geocoder | None, Depends(get_geocoder)],
    ) -> InterpretResponse:
        settings = request.app.state.settings
        max_terms = _effective_limit(
            body.max_terms, DEFAULT_MAX_TERMS, settings.discovery_max_terms, "max_terms"
        )

        decomposed = await QueryDecomposer(llm).decompose(body.query)
        if decomposed.error:
            logger.warning("query decomposition failed: %s", decomposed.error)
            raise HTTPException(status_code=503, detail="LLM unavailable")

        (terms, w_terms), (dt, w_dt), (bbox, w_bbox) = await asyncio.gather(
            _expand(llm, decomposed.topic, max_terms),
            _resolve_datetime(llm, decomposed),
            _resolve_bbox(geocoder, decomposed, settings.geocoding_timeout),
        )

        return InterpretResponse(
            q=terms, bbox=bbox, datetime=dt, warnings=[*w_terms, *w_dt, *w_bbox]
        )

    @router.post(
        "/search",
        response_model=SearchResponse,
        summary="Search collections for each term and merge the results",
        description=(
            "Run one federated `GET /collections` search per term in `q` "
            "(following `next` up to `max_pages`), merge the results by the "
            "collection's `self` link, and record which terms returned each "
            "collection in `matched_terms`. Candidates are ordered by term "
            "coverage and ready to send to `/discovery/rank`. Makes no LLM call. "
            "Upstream failures are listed per term in `failed`."
        ),
    )
    async def search(
        body: SearchRequest,
        request: Request,
        search_client: Annotated[Any, Depends(get_search_client)],
    ) -> SearchResponse:
        settings = request.app.state.settings
        max_pages = _effective_limit(
            body.max_pages, DEFAULT_MAX_PAGES, settings.discovery_max_pages, "max_pages"
        )
        if len(body.q) > settings.discovery_max_terms:
            raise HTTPException(
                status_code=422,
                detail=f"Too many terms ({len(body.q)}); "
                f"maximum is {settings.discovery_max_terms}.",
            )

        terms: list[str | None] = list(body.q) or [None]
        semaphore = asyncio.Semaphore(SEARCH_TERM_CONCURRENCY)

        async def run(term: str | None):
            async with semaphore:
                return await _search_term(search_client, request, term, body, max_pages)

        per_term = await asyncio.gather(*(run(t) for t in terms))
        return _merge_search_results(
            terms, per_term, settings.discovery_max_candidates, body.include_collections
        )

    @router.post(
        "/rank",
        response_model=RankResponse,
        summary="Rank candidate collections by relevance",
        description=(
            "Score candidates against the original query. Candidates are "
            "ordered by term coverage (`matched_terms`) and the top "
            "`max_scored` (default 50) are scored by the LLM; the rest are "
            "returned after them with `score: null`. All candidates are "
            "returned, best first. `reason` is plain text; escape it before "
            "rendering as HTML."
        ),
    )
    async def rank(
        body: RankRequest,
        request: Request,
        llm: Annotated[LLMClient, Depends(get_llm)],
    ) -> RankResponse:
        settings = request.app.state.settings

        max_scored = _effective_limit(
            body.max_scored,
            DEFAULT_MAX_SCORED,
            settings.discovery_max_scored,
            "max_scored",
        )
        if len(body.candidates) > settings.discovery_max_candidates:
            raise HTTPException(
                status_code=422,
                detail=f"Too many candidates ({len(body.candidates)}); "
                f"maximum is {settings.discovery_max_candidates}.",
            )

        refs = [c.ref or c.id for c in body.candidates]
        duplicates = sorted(r for r, n in Counter(refs).items() if n > 1)
        if duplicates:
            raise HTTPException(
                status_code=422,
                detail=f"{len(duplicates)} duplicate candidate ref(s), "
                f"e.g. {duplicates[0][:100]!r}; supply a unique `ref` per "
                "candidate (e.g. the collection's self link).",
            )

        candidates = [
            RankCandidate(id=c.id, ref=ref, title=c.title, matched_terms=c.matched_terms)
            for c, ref in zip(body.candidates, refs, strict=True)
        ]
        result = await CollectionReranker(llm).rerank(
            body.query,
            candidates,
            max_scored=max_scored,
        )
        return RankResponse(
            ranked=result.ranked,
            scored_count=result.scored_count,
            unscored_count=result.unscored_count,
            warnings=[f"rerank: {result.error}"] if result.error else [],
        )

    return router
