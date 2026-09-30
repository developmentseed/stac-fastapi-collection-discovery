import json
from unittest.mock import Mock

import pytest
from brotli_asgi import BrotliMiddleware
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware import Middleware

from stac_fastapi.api.middleware import CORSMiddleware, ProxyHeaderMiddleware
from stac_fastapi.collection_discovery.app import (
    COLLECTION_SEARCH_CONFORMANCE_CLASSES,
    StacCollectionSearchApi,
    collections_get_request_model,
    cs_extensions,
    health_check,
)
from stac_fastapi.collection_discovery.core import CollectionSearchClient
from stac_fastapi.collection_discovery.discovery import discovery_conformance_classes
from stac_fastapi.collection_discovery.settings import Settings

print(collections_get_request_model)


def build_test_app(test_settings: Settings):
    api = StacCollectionSearchApi(
        app=FastAPI(
            openapi_url=test_settings.openapi_url,
            docs_url=test_settings.docs_url,
            redoc_url=None,
            root_path=test_settings.root_path,
            title=test_settings.stac_fastapi_title,
            version=test_settings.stac_fastapi_version,
            description=test_settings.stac_fastapi_description,
        ),
        extensions=cs_extensions,
        client=CollectionSearchClient(
            base_conformance_classes=COLLECTION_SEARCH_CONFORMANCE_CLASSES
            + discovery_conformance_classes(test_settings)
        ),
        settings=test_settings,
        collections_get_request_model=collections_get_request_model,
        health_check=health_check,
        middlewares=[
            Middleware(BrotliMiddleware),
            Middleware(ProxyHeaderMiddleware),
            Middleware(
                CORSMiddleware,
                allow_origins=test_settings.cors_origins,
                allow_credentials=True,
                allow_methods=test_settings.cors_methods,
                allow_headers=["*"],
            ),
        ],
    )
    return api.app


UPSTREAMS = "https://api1.example.com,https://api2.example.com"


@pytest.fixture
def test_app():
    """Test app with LLM features off."""
    return build_test_app(Settings(upstream_api_urls=UPSTREAMS))


@pytest.fixture
def llm_test_app():
    """Test app with LLM features on (discovery routes registered)."""
    return build_test_app(
        Settings(upstream_api_urls=UPSTREAMS, llm_provider="openai", llm_api_key="k")
    )


@pytest.fixture
def client(test_app):
    """Test client for FastAPI application."""
    return TestClient(test_app)


@pytest.fixture
def mock_settings():
    """Mock settings with test configuration."""
    return Settings(child_api_urls="https://api1.example.com,https://api2.example.com")


@pytest.fixture
def collection_search_client():
    """CollectionSearchClient instance for testing."""
    return CollectionSearchClient()


@pytest.fixture
def mock_request():
    """Mock FastAPI request object."""
    mock_request = Mock()
    mock_request.url = "http://localhost:8080/collections"
    mock_request.base_url = "http://localhost:8080/"
    mock_request.app.state.settings.upstream_api_urls = [
        "https://api1.example.com",
        "https://api2.example.com",
    ]
    # Mock attributes are truthy; keep LLM features off in unrelated tests
    mock_request.app.state.settings.llm_provider = None
    mock_request.app.state.settings.llm_api_key = None
    return mock_request


@pytest.fixture
def sample_collection():
    """Sample STAC collection for testing."""
    return {
        "type": "Collection",
        "id": "test-collection",
        "title": "Test Collection",
        "description": "A test collection",
        "extent": {
            "spatial": {"bbox": [[-180, -90, 180, 90]]},
            "temporal": {"interval": [["2020-01-01T00:00:00Z", "2021-01-01T00:00:00Z"]]},
        },
        "license": "MIT",
        "links": [],
    }


@pytest.fixture
def sample_collections_response():
    """Sample collections response from a STAC API."""
    return {
        "collections": [
            {
                "type": "Collection",
                "id": "collection-1",
                "title": "Collection 1",
                "description": "First collection",
                "extent": {
                    "spatial": {"bbox": [[-180, -90, 180, 90]]},
                    "temporal": {
                        "interval": [["2020-01-01T00:00:00Z", "2021-01-01T00:00:00Z"]]
                    },
                },
                "license": "MIT",
                "links": [],
            },
            {
                "type": "Collection",
                "id": "collection-2",
                "title": "Collection 2",
                "description": "Second collection",
                "extent": {
                    "spatial": {"bbox": [[-180, -90, 180, 90]]},
                    "temporal": {
                        "interval": [["2020-01-01T00:00:00Z", "2021-01-01T00:00:00Z"]]
                    },
                },
                "license": "MIT",
                "links": [],
            },
        ],
        "links": [
            {"rel": "self", "href": "https://api.example.com/collections"},
            {
                "rel": "next",
                "href": "https://api.example.com/collections?token=next_token",
            },
        ],
    }


class StubLLMResponse:
    def __init__(self, content: str):
        self.content = content

    def parse_json(self):
        try:
            return json.loads(self.content)
        except ValueError:
            return None


class StubLLM:
    """LLMClient stand-in. `routes` maps a substring of the system prompt to
    the content returned (dict/list are JSON-encoded, str is returned as-is)."""

    def __init__(self, routes: dict, error: Exception | None = None):
        self.routes = routes
        self.error = error
        self.calls: list[dict] = []

    async def generate(self, prompt, system=None, **kwargs):
        self.calls.append({"prompt": prompt, "system": system, **kwargs})
        if self.error:
            raise self.error
        for key, content in self.routes.items():
            if key in (system or ""):
                body = content if isinstance(content, str) else json.dumps(content)
                return StubLLMResponse(body)
        raise AssertionError(f"no stub route for system prompt: {(system or '')[:60]!r}")


@pytest.fixture
def make_stub_llm():
    return StubLLM
