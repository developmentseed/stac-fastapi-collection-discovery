import logging
from typing import Annotated, Dict, List, Optional

import attr
from brotli_asgi import BrotliMiddleware
from fastapi import APIRouter, FastAPI, Query
from stac_pydantic.api import Conformance, LandingPage
from stac_pydantic.shared import MimeTypes
from starlette.middleware import Middleware

from stac_fastapi.api.app import StacApi
from stac_fastapi.api.middleware import CORSMiddleware, ProxyHeaderMiddleware
from stac_fastapi.api.models import HealthCheck
from stac_fastapi.api.routes import create_async_endpoint
from stac_fastapi.collection_discovery.core import (
    BASE_CONFORMANCE_CLASSES,
    CollectionSearchClient,
    health_check,
)
from stac_fastapi.collection_discovery.settings import Settings
from stac_fastapi.extensions.core import (
    CollectionSearchExtension,
    CollectionSearchFilterExtension,
    FieldsExtension,
    FreeTextExtension,
    SortExtension,
    TokenPaginationExtension,
)
from stac_fastapi.extensions.core.fields import FieldsConformanceClasses
from stac_fastapi.extensions.core.free_text import FreeTextConformanceClasses
from stac_fastapi.extensions.core.sort import SortConformanceClasses
from stac_fastapi.types.extension import ApiExtension
from stac_fastapi.types.search import APIRequest

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("stac_fastapi.collection_discovery")
logger.setLevel(logging.INFO)

settings = Settings()


@attr.s
class FederatedApisGetRequest(APIRequest):
    apis: Annotated[
        Optional[List[str]],
        Query(
            description="List of STAC APIs to include in the search. Can be provided as multiple query parameters (?apis=url1&apis=url2) or as a comma-separated string (?apis=url1,url2)"  # noqa: E501
        ),
    ] = attr.ib(default=None)

    def __attrs_post_init__(self):
        """Post-initialization to handle comma-separated apis parameter."""
        if self.apis and len(self.apis) == 1 and "," in self.apis[0]:
            # Split comma-separated string into list
            self.apis = [api.strip() for api in self.apis[0].split(",") if api.strip()]


@attr.s
class FederatedApisExtension(ApiExtension):
    GET: FederatedApisGetRequest = attr.ib(default=FederatedApisGetRequest)  # type: ignore
    POST = attr.ib(init=False)

    def register(self, app: FastAPI) -> None:
        """Register the extension with a FastAPI application.

        Args:
            app (fastapi.FastAPI): target FastAPI application.

        Returns:
            None
        """
        pass


cs_extensions = [
    FieldsExtension(conformance_classes=[FieldsConformanceClasses.COLLECTIONS]),
    FreeTextExtension(
        conformance_classes=[FreeTextConformanceClasses.COLLECTIONS],
    ),
    CollectionSearchFilterExtension(),
    SortExtension(conformance_classes=[SortConformanceClasses.COLLECTIONS]),
    TokenPaginationExtension(),
    FederatedApisExtension(),
]

collection_search_extension = CollectionSearchExtension.from_extensions(cs_extensions)
collections_get_request_model = collection_search_extension.GET
cs_extensions.append(collection_search_extension)


class StacCollectionSearchApi(StacApi):
    def register_core(self):
        self.register_landing_page()
        self.register_conformance_classes()
        self.register_get_collections()

    def register_landing_page(self) -> None:
        """Register landing page (GET /)."""
        self.router.add_api_route(
            name="Landing Page",
            path="/",
            response_model=(
                LandingPage if self.settings.enable_response_models else None
            ),
            responses={
                200: {
                    "content": {
                        MimeTypes.json.value: {},
                    },
                    "model": LandingPage,
                },
            },
            response_class=self.response_class,
            response_model_exclude_unset=False,
            response_model_exclude_none=True,
            methods=["GET"],
            endpoint=create_async_endpoint(
                self.client.landing_page, FederatedApisGetRequest
            ),
        )

    def register_conformance_classes(self) -> None:
        """Register conformance classes (GET /conformance)."""
        self.router.add_api_route(
            name="Conformance Classes",
            path="/conformance",
            response_model=(
                Conformance if self.settings.enable_response_models else None
            ),
            responses={
                200: {
                    "content": {
                        MimeTypes.json.value: {},
                    },
                    "model": Conformance,
                },
            },
            response_class=self.response_class,
            response_model_exclude_unset=True,
            response_model_exclude_none=True,
            methods=["GET"],
            endpoint=create_async_endpoint(
                self.client.conformance, FederatedApisGetRequest
            ),
        )

    def add_health_check(self) -> None:
        """Add a health check."""

        mgmt_router = APIRouter(prefix=self.app.state.router_prefix)

        async def ping():
            """Liveliness probe."""
            return {"message": "PONG"}

        mgmt_router.add_api_route(
            name="Ping",
            path="/_mgmt/ping",
            response_model=Dict,
            responses={
                200: {
                    "content": {
                        MimeTypes.json.value: {},
                    },
                },
            },
            response_class=self.response_class,
            methods=["GET"],
            endpoint=ping,
        )

        mgmt_router.add_api_route(
            name="Health",
            path="/_mgmt/health",
            response_model=(
                HealthCheck if self.settings.enable_response_models else None
            ),
            responses={
                200: {
                    "content": {
                        MimeTypes.json.value: {},
                    },
                    "model": HealthCheck,
                },
            },
            response_class=self.response_class,
            methods=["GET"],
            endpoint=create_async_endpoint(health_check, FederatedApisGetRequest),
        )
        self.app.include_router(mgmt_router, tags=["Liveliness/Readiness"])


DESCRIPTION = (
    "A collection-search-only STAC API that combines paginated search results from "
    "multiple upstream STAC APIs into a single unified interface.\n\n"
    "## API Configuration\n"
    "The application can be pre-configured with a default set of upstream STAC APIs via "
    "the `UPSTREAM_API_URLS` environment variable (comma-separated list). "
    "Users can override this configuration for individual requests by providing their "
    "own list of APIs using the `apis` query parameter, "
    "either as multiple parameters (`?apis=url1&apis=url2`) or as a comma-separated "
    "string (`?apis=url1,url2`).\n\n"
    "## Conformance Classes\n"
    "The API's conformance classes are dynamically calculated based on the intersection "
    "of capabilities across all queried upstream APIs. "
    "The conformance classes returned for any given request represent only the "
    "collection-search features that are commonly supported by ALL upstream APIs in the "
    "request, limited to the extensions enabled in this application: filter, sort, "
    "free-text search, and fields selection.\n\n"
    "## Pagination Behavior\n"
    "The `limit` parameter is passed to each upstream API individually, meaning the "
    "total number of collections returned will be `limit × number_of_APIs`. "
    "For example, with `limit=10` and 3 upstream APIs, you may receive up to 30 "
    "collections per page. "
    "Pagination state is maintained using base64-encoded tokens that track the current "
    "position across all upstream APIs.\n\n"
    "## Example Usage\n"
    "- Search all pre-configured APIs: `GET /collections`\n"
    "- Search with bounding box: `GET /collections?bbox=-180,-90,180,90&limit=5`\n"
    "- Search specific APIs: `GET /collections?apis=https://stac.eoapi.dev,https://stac.maap-project.org`\n"
    "- Free-text search: `GET /collections?q=landsat,sentinel`\n"
    "- Filtered search: `GET /collections?filter=mission='sentinel-2'&"
    "filter-lang=cql2-text`\n"
    "- Paginated search: `GET /collections?token=eyJ...`"
)


api = StacCollectionSearchApi(
    app=FastAPI(
        openapi_url=settings.openapi_url,
        docs_url=settings.docs_url,
        redoc_url=None,
        root_path=settings.root_path,
        title=settings.stac_fastapi_title,
        version=settings.stac_fastapi_version,
        description=DESCRIPTION,
    ),
    description=DESCRIPTION,
    extensions=cs_extensions,
    client=CollectionSearchClient(base_conformance_classes=BASE_CONFORMANCE_CLASSES),
    settings=settings,
    collections_get_request_model=collections_get_request_model,
    health_check=health_check,
    middlewares=[
        Middleware(BrotliMiddleware),
        Middleware(ProxyHeaderMiddleware),
        Middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=settings.cors_methods,
            allow_headers=["*"],
        ),
    ],
)

app = api.app
