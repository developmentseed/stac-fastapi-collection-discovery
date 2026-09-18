"""LLM-assisted re-ranking of federated collection search results."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from stac_fastapi.collection_discovery.llm.client import LLMClient, LLMError
from stac_fastapi.collection_discovery.llm.prompts import RERANKING_SYSTEM_PROMPT

logger = logging.getLogger(__name__)


@dataclass
class RankedCollection:
    """A collection with its relevance assessment."""

    collection: dict[str, Any]
    """The STAC collection object."""

    score: float | None
    """Relevance score (0-10), or None if not ranked."""

    reason: str | None
    """Short explanation of the relevance judgment."""

    source_api: str | None = None
    """Upstream API the collection came from (provenance)."""

    matched_term: str | None = None
    """Search term that surfaced this collection (provenance)."""


@dataclass
class RerankResult:
    """Result of re-ranking a set of collections."""

    ranked: list[RankedCollection] = field(default_factory=list)
    """Collections ordered by relevance score, most relevant first."""

    candidate_count: int = 0
    """Number of candidates submitted for ranking."""

    rerank_time_ms: float = 0.0
    """Time taken for re-ranking in milliseconds."""

    error: str | None = None
    """Error message if re-ranking failed."""


class CollectionReranker:
    """Re-rank collections by relevance to the original query using an LLM.

    Uses a single batched LLM call: sends a compact "N. id - title" list
    and receives relevance scores, then reorders and annotates results.

    Example:
        ```python
        reranker = CollectionReranker(llm_client)
        result = await reranker.rerank("wildfires in California", collections)
        for rc in result.ranked:
            print(rc.score, rc.collection["id"])
        ```
    """

    def __init__(self, client: LLMClient):
        """Initialize the reranker.

        Args:
            client: LLM client for making generation requests
        """
        self._client = client

    async def rerank(
        self,
        query: str,
        collections: list[dict[str, Any]],
        max_candidates: int = 50,
        top_k: int = 10,
    ) -> RerankResult:
        """Score and reorder collections by relevance to the query.

        Args:
            query: The original natural language user query
            collections: Candidate collections (dicts); provenance keys
                ``_source_api`` and ``_matched_term`` are carried through
            max_candidates: Cap on candidates sent to the LLM
            top_k: Number of results to return after ranking

        Returns:
            RerankResult with ranked collections
        """
        start_time = time.perf_counter()
        candidates = collections[:max_candidates]

        if not candidates:
            return RerankResult(candidate_count=0)

        lines = []
        for i, c in enumerate(candidates, 1):
            title = (c.get("title") or "")[:80]
            lines.append(f"{i}. {c.get('id', '?')} - {title}")

        try:
            response = await self._client.generate(
                prompt=(
                    f'User query: "{query}"\n\nCollections:\n'
                    + "\n".join(lines)
                    + f"\n\nReturn the top {top_k} candidates by score."
                ),
                system=RERANKING_SYSTEM_PROMPT,
                json_mode=True,
                temperature=0.0,
                max_tokens=1024,
            )

            rerank_time_ms = (time.perf_counter() - start_time) * 1000

            parsed = response.parse_json()
            ranked_items: list[dict] = []
            if parsed and isinstance(parsed, dict):
                ranked_items = parsed.get("ranked") or parsed.get("results") or []
            elif parsed and isinstance(parsed, list):
                ranked_items = parsed

            ranked_items = sorted(
                (
                    r
                    for r in ranked_items
                    if isinstance(r, dict) and isinstance(r.get("i"), int)
                ),
                key=lambda r: -(r.get("score") or 0),
            )

            reranked: list[RankedCollection] = []
            used: set[int] = set()
            for r in ranked_items:
                idx = r["i"] - 1
                if 0 <= idx < len(candidates) and idx not in used:
                    used.add(idx)
                    c = candidates[idx]
                    reranked.append(
                        RankedCollection(
                            collection=c,
                            score=r.get("score"),
                            reason=r.get("reason"),
                            source_api=c.get("_source_api"),
                            matched_term=c.get("_matched_term"),
                        )
                    )

            logger.info(
                f"Reranked {len(candidates)} candidates -> "
                f"{min(len(reranked), top_k)} results",
                extra={
                    "query": query,
                    "candidate_count": len(candidates),
                    "rerank_time_ms": round(rerank_time_ms, 2),
                },
            )

            return RerankResult(
                ranked=reranked[:top_k],
                candidate_count=len(candidates),
                rerank_time_ms=rerank_time_ms,
            )

        except LLMError as e:
            rerank_time_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"LLM error re-ranking for '{query}': {e}")
            # On failure return candidates in original order, unranked
            return RerankResult(
                ranked=[
                    RankedCollection(
                        collection=c,
                        score=None,
                        reason="not ranked by the LLM reranker",
                        source_api=c.get("_source_api"),
                        matched_term=c.get("_matched_term"),
                    )
                    for c in candidates[:top_k]
                ],
                candidate_count=len(candidates),
                rerank_time_ms=rerank_time_ms,
                error=f"LLM error: {e}",
            )
