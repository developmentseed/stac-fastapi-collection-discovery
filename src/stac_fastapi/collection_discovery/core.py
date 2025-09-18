import asyncio
import base64
import json
import logging
from typing import Annotated, Any
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

logger = logging.getLogger(__name__)


COLLECTION_SEARCH_CONFORMANCE_CLASSES = [
    STACConformanceClasses.CORE,
    STACConformanceClasses.COLLECTIONS,
    OAFConformanceClasses.CORE,
    OAFConformanceClasses.OPEN_API,
]

HTTPX_TIMEOUT = 15.0


class UpstreamApiStatus(BaseModel):
    """Status information for an upstream API."""

    healthy: bool


class LifespanStatus(BaseModel):
    """Lifespan status information."""

    status: str


class HealthCheckResponse(BaseModel):
    """Health check response model."""

    status: str
    lifespan: LifespanStatus
    upstream_apis: dict[str, UpstreamApiStatus]


class CollectionSearchClient(AsyncBaseCoreClient):
    """AsyncBaseCoreClient modified to return interleaaved collection-search results
    from multiple upstream APIs"""

    base_conformance_classes: list[str] = attr.ib(
        factory=lambda: COLLECTION_SEARCH_CONFORMANCE_CLASSES
    )

    def _encode_token(self, state: dict) -> str:
        """Encode pagination state into a token."""
        json_str = json.dumps(state, separators=(",", ":"))
        return base64.urlsafe_b64encode(json_str.encode()).decode()

    def _decode_token(self, token: str) -> dict:
        """Decode token back into pagination state."""
        json_str = base64.urlsafe_b64decode(token.encode()).decode()
        return json.loads(json_str)

    def _build_search_params(
        self,
        bbox: BBox | None,
        datetime: str | None,
        limit: int | None,
        fields: list[str] | None,
        sortby: str | None,
        filter_expr: str | None,
        filter_lang: str | None,
        q: list[str] | None,
    ) -> dict[str, Any]:
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
        self, token: str | None, apis: list[str], param_str: str
    ) -> dict[str, Any]:
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
        self, request: Request, search_state: dict[str, Any], new_state: dict[str, Any]
    ) -> list[dict[str, str]]:
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

    async def _fetch_api_conformance(
        self, client: AsyncClient, api: str, semaphore: asyncio.Semaphore
    ) -> tuple[str, set]:
        """Fetch conformance classes from a single API."""
        async with semaphore:
            try:
                api_response = await client.get(f"{api}/conformance")
                if api_response.status_code == 200:
                    conformance_data = api_response.json()
                    return api, set(conformance_data.get("conformsTo", []))
                else:
                    logger.warning(
                        f"Failed to fetch conformance from {api}: "
                        f"{api_response.status_code}"
                    )
                    return api, set()
            except Exception as e:
                logger.warning(f"Error fetching conformance from {api}: {e}")
                return api, set()

    async def all_collections(
        self,
        request: Request,
        apis: list[str] | None = None,
        token: str | None = None,
        bbox: BBox | None = None,
        datetime: str | None = None,
        limit: int | None = None,
        fields: list[str] | None = None,
        sortby: str | None = None,
        filter_expr: str | None = None,
        filter_lang: str | None = None,
        q: list[str] | None = None,
        **kwargs,
    ) -> Collections:
        """Collection search for multiple upstream APIs"""
        if not apis:
            apis = request.app.state.settings.upstream_api_urls
            if not apis:
                raise ValueError("no apis specified!")

        params = self._build_search_params(
            bbox, datetime, limit, fields, sortby, filter_expr, filter_lang, q
        )
        param_str = unquote(urlencode(params, True))
        search_state = self._get_search_state(token, apis, param_str)

        collections = []
        canonical_links = []

        new_state: dict[str, Any] = {
            "current": {},
            "previous": {},
            "next": {},
            "is_first_page": False,
        }

        async def fetch_api_data(
            client, api: str, url: str
        ) -> tuple[str, dict[str, Any]]:
            """Fetch data from a single API endpoint."""
            api_request = await client.get(url)
            json_response = api_request.json()
            return api, json_response

        async with AsyncClient(timeout=HTTPX_TIMEOUT) as client:
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

    async def landing_page(
        self, request: Request, apis: list[str] | None = None, **kwargs
    ) -> LandingPage:
        """Landing page.

        Modified version of the default with the STAC item search links removed and
        upstream APIs added as child links.

        Called with `GET /`.

        Returns:
            API landing page, serving as an entry point to the API.
        """
        base_url = get_base_url(request)

        landing_page = self._landing_page(
            base_url=base_url,
            conformance_classes=await self.conformance_classes(
                request=request, apis=apis
            ),
            extension_schemas=[],
        )

        # Add upstream APIs as child links
        if not apis:
            apis = request.app.state.settings.upstream_api_urls
            if not apis:
                raise ValueError("no apis specified!")

        # include the configured APIs in the description
        landing_page["description"] = (
            landing_page["description"] + f"\n\nConfigured APIs:\n{'\n'.join(apis)}"
        )

        landing_page["links"].extend(
            [
                {
                    "rel": Relations.child.value,
                    "type": MimeTypes.json.value,
                    "title": f"Upstream STAC API: {api}",
                    "href": api,
                    "method": "GET",
                }
                for api in apis
            ]
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

    async def conformance_classes(
        self, request: Request, apis: list[str] | None = None
    ) -> list[str]:
        """Generate conformance classes by finding intersection of local and upstream API
        conformance classes."""
        local_conformance_classes = self.base_conformance_classes.copy()

        for extension in self.extensions:
            extension_classes = getattr(extension, "conformance_classes", [])
            local_conformance_classes.extend(extension_classes)

        local_conformance_set = set(local_conformance_classes)

        if not apis:
            apis = request.app.state.settings.upstream_api_urls
            if not apis:
                raise ValueError("no apis specified!")

        semaphore = asyncio.Semaphore(10)

        async with AsyncClient(timeout=HTTPX_TIMEOUT) as client:
            tasks = [self._fetch_api_conformance(client, api, semaphore) for api in apis]
            upstream_conformance_classes = await asyncio.gather(*tasks)

        # Only check intersection for collection-search related conformance classes
        # Keep all other local conformance classes as-is
        collection_search_classes = {
            cls for cls in local_conformance_set if "collection-search" in cls
        }

        # keep list of non-collection-search conformance classes
        other_classes = local_conformance_set - collection_search_classes

        def get_collection_search_suffix(cls: str) -> str:
            if "collection-search" in cls:
                parts = cls.split("collection-search")
                return parts[-1]  # Get the suffix after collection-search
            return ""

        # gather the suffixes of collection-search conformance classes
        # e.g. #filter, #fields
        local_suffixes = {
            get_collection_search_suffix(cls) for cls in collection_search_classes
        }

        # Find the set of suffixes that are present in both the local API and all upstream
        # APIs
        result_suffixes = local_suffixes
        for _, upstream_set in upstream_conformance_classes:
            if upstream_set:
                upstream_suffixes = {
                    get_collection_search_suffix(cls)
                    for cls in upstream_set
                    if "collection-search" in cls
                }
                result_suffixes = result_suffixes.intersection(upstream_suffixes)

        # Convert back to full conformance classes using local URLs
        result_collection_search = {
            cls
            for cls in collection_search_classes
            if get_collection_search_suffix(cls) in result_suffixes
        }

        # Combine filtered collection-search classes with other local classes
        result_set = result_collection_search.union(other_classes)

        return sorted(result_set)

    async def conformance(
        self, request: Request, apis: list[str] | None, **kwargs
    ) -> dict[str, list[str]]:
        """Conformance classes endpoint.

        Override to provide request parameter to conformance_classes method.
        """
        return {"conformsTo": await self.conformance_classes(request=request, apis=apis)}

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
        list[str] | None,
        Query(description="List of STAC APIs to check health status for"),
    ] = None,
) -> HealthCheckResponse:
    """PgSTAC HealthCheck."""
    if not apis:
        apis = request.app.state.settings.upstream_api_urls
        if not apis:
            raise ValueError("no apis specified!")

    upstream_apis: dict[str, UpstreamApiStatus] = {}
    semaphore = asyncio.Semaphore(10)

    async def check_api_health(client, api: str) -> tuple[str, UpstreamApiStatus]:
        async with semaphore:
            try:
                # Check landing page health
                api_response = await client.get(api)
                return api, UpstreamApiStatus(healthy=api_response.status_code == 200)

            except Exception:
                return api, UpstreamApiStatus(healthy=False)

    async with AsyncClient(timeout=HTTPX_TIMEOUT) as client:
        tasks = [check_api_health(client, api) for api in apis]
        results = await asyncio.gather(*tasks)

        for api, result in results:
            upstream_apis[api] = result

    return HealthCheckResponse(
        status="UP", lifespan=LifespanStatus(status="UP"), upstream_apis=upstream_apis
    )
