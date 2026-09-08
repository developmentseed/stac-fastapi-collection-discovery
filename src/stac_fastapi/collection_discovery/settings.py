from typing import Literal

from pydantic import Field, field_validator

from stac_fastapi.types.config import ApiSettings


class Settings(ApiSettings):
    stac_fastapi_title: str = "STAC Collection Discovery API"
    stac_fastapi_landing_id: str = "stac-fastapi-collection-discovery"

    upstream_api_urls: str = Field(
        default="",
        description="comma separated list of STAC API URLs",
    )

    cors_origins: str = "*"
    cors_methods: str = "GET,POST,OPTIONS"

    # LLM Configuration
    llm_provider: Literal["openai", "anthropic"] | None = Field(
        default=None,
        description="LLM provider to use. None disables LLM features.",
    )
    llm_api_key: str | None = Field(
        default=None,
        description="API key for the LLM provider. Required if llm_provider is set.",
    )
    llm_model: str = Field(
        default="gpt-4o",
        description="Model name (e.g., 'gpt-4o', 'claude-sonnet-4-20250514')",
    )

    # LLM Feature Flags (all default False for backward compatibility)
    query_expansion_enabled: bool = Field(
        default=False,
        description="Enable LLM-powered query expansion",
    )
    reranking_enabled: bool = Field(
        default=False,
        description="Enable LLM-powered result re-ranking",
    )
    date_parsing_enabled: bool = Field(
        default=False,
        description="Enable LLM-assisted natural language date parsing",
    )
    location_parsing_enabled: bool = Field(
        default=False,
        description="Enable LLM-assisted natural language location parsing",
    )

    # LLM Tuning Parameters
    max_expansion_terms: int = Field(
        default=10,
        description="Maximum number of expanded terms to generate",
    )
    rerank_candidate_count: int = Field(
        default=50,
        description="Number of candidates to fetch before re-ranking",
    )
    rerank_return_count: int = Field(
        default=10,
        description="Number of results to return after re-ranking",
    )

    # Geocoding Configuration (for location parsing)
    geocoding_service_url: str | None = Field(
        default=None,
        description="URL for geocoding API service",
    )
    geocoding_timeout: float = Field(
        default=10.0,
        description="Timeout in seconds for geocoding requests",
    )

    @field_validator("upstream_api_urls")
    def parse_upstream_api_urls(cls, v):
        return v.split(",") if v else []
