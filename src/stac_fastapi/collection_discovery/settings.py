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
        default="gpt-4o-mini",
        description="Model name (e.g., 'gpt-4o-mini', 'claude-sonnet-4-20250514')",
    )

    llm_timeout: float = Field(
        default=30.0,
        gt=0,
        description="Timeout in seconds for each LLM provider request",
    )

    # LLM Tuning Parameters
    discovery_max_terms: int = Field(
        default=25,
        ge=1,
        description="Ceiling on the `max_terms` a client may request from "
        "POST /discovery/interpret; larger values are rejected with 422",
    )
    discovery_max_scored: int = Field(
        default=100,
        ge=1,
        description="Ceiling on the `max_scored` a client may request from "
        "POST /discovery/rank; larger values are rejected with 422",
    )
    discovery_max_candidates: int = Field(
        default=200,
        ge=1,
        description="Maximum candidates accepted by POST /discovery/rank; "
        "larger requests are rejected with 422",
    )

    # Geocoding Configuration (for location parsing)
    geocoding_service_url: str | None = Field(
        default=None,
        description="Base URL of a Nominatim-compatible geocoder. Required for "
        "location resolution; if unset, locations are not geocoded.",
    )
    geocoding_timeout: float = Field(
        default=10.0,
        description="Timeout in seconds for geocoding requests",
    )

    @field_validator("upstream_api_urls")
    def parse_upstream_api_urls(cls, v):
        return v.split(",") if v else []
