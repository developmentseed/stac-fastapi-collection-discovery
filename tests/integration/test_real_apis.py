"""
Integration tests using pytest-recording to test against real STAC APIs.

These tests use pytest-recording to record real API responses and replay them.
To record new cassettes, delete the existing ones and run:
    pytest tests/integration/ --record-mode=once

To run with existing cassettes:
    pytest tests/integration/
"""

from urllib.parse import urlparse

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

TEST_APIS = [
    "https://stac.maap-project.org",
    "https://stac.eoapi.dev",
]


@pytest.fixture
def integration_app():
    """Create an integration test app instance with real API settings."""

    integration_settings = Settings(upstream_api_urls=",".join(TEST_APIS))

    api = StacCollectionSearchApi(
        app=FastAPI(
            openapi_url=integration_settings.openapi_url,
            docs_url=integration_settings.docs_url,
            redoc_url=None,
            root_path=integration_settings.root_path,
            title=integration_settings.stac_fastapi_title,
            version=integration_settings.stac_fastapi_version,
            description=integration_settings.stac_fastapi_description,
        ),
        extensions=cs_extensions,
        client=CollectionSearchClient(base_conformance_classes=BASE_CONFORMANCE_CLASSES),
        settings=integration_settings,
        collections_get_request_model=collections_get_request_model,
        health_check=health_check,
        middlewares=[
            Middleware(BrotliMiddleware),
            Middleware(ProxyHeaderMiddleware),
            Middleware(
                CORSMiddleware,
                allow_origins=integration_settings.cors_origins,
                allow_credentials=True,
                allow_methods=integration_settings.cors_methods,
                allow_headers=["*"],
            ),
        ],
    )

    return api.app


@pytest.fixture
def integration_client(integration_app):
    """Test client configured with real STAC APIs."""
    return TestClient(integration_app)


@pytest.mark.vcr
def test_real_collections_search(integration_client):
    """Test collection search against real STAC APIs."""
    response = integration_client.get("/collections?limit=5")

    assert response.status_code == 200
    data = response.json()

    # Verify response structure
    assert "collections" in data
    assert "links" in data
    assert "numberReturned" in data

    # Should have collections from both APIs
    assert len(data["collections"]) <= 20  # 10 from each API max
    assert data["numberReturned"] == len(data["collections"])

    # Verify each collection has required STAC fields
    for collection in data["collections"]:
        assert "id" in collection
        assert "type" in collection
        assert collection["type"] == "Collection"
        assert "extent" in collection
        assert "license" in collection

    # Check for canonical links to both APIs
    canonical_links = [link for link in data["links"] if link["rel"] == "canonical"]
    assert len(canonical_links) == 2

    # Verify canonical links point to real APIs
    api_hosts = [link["href"] for link in canonical_links]
    for test_api in TEST_APIS:
        parsed = urlparse(test_api)
        assert any(str(parsed.netloc) in host for host in api_hosts)


@pytest.mark.vcr
def test_real_collections_with_bbox(integration_client):
    """Test collection search with bbox parameter against real APIs."""
    # Search over a small area (San Francisco Bay Area)
    response = integration_client.get("/collections?bbox=-122.5,37.7,-122.3,37.8&limit=3")

    assert response.status_code == 200
    data = response.json()

    assert "collections" in data
    assert len(data["collections"]) <= 6  # 3 from each API max


@pytest.mark.vcr
def test_real_collections_with_datetime(integration_client):
    """Test collection search with datetime parameter against real APIs."""
    # Search for collections with data from 2023
    response = integration_client.get(
        "/collections?datetime=2023-01-01T00:00:00Z/2023-12-31T23:59:59Z&limit=3"
    )

    assert response.status_code == 200
    data = response.json()

    assert "collections" in data
    assert len(data["collections"]) <= 6  # 3 from each API max


@pytest.mark.vcr
def test_real_health_check(integration_client):
    """Test health check against real APIs."""
    response = integration_client.get("/_mgmt/health")

    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "UP"
    assert "upstream_apis" in data

    # Both APIs should be healthy
    for test_api in TEST_APIS:
        assert data["upstream_apis"][test_api] is True


@pytest.mark.vcr
def test_real_collections_pagination(integration_client):
    """Test pagination with real APIs."""
    # Get first page with small limit
    response = integration_client.get("/collections?limit=2")

    assert response.status_code == 200
    data = response.json()

    # Should have next link if there are more results
    next_link = next((link for link in data["links"] if link["rel"] == "next"), None)

    if next_link:
        # Follow the next link
        next_response = integration_client.get(next_link["href"])
        assert next_response.status_code == 200

        next_data = next_response.json()
        assert "collections" in next_data

        # Should have different collections than first page
        first_page_ids = {c["id"] for c in data["collections"]}
        second_page_ids = {c["id"] for c in next_data["collections"]}

        # Collections should be different (though there might be some overlap
        # if APIs return results in different orders)
        assert len(first_page_ids.union(second_page_ids)) > len(first_page_ids)


@pytest.mark.vcr
def test_real_landing_page(integration_client):
    """Test landing page structure."""
    response = integration_client.get("/")

    assert response.status_code == 200
    data = response.json()

    assert data["type"] == "Catalog"
    assert "stac_version" in data
    assert "links" in data
    assert "conformsTo" in data

    # Should have collections link
    collections_link = next(
        (link for link in data["links"] if link["rel"] == "data"), None
    )
    assert collections_link is not None

    # Should NOT have search links (this API doesn't support item search)
    search_links = [
        link for link in data["links"] if "search" in link.get("title", "").lower()
    ]
    assert len(search_links) == 0


@pytest.fixture(scope="session")
def vcr_config():
    """Configure pytest-recording (VCR) for integration tests."""
    return {
        "filter_headers": [
            ("authorization", "DUMMY"),
            ("x-api-key", "DUMMY"),
        ],
        "record_mode": "once",
        "cassette_library_dir": "tests/fixtures/cassettes",
        "path_transformer": lambda path: path.replace("tests/integration/", ""),
        "match_on": ["method", "scheme", "host", "port", "path", "query"],
    }
