"""LLM-assisted ranking of candidate collections."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from stac_fastapi.collection_discovery.llm.client import LLMClient, LLMError
from stac_fastapi.collection_discovery.llm.prompts import RERANKING_SYSTEM_PROMPT

logger = logging.getLogger(__name__)

NOT_RANKED_REASON = "not ranked by the LLM reranker"
NOT_SCORED_REASON = "not scored by the LLM"
OVER_CAP_REASON = "not scored: over candidate cap"
MIN_TOKENS = 512
TOKENS_PER_CANDIDATE = 64


@dataclass
class RankCandidate:
    """A candidate collection submitted for ranking."""

    id: str
    ref: str
    """Opaque, unique identifier echoed back in the result."""

    title: str | None = None
    matched_terms: list[str] = field(default_factory=list)
    """Search terms that surfaced this candidate (client-reported)."""


@dataclass
class RankedItem:
    """One ranked candidate."""

    ref: str
    score: float | None
    """Relevance score 0-10, or None if the candidate was not scored."""

    reason: str | None


@dataclass
class RerankResult:
    """Result of ranking a set of candidates."""

    ranked: list[RankedItem]
    """All candidates: scored (best first), then unscored."""

    candidate_count: int
    scored_count: int
    rerank_time_ms: float
    error: str | None = None

    @property
    def unscored_count(self) -> int:
        return self.candidate_count - self.scored_count


def _one_line(text: str | None, limit: int) -> str:
    """Collapse whitespace so a value cannot break the numbered prompt list."""
    return " ".join((text or "").split())[:limit]


def _coerce_score(value: Any) -> float | None:
    """Coerce an LLM-provided score to a float in [0, 10], or None."""
    if isinstance(value, bool):
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if score != score:  # NaN
        return None
    return min(10.0, max(0.0, score))


class CollectionReranker:
    """Rank candidate collections by relevance to a query using one LLM call.

    Candidates are stable-sorted by term coverage (how many distinct search
    terms surfaced them); the first ``max_scored`` are scored by the LLM and
    the rest are appended unscored, so no candidate is ever dropped.

    Example:
        ```python
        reranker = CollectionReranker(llm_client)
        result = await reranker.rerank("wildfires", candidates, max_scored=50)
        ```
    """

    def __init__(self, client: LLMClient):
        self._client = client

    async def rerank(
        self,
        query: str,
        candidates: list[RankCandidate],
        max_scored: int = 50,
    ) -> RerankResult:
        """Score and order candidates.

        Args:
            query: The original natural language user query
            candidates: Candidates to rank (refs must be unique)
            max_scored: Number of top-coverage candidates sent to the LLM

        Returns:
            RerankResult with every candidate present in ``ranked``
        """
        start = time.perf_counter()
        if not candidates:
            return RerankResult([], 0, 0, 0.0)

        # Stable sort: ties keep the caller's order
        ordered = sorted(candidates, key=lambda c: -len(set(c.matched_terms)))
        window, tail = ordered[:max_scored], ordered[max_scored:]

        lines = [
            f"{i}. {_one_line(c.id, 120)} - {_one_line(c.title, 80)}"
            for i, c in enumerate(window, 1)
        ]
        prompt = (
            f"User query: {json.dumps(query)}\n\nCollections:\n"
            + "\n".join(lines)
            + f"\n\nReturn a score for each of the {len(window)} candidates."
        )

        try:
            response = await self._client.generate(
                prompt=prompt,
                system=RERANKING_SYSTEM_PROMPT,
                json_mode=True,
                temperature=0.0,
                max_tokens=max(MIN_TOKENS, TOKENS_PER_CANDIDATE * len(window)),
            )
        except LLMError as e:
            logger.error(f"LLM error ranking for '{query}': {e}")
            return RerankResult(
                ranked=[RankedItem(c.ref, None, NOT_RANKED_REASON) for c in ordered],
                candidate_count=len(ordered),
                scored_count=0,
                rerank_time_ms=(time.perf_counter() - start) * 1000,
                error=f"LLM error: {e}",
            )

        scored = self._parse(response.parse_json(), len(window))
        order = sorted(scored, key=lambda idx: (-scored[idx][0], idx))

        ranked = [RankedItem(window[i].ref, *scored[i]) for i in order]
        ranked += [
            RankedItem(c.ref, None, NOT_SCORED_REASON)
            for idx, c in enumerate(window)
            if idx not in scored
        ]
        ranked += [RankedItem(c.ref, None, OVER_CAP_REASON) for c in tail]

        elapsed = (time.perf_counter() - start) * 1000
        logger.info(
            f"Ranked {len(ordered)} candidates ({len(scored)} scored)",
            extra={
                "query": query,
                "candidate_count": len(ordered),
                "scored_count": len(scored),
                "rerank_time_ms": round(elapsed, 2),
            },
        )
        return RerankResult(
            ranked=ranked,
            candidate_count=len(ordered),
            scored_count=len(scored),
            rerank_time_ms=elapsed,
        )

    @staticmethod
    def _parse(parsed: Any, window_size: int) -> dict[int, tuple[float, str | None]]:
        """Map 0-based window index -> (score, reason), ignoring invalid items."""
        items: Any = []
        if isinstance(parsed, dict):
            items = parsed.get("ranked") or parsed.get("results") or []
        elif isinstance(parsed, list):
            items = parsed

        scored: dict[int, tuple[float, str | None]] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            i = item.get("i")
            if isinstance(i, bool) or not isinstance(i, int):
                continue
            if not 1 <= i <= window_size or (i - 1) in scored:
                continue
            score = _coerce_score(item.get("score"))
            if score is None:
                continue
            reason = item.get("reason")
            scored[i - 1] = (score, reason if isinstance(reason, str) else None)
        return scored
