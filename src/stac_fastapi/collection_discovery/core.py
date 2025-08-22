import asyncio
import base64
import json
import logging
from typing import Annotated, Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlencode, urljoin

import attr
from fastapi import Query, Request
from httpx import AsyncClient
from pydantic import BaseModel
from stac_pydantic.links import Relations
from stac_pydantic.shared import BBox, MimeTypes

from stac_fastapi.types.conformance import OAFConformanceClasses, STACConformanceClasses
from stac_fastapi.types.core import AsyncBaseCoreClient
from stac_fastapi.types.requests import get_base_url
from stac_fastapi.types.stac import (
    Collection,
    Collections,
    Item,
    ItemCollection,
    LandingPage,
)

BASE_CONFORMANCE_CLASSES = [
    STACConformanceClasses.CORE,
    STACConformanceClasses.COLLECTIONS,
    OAFConformanceClasses.CORE,
    OAFConformanceClasses.OPEN_API,
]


class ChildApiStatus(BaseModel):
    """Status information for a child API."""

    healthy: bool
    conformance_valid: bool
    has_collection_search: Optional[bool] = None
    has_free_text: Optional[bool] = None


class LifespanStatus(BaseModel):
    """Lifespan status information."""

    status: str


class HealthCheckResponse(BaseModel):
    """Health check response model."""

    status: str
    lifespan: LifespanStatus
    child_apis: Dict[str, ChildApiStatus]


logger = logging.getLogger(__name__)


class CollectionSearchClient(AsyncBaseCoreClient):
    base_conformance_classes: List[str] = attr.ib(
        factory=lambda: BASE_CONFORMANCE_CLASSES
    )

    def _encode_token(self, state: Dict) -> str:
        """Encode pagination state into a token."""
        json_str = json.dumps(state, separators=(",", ":"))
        return base64.urlsafe_b64encode(json_str.encode()).decode()

    def _decode_token(self, token: str) -> Dict:
        """Decode token back into pagination state."""
        json_str = base64.urlsafe_b64decode(token.encode()).decode()
        return json.loads(json_str)

    def _build_search_params(
        self,
        bbox: Optional[BBox],
        datetime: Optional[str],
        limit: Optional[int],
        fields: Optional[List[str]],
        sortby: Optional[str],
        filter_expr: Optional[str],
        filter_lang: Optional[str],
        q: Optional[List[str]],
    ) -> Dict[str, Any]:
        """Build search parameters dictionary."""
        _bbox = ",".join(str(coord) for coord in bbox) if bbox else None

        return {
            key: value
            for key, value in {
                "bbox": _bbox,
                "datetime": datetime,
                "limit": limit,
                "fields": fields,
                "sortby": sortby,
                "filter_expr": filter_expr,
                "filter_lang": filter_lang,
                "q": q,
            }.items()
            if value is not None
        }

    def _get_search_state(
        self, token: Optional[str], apis: List[str], param_str: str
    ) -> Dict[str, Any]:
        """Get or create search state based on token."""
        if token:
            search_state = self._decode_token(token)
            logger.info("Continuing collection search with token pagination")
        else:
            search_state = {
                "current": {api: f"{api}/collections?{param_str}" for api in apis},
                "is_first_page": True,
            }
            logger.info(f"Starting new collection search across {len(apis)} APIs")

        return search_state

    def _build_pagination_links(
        self, request: Request, search_state: Dict[str, Any], new_state: Dict[str, Any]
    ) -> List[Dict[str, str]]:
        """Build pagination links for the response."""
        links = [
            {
                "rel": "self",
                "href": str(request.url),
            }
        ]

        if not search_state.get("is_first_page", False) and new_state["previous"]:
            prev_state = {
                "current": new_state["previous"],
                "is_first_page": False,
            }
            prev_token = self._encode_token(prev_state)
            links.append(
                {
                    "rel": "previous",
                    "href": f"{request.base_url}collections?token={prev_token}",
                }
            )

        if new_state["next"]:
            next_state = {
                "current": new_state["next"],
                "is_first_page": False,
            }
            next_token = self._encode_token(next_state)
            links.append(
                {
                    "rel": "next",
                    "href": f"{request.base_url}collections?token={next_token}",
                }
            )

        return links

    async def all_collections(
        self,
        request: Request,
        apis: Optional[List[str]] = None,
        token: Optional[str] = None,
        bbox: Optional[BBox] = None,
        datetime: Optional[str] = None,
        limit: Optional[int] = None,
        fields: Optional[List[str]] = None,
        sortby: Optional[str] = None,
        filter_expr: Optional[str] = None,
        filter_lang: Optional[str] = None,
        q: Optional[List[str]] = None,
        **kwargs,
    ) -> Collections:
        if not apis:
            apis = request.app.state.settings.child_api_urls
            if not apis:
                raise ValueError("no apis specified!")

        params = self._build_search_params(
            bbox, datetime, limit, fields, sortby, filter_expr, filter_lang, q
        )
        param_str = unquote(urlencode(params, True))
        search_state = self._get_search_state(token, apis, param_str)

        collections = []
        canonical_links = []

        new_state: Dict[str, Any] = {
            "current": {},
            "previous": {},
            "next": {},
            "is_first_page": False,
        }

        async def fetch_api_data(
            client, api: str, url: str
        ) -> Tuple[str, Dict[str, Any]]:
            """Fetch data from a single API endpoint."""
            api_request = await client.get(url)
            json_response = api_request.json()
            return api, json_response

        async with AsyncClient() as client:
            current_urls = search_state.get("current", search_state.get("next", {}))

            for api, url in current_urls.items():
                logger.info(f"Making request to {api}: {url}")

            tasks = [
                fetch_api_data(client, api, url) for api, url in current_urls.items()
            ]

            api_responses = await asyncio.gather(*tasks)

            for api, json_response in api_responses:
                url = current_urls[api]
                collections_count = len(json_response["collections"])
                logger.info(f"Received {collections_count} collections from {api}")

                canonical_links.append({"rel": "canonical", "href": url})
                collections.extend(json_response["collections"])

                next_link = next(
                    filter(lambda x: x["rel"] == "next", json_response["links"]),
                    None,
                )
                prev_link = next(
                    filter(lambda x: x["rel"] == "previous", json_response["links"]),
                    None,
                )

                new_state["current"][api] = url

                if next_link:
                    new_state["next"][api] = next_link["href"]

                if prev_link:
                    new_state["previous"][api] = prev_link["href"]

            logger.info(
                "Collection search completed. "
                f"Total collections returned: {len(collections)}"
            )

        links = self._build_pagination_links(request, search_state, new_state)
        links.extend(canonical_links)

        return Collections(
            collections=collections,
            links=links,
            numberReturned=len(collections),
        )

    async def landing_page(self, **kwargs) -> LandingPage:
        """Landing page.

        Modified version of the default with the STAC search links removed

        Called with `GET /`.

        Returns:
            API landing page, serving as an entry point to the API.
        """
        request: Request = kwargs["request"]
        base_url = get_base_url(request)

        landing_page = self._landing_page(
            base_url=base_url,
            conformance_classes=self.conformance_classes(),
            extension_schemas=[],
        )

        # Add Queryables link
        if self.extension_is_enabled("FilterExtension") or self.extension_is_enabled(
            "SearchFilterExtension"
        ):
            landing_page["links"].append(
                {
                    "rel": Relations.queryables.value,
                    "type": MimeTypes.jsonschema.value,
                    "title": "Queryables available for this Catalog",
                    "href": urljoin(base_url, "queryables"),
                    "method": "GET",
                }
            )

        # Add Aggregation links
        if self.extension_is_enabled("AggregationExtension"):
            landing_page["links"].extend(
                [
                    {
                        "rel": "aggregate",
                        "type": "application/json",
                        "title": "Aggregate",
                        "href": urljoin(base_url, "aggregate"),
                    },
                    {
                        "rel": "aggregations",
                        "type": "application/json",
                        "title": "Aggregations",
                        "href": urljoin(base_url, "aggregations"),
                    },
                ]
            )

        # Add OpenAPI URL
        landing_page["links"].append(
            {
                "rel": Relations.service_desc.value,
                "type": MimeTypes.openapi.value,
                "title": "OpenAPI service description",
                "href": str(request.url_for("openapi")),
            }
        )

        # Add human readable service-doc
        landing_page["links"].append(
            {
                "rel": Relations.service_doc.value,
                "type": MimeTypes.html.value,
                "title": "OpenAPI service documentation",
                "href": str(request.url_for("swagger_ui_html")),
            }
        )

        # SCRUB ITEM SEARCH links
        # TODO: open issue in stac-fastapi to only add these if the conformance classes
        # are there?
        landing_page["links"] = list(
            filter(
                lambda link: not link["title"].startswith("STAC search"),
                landing_page["links"],
            )
        )

        return LandingPage(**landing_page)

    async def post_search(self, *args, **kwargs) -> ItemCollection:
        raise NotImplementedError

    async def get_search(
        self,
        *args,
        **kwargs,
    ) -> ItemCollection:
        raise NotImplementedError

    async def get_item(self, *args, **kwargs) -> Item:
        raise NotImplementedError

    async def get_collection(self, *args, **kwargs) -> Collection:
        raise NotImplementedError

    async def item_collection(
        self,
        *args,
        **kwargs,
    ) -> ItemCollection:
        raise NotImplementedError


async def health_check(
    request: Request,
    apis: Annotated[
        Optional[List[str]],
        Query(description="List of STAC APIs to check health status for"),
    ] = None,
) -> HealthCheckResponse:
    """PgSTAC HealthCheck."""
    if not apis:
        apis = request.app.state.settings.child_api_urls
        if not apis:
            raise ValueError("no apis specified!")

    child_apis: Dict[str, ChildApiStatus] = {}
    semaphore = asyncio.Semaphore(10)

    async def check_api_health(client, api: str) -> Tuple[str, ChildApiStatus]:
        async with semaphore:
            try:
                api_response = await client.get(api)
                if api_response.status_code != 200:
                    return api, ChildApiStatus(healthy=False, conformance_valid=False)

                landing_page = api_response.json()
                conforms_to = landing_page.get("conformsTo", [])

                has_collection_search = any(
                    cls.endswith("collection-search") for cls in conforms_to
                )
                has_free_text = any(
                    cls.endswith("collection-search#free-text") for cls in conforms_to
                )

                conformance_valid = has_collection_search and has_free_text

                result = ChildApiStatus(
                    healthy=True,
                    conformance_valid=conformance_valid,
                    has_collection_search=has_collection_search,
                    has_free_text=has_free_text,
                )

                return api, result

            except Exception:
                return api, ChildApiStatus(healthy=False, conformance_valid=False)

    async with AsyncClient() as client:
        tasks = [check_api_health(client, api) for api in apis]
        results = await asyncio.gather(*tasks)

        for api, result in results:
            child_apis[api] = result

    return HealthCheckResponse(
        status="UP", lifespan=LifespanStatus(status="UP"), child_apis=child_apis
    )
