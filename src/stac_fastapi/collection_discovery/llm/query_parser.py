"""LLM-assisted query decomposition for natural language search queries."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from stac_fastapi.collection_discovery.llm.client import LLMClient, LLMError
from stac_fastapi.collection_discovery.llm.prompts import (
    QUERY_DECOMPOSE_SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


@dataclass
class DecomposedQuery:
    """Result of decomposing a natural language search query."""

    original_query: str
    """The original user query."""

    topic: str
    """The core phenomenon or data type (no location, no dates)."""

    location: str | None
    """Extracted place name, or None if no location found."""

    date_expression: str | None
    """Natural language date phrase verbatim, or None if absent."""

    decompose_time_ms: float
    """Time taken for decomposition in milliseconds."""

    error: str | None = None
    """Error message if decomposition failed."""


class QueryDecomposer:
    """Split a natural language query into structured fields using an LLM.

    Extracts topic, location, and date expression in a single LLM call so
    each can be routed to its dedicated component (geocoder, date parser,
    query expander).

    Example:
        ```python
        decomposer = QueryDecomposer(llm_client)
        result = await decomposer.decompose("wildfires in California 2023")
        # result.topic == "wildfires"
        # result.location == "California"
        # result.date_expression == "2023"
        ```
    """

    def __init__(self, client: LLMClient):
        """Initialize the query decomposer.

        Args:
            client: LLM client for making generation requests
        """
        self._client = client

    async def decompose(self, query: str) -> DecomposedQuery:
        """Decompose a natural language query into structured fields.

        Args:
            query: Natural language search query

        Returns:
            DecomposedQuery with topic, location, and date_expression
        """
        start_time = time.perf_counter()

        try:
            response = await self._client.generate(
                prompt=f'Extract fields from this query: "{query}"',
                system=QUERY_DECOMPOSE_SYSTEM_PROMPT,
                json_mode=True,
                temperature=0.0,
                max_tokens=256,
            )

            decompose_time_ms = (time.perf_counter() - start_time) * 1000

            parsed = response.parse_json()

            if not parsed or not isinstance(parsed, dict):
                logger.warning(
                    f"Failed to parse LLM decompose response: {response.content}"
                )
                return DecomposedQuery(
                    original_query=query,
                    topic=query,
                    location=None,
                    date_expression=None,
                    decompose_time_ms=decompose_time_ms,
                    error="Failed to parse LLM response",
                )

            result = DecomposedQuery(
                original_query=query,
                topic=parsed.get("topic") or query,
                location=parsed.get("location"),
                date_expression=parsed.get("date_expression"),
                decompose_time_ms=decompose_time_ms,
            )

            logger.info(
                f"Decomposed '{query}' -> topic={result.topic}, "
                f"location={result.location}, date={result.date_expression}",
                extra={
                    "query": query,
                    "topic": result.topic,
                    "location": result.location,
                    "date_expression": result.date_expression,
                    "decompose_time_ms": round(decompose_time_ms, 2),
                },
            )

            return result

        except LLMError as e:
            decompose_time_ms = (time.perf_counter() - start_time) * 1000
            logger.error(f"LLM error decomposing query '{query}': {e}")
            return DecomposedQuery(
                original_query=query,
                topic=query,
                location=None,
                date_expression=None,
                decompose_time_ms=decompose_time_ms,
                error=f"LLM error: {e}",
            )
