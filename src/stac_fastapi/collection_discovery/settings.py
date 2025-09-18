from pydantic import Field, field_validator

from stac_fastapi.types.config import ApiSettings


class Settings(ApiSettings):
    stac_fastapi_title: str = "STAC Collection Discovery API"
    stac_fastapi_landing_id: str = "stac-fastapi"

    upstream_api_urls: str = Field(
        default="",
        description="comma separated list of STAC API URLs",
    )

    cors_origins: str = "*"
    cors_methods: str = "GET,POST,OPTIONS"

    @field_validator("upstream_api_urls")
    def parse_upstream_api_urls(cls, v):
        return v.split(",") if v else []
