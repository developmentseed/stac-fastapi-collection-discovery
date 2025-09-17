from unittest.mock import Mock

import pytest
from brotli_asgi import BrotliMiddleware
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware import Middleware

from stac_fastapi.api.middleware import CORSMiddleware, ProxyHeaderMiddleware
from stac_fastapi.collection_discovery.app import (
    BASE_CONFORMANCE_CLASSES,
    StacCollectionSearchApi,
    collections_get_request_model,
    cs_extensions,
    health_check,
)
from stac_fastapi.collection_discovery.core import CollectionSearchClient
from stac_fastapi.collection_discovery.settings import Settings

print(collections_get_request_model)


@pytest.fixture
def test_app():
    """Create a test app instance with mock settings."""

    test_settings = Settings(
        upstream_api_urls="https://api1.example.com,https://api2.example.com"
    )

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
        client=CollectionSearchClient(base_conformance_classes=BASE_CONFORMANCE_CLASSES),
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
