"""LLM-assisted query expansion for free-text collection search."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field

from stac_fastapi.collection_discovery.llm.client import LLMClient, LLMError
from stac_fastapi.collection_discovery.llm.prompts import (
    QUERY_EXPANSION_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


@dataclass
class ExpansionResult:
    """Result of expanding a topic into related search terms."""

    topic: str
    """The original topic that was expanded."""

    terms: list[str] = field(default_factory=list)
    """Search terms including the topic itself (deduplicated, topic first)."""

    expansion_time_ms: float = 0.0
    """Time taken for expansion in milliseconds."""

    error: str | None = None
    """Error message if expansion failed."""

    @property
    def success(self) -> bool:
        """Whether expansion produced terms beyond the topic."""
        return len(self.terms) > 1 and self.error is None


def sanitize_term(term: str) -> str:
    """Clean a search term of tsquery-breaking characters.

    Parenthetical content and tsquery operators (&, |, !, :, *, quotes)
    cause 400/500 errors on pgstac-backed catalogs. Phrase semantics are
    preserved - multi-word terms stay intact for catalogs that support
    them, with a quoted fallback handled by the search layer.
    """
    term = re.sub(r"\([^)]*\)", " ", term)
    term = re.sub(r"[&|!:*'\"()<>]", " ", term)
    return re.sub(r"\s+", " ", term).strip()


class QueryExpander:
    """Expand a topic into related STAC search terms using an LLM.

    Example:
        ```python
        expander = QueryExpander(llm_client)
        result = await expander.expand("coral bleaching")
        # result.terms -> ["coral bleaching", "SST", "ocean heat", ...]
        ```
    """

    def __init__(self, client: LLMClient):
        """Initialize the query expander.

        Args:
            client: LLM client for making generation requests
        """
        self._client = client

    async def expand(
        self,
        topic: str,
        max_terms: int = 5,
    ) -> ExpansionResult:
        """Expand a topic into related search terms.

        Args:
            topic: The core phenomenon/data type to expand
            max_terms: Maximum number of expanded terms to generate

        Returns:
            ExpansionResult with the topic plus expanded terms
        """
        start_time = time.perf_counter()

        try:
            response = await self._client.generate(
                prompt=(
                    "Generate related search terms for finding Earth "
                    f'observation data about "{topic}".'
                ),
                system=QUERY_EXPANSION_SYSTEM_PROMPT,
                json_mode=True,
                temperature=0.3,
                max_tokens=256,
            )

            expansion_time_ms = (time.perf_counter() - start_time) * 1000

            parsed = response.parse_json()

            raw_terms: list[str] = []
            if parsed and isinstance(parsed, list):
                raw_terms = parsed
            elif parsed and isinstance(parsed, dict):
                # Accept the first value that is a list of strings - the
                # model may use any key (terms, related_search_terms, etc.)
                for value in parsed.values():
                    if isinstance(value, list) and all(
                        isinstance(t, str) for t in value
                    ):
                        raw_terms = value
                        break

            if not raw_terms:
                logger.warning(
                    f"No expansion terms parsed for '{topic}': "
                    f"{response.content[:200]}"
                )

            # Sanitize and drop the original topic from expansions
            expanded = [
                s
                for t in raw_terms
                if isinstance(t, str)
                and (s := sanitize_term(t))
                and s.lower() != topic.lower()
            ][:max_terms]

            topic_clean = sanitize_term(topic) or topic
            terms = list(dict.fromkeys([topic_clean] + expanded))

            logger.info(
                f"Expanded '{topic}' -> {terms}",
                extra={
                    "topic": topic,
                    "terms": terms,
                    "expansion_time_ms": round(expansion_time_ms, 2),
                },
            )

            return ExpansionResult(
                topic=topic,
                terms=terms,
                expansion_time_ms=expansion_time_ms,
            )

        except LLMError as e:
            expansion_time_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"LLM error expanding topic '{topic}': {e}")
            return ExpansionResult(
                topic=topic,
                terms=[topic],
                expansion_time_ms=expansion_time_ms,
                error=f"LLM error: {e}",
            )
