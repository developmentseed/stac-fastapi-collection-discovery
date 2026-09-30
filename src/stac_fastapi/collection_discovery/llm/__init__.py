"""LLM client infrastructure for assisted search capabilities."""

from stac_fastapi.collection_discovery.llm.client import (
    LLMClient,
    LLMResponse,
    LLMError,
    LLMConfigurationError,
    LLMRateLimitError,
    get_llm_client,
)
from stac_fastapi.collection_discovery.llm.date_parser import (
    DateParser,
    DateParseResult,
    to_rfc3339_interval,
    validate_datetime_range,
)
from stac_fastapi.collection_discovery.llm.expansion import (
    ExpansionResult,
    QueryExpander,
    sanitize_term,
)
from stac_fastapi.collection_discovery.llm.location_parser import (
    Geocoder,
    GeocodeResult,
)
from stac_fastapi.collection_discovery.llm.query_parser import (
    DecomposedQuery,
    QueryDecomposer,
)
from stac_fastapi.collection_discovery.llm.reranker import (
    CollectionReranker,
    RankedCollection,
    RerankResult,
)

__all__ = [
    "LLMClient",
    "LLMResponse",
    "LLMError",
    "LLMConfigurationError",
    "LLMRateLimitError",
    "get_llm_client",
    "DateParser",
    "DateParseResult",
    "to_rfc3339_interval",
    "validate_datetime_range",
    "ExpansionResult",
    "QueryExpander",
    "sanitize_term",
    "Geocoder",
    "GeocodeResult",
    "DecomposedQuery",
    "QueryDecomposer",
    "CollectionReranker",
    "RankedCollection",
    "RerankResult",
]
