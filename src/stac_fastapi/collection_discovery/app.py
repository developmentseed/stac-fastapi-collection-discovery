import logging
from typing import Annotated, List, Optional

import attr
from brotli_asgi import BrotliMiddleware
from fastapi import FastAPI, Query
from starlette.middleware import Middleware

from stac_fastapi.api.app import StacApi
from stac_fastapi.api.middleware import CORSMiddleware, ProxyHeaderMiddleware
from stac_fastapi.collection_discovery.core import (
    BASE_CONFORMANCE_CLASSES,
    CollectionSearchClient,
    health_check,
)
from stac_fastapi.collection_discovery.settings import Settings
from stac_fastapi.extensions.core import (
    CollectionSearchExtension,
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
            description="List of STAC APIs to include in the search"  # noqa: E501
        ),
    ] = attr.ib(default=None)


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
    SortExtension(conformance_classes=[SortConformanceClasses.COLLECTIONS]),
    FieldsExtension(conformance_classes=[FieldsConformanceClasses.COLLECTIONS]),
    FreeTextExtension(
        conformance_classes=[FreeTextConformanceClasses.COLLECTIONS],
    ),
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


api = StacCollectionSearchApi(
    app=FastAPI(
        openapi_url=settings.openapi_url,
        docs_url=settings.docs_url,
        redoc_url=None,
        root_path=settings.root_path,
        title=settings.stac_fastapi_title,
        version=settings.stac_fastapi_version,
        description=settings.stac_fastapi_description,
    ),
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
