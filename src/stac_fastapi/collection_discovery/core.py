import base64
import json
from typing import Any, Dict, List, Optional, Union
from urllib.parse import unquote, urlencode

import attr
from fastapi import Request
from fastapi.responses import JSONResponse
from httpx import AsyncClient
from stac_pydantic.shared import BBox

from stac_fastapi.types.conformance import OAFConformanceClasses, STACConformanceClasses
from stac_fastapi.types.core import AsyncBaseCoreClient
from stac_fastapi.types.stac import Collection, Collections, Item, ItemCollection

BASE_CONFORMANCE_CLASSES = [
    STACConformanceClasses.CORE,
    STACConformanceClasses.COLLECTIONS,
    OAFConformanceClasses.CORE,
    OAFConformanceClasses.OPEN_API,
]


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

    async def all_collections(
        self,
        request: Request,
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
        params = {
            key: value
            for key, value in {
                "bbox": bbox,
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
        collections = []
        links = [
            {
                "rel": "self",
                "href": str(request.url),
            }
        ]
        param_str = unquote(urlencode(params, True))

        if token:
            search_state = self._decode_token(token)
        else:
            search_state = {
                "current": {
                    api: f"{api}/collections?{param_str}"
                    for api in request.app.state.settings.child_api_urls
                },
                "is_first_page": True,
            }

        new_state: Dict[str, Any] = {
            "current": {},
            "previous": {},
            "next": {},
            "is_first_page": False,
        }

        async with AsyncClient() as client:
            current_urls = search_state.get("current", search_state.get("next", {}))

            for api, url in current_urls.items():
                # provide link to actual API search
                links.append({"rel": "canonical", "href": url})

                api_request = await client.get(url)
                json_response = api_request.json()
                collections.extend(json_response["collections"])

                next_link = next(
                    filter(lambda x: x["rel"] == "next", json_response["links"]),
                    None,
                )
                prev_link = next(
                    filter(lambda x: x["rel"] == "prev", json_response["links"]),
                    None,
                )

                new_state["current"][api] = url

                if next_link:
                    new_state["next"][api] = next_link["href"]

                if prev_link:
                    new_state["previous"][api] = prev_link["href"]

        if not search_state.get("is_first_page", False) and new_state["previous"]:
            prev_state = {
                "current": new_state["previous"],
                "is_first_page": False,
            }
            prev_token = self._encode_token(prev_state)
            links.append(
                {
                    "rel": "prev",
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

        return Collections(
            collections=collections,
            links=links,
            numberReturned=len(collections),
        )

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


async def health_check(request: Request) -> Union[Dict, JSONResponse]:
    """PgSTAC HealthCheck."""
    resp: Dict[str, Any] = {
        "status": "UP",
        "lifespan": {
            "status": "UP",
        },
        "child_apis": {},
    }

    async with AsyncClient() as client:
        for api in request.app.state.settings.child_api_urls:
            api_response = await client.get(api)
            resp["child_apis"][api] = api_response.status_code == 200

    return resp
