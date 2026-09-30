"""LLM-assisted search endpoints: POST /discovery/interpret and /discovery/rank.

Both endpoints are stateless. The client performs the actual collection search
(see dev-docs/specs/discovery-endpoints.md).
"""

import asyncio
import logging
from collections import Counter
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

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
)

logger = logging.getLogger(__name__)

MAX_QUERY_LENGTH = 1000


class _QueryModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: Annotated[str, Field(min_length=1, max_length=MAX_QUERY_LENGTH)]

    @field_validator("query")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be blank")
        return value


class InterpretRequest(_QueryModel):
    """Natural language query to interpret."""


class InterpretResponse(BaseModel):
    """Suggested /collections parameters for a natural language query."""

    q: list[str]
    bbox: list[float] | None = None
    datetime: str | None = None
    warnings: list[str] = []


class RankCandidateIn(BaseModel):
    """A slim candidate collection. Full collection objects are rejected."""

    model_config = ConfigDict(extra="forbid")

    id: Annotated[str, Field(min_length=1, max_length=500)]
    ref: Annotated[str, Field(min_length=1, max_length=2000)] | None = None
    title: Annotated[str, Field(max_length=1000)] | None = None
    matched_terms: Annotated[list[str], Field(max_length=50)] = Field(
        default_factory=list
    )


class RankRequest(_QueryModel):
    """Original query plus the candidate collections to rank."""

    candidates: list[RankCandidateIn]


class RankedOut(BaseModel):
    ref: str
    score: float | None
    reason: str | None


class RankResponse(BaseModel):
    ranked: list[RankedOut]
    unscored_count: int
    warnings: list[str] = []


def get_llm(request: Request) -> LLMClient:
    """Build the LLM client from app settings; 503 if not configured."""
    try:
        return LLMClient.from_settings(request.app.state.settings)
    except LLMConfigurationError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e


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
    try:
        result = await QueryExpander(llm).expand(topic, max_terms=max_terms)
    except Exception:
        logger.exception("query expansion failed unexpectedly")
        return [topic], ["expansion failed"]
    warnings = [f"expansion: {result.error}"] if result.error else []
    return result.terms, warnings


async def _resolve_datetime(
    llm: LLMClient, decomposed: DecomposedQuery
) -> tuple[str | None, list[str]]:
    if not decomposed.date_expression:
        return None, []
    try:
        result = await DateParser(llm).parse(decomposed.date_expression)
        if not result.success:
            return None, [f"date parsing: {result.error}"]
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

        decomposed = await QueryDecomposer(llm).decompose(body.query)
        if decomposed.error:
            raise HTTPException(
                status_code=503, detail=f"LLM unavailable: {decomposed.error}"
            )

        (terms, w_terms), (dt, w_dt), (bbox, w_bbox) = await asyncio.gather(
            _expand(llm, decomposed.topic, settings.max_expansion_terms),
            _resolve_datetime(llm, decomposed),
            _resolve_bbox(geocoder, decomposed, settings.geocoding_timeout),
        )

        return InterpretResponse(
            q=terms, bbox=bbox, datetime=dt, warnings=[*w_terms, *w_dt, *w_bbox]
        )

    @router.post(
        "/rank",
        response_model=RankResponse,
        summary="Rank candidate collections by relevance",
        description=(
            "Score candidates against the original query. Candidates are "
            "ordered by term coverage (`matched_terms`) and the top "
            "`rerank_candidate_count` are scored by the LLM; the rest are "
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

        if len(body.candidates) > settings.rerank_max_request_candidates:
            raise HTTPException(
                status_code=422,
                detail=f"Too many candidates ({len(body.candidates)}); "
                f"maximum is {settings.rerank_max_request_candidates}.",
            )

        refs = [c.ref or c.id for c in body.candidates]
        duplicates = sorted(r for r, n in Counter(refs).items() if n > 1)
        if duplicates:
            raise HTTPException(
                status_code=422,
                detail=f"Duplicate candidate refs: {duplicates}. Supply a unique "
                "`ref` per candidate (e.g. the collection's self link).",
            )

        candidates = [
            RankCandidate(id=c.id, ref=ref, title=c.title, matched_terms=c.matched_terms)
            for c, ref in zip(body.candidates, refs, strict=True)
        ]
        result = await CollectionReranker(llm).rerank(
            body.query,
            candidates,
            max_scored=settings.rerank_candidate_count,
        )
        return RankResponse(
            ranked=[
                RankedOut(ref=r.ref, score=r.score, reason=r.reason)
                for r in result.ranked
            ],
            unscored_count=result.unscored_count,
            warnings=[f"rerank: {result.error}"] if result.error else [],
        )

    return router
