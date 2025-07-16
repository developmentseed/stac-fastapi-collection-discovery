from pydantic import Field, field_validator, model_validator

from stac_fastapi.collection_discovery import __version__
from stac_fastapi.types.config import ApiSettings


class Settings(ApiSettings):
    stac_fastapi_title: str = "STAC Collection Discovery API"
    stac_fastapi_description: str = (
        "A collection-search-only STAC API that combines "
        "paginated search results from multiple STAC APIs."
    )
    stac_fastapi_version: str = __version__
    stac_fastapi_landing_id: str = "stac-fastapi"

    child_api_urls: str = Field(
        default="",
        description="comma separated list of STAC API URLs",
    )

    cors_origins: str = "*"
    cors_methods: str = "GET,POST,OPTIONS"

    @field_validator("child_api_urls")
    def parse_child_api_urls(cls, v):
        return v.split(",") if v else []

    @model_validator(mode="after")
    def update_description(self):
        urls_list = "\n".join(
            f"* {url.strip()}" for url in self.child_api_urls if url.strip()
        )
        self.stac_fastapi_description = (
            f"{self.stac_fastapi_description}\n\nConfigured APIs:\n{urls_list}"
        )

        return self
