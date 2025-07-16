import pytest
import respx
from httpx import Response


class TestApp:
    """Test cases for FastAPI application endpoints."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_landing_page(self, client):
        """Test landing page endpoint."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()

        assert data["type"] == "Catalog"
        assert "stac_version" in data
        assert "links" in data
        assert "conformsTo" in data

    @pytest.mark.asyncio
    @respx.mock
    async def test_conformance(self, client):
        """Test conformance endpoint."""
        response = client.get("/conformance")

        assert response.status_code == 200
        data = response.json()

        assert "conformsTo" in data
        assert isinstance(data["conformsTo"], list)
        assert len(data["conformsTo"]) > 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_collections_endpoint(self, client, sample_collections_response):
        """Test collections endpoint."""
        # Mock child API responses
        respx.get("https://api1.example.com/collections").mock(
            return_value=Response(200, json=sample_collections_response)
        )
        respx.get("https://api2.example.com/collections").mock(
            return_value=Response(200, json=sample_collections_response)
        )

        response = client.get("/collections")

        assert response.status_code == 200
        data = response.json()

        assert "collections" in data
        assert "links" in data
        assert "numberReturned" in data
        assert isinstance(data["collections"], list)

    @pytest.mark.asyncio
    @respx.mock
    async def test_collections_with_params(self, client, sample_collections_response):
        """Test collections endpoint with query parameters."""
        respx.get(
            "https://api1.example.com/collections?bbox=-180.0,-90.0,180.0,90.0&limit=5"
        ).mock(return_value=Response(200, json=sample_collections_response))
        respx.get(
            "https://api2.example.com/collections?bbox=-180.0,-90.0,180.0,90.0&limit=5"
        ).mock(return_value=Response(200, json=sample_collections_response))

        response = client.get("/collections?limit=5&bbox=-180,-90,180,90")

        assert response.status_code == 200
        data = response.json()

        assert "collections" in data
        assert isinstance(data["collections"], list)

    @pytest.mark.asyncio
    @respx.mock
    async def test_health_endpoint(self, client):
        """Test health check endpoint."""
        respx.get("https://api1.example.com").mock(
            return_value=Response(200, json={"status": "ok"})
        )
        respx.get("https://api2.example.com").mock(
            return_value=Response(200, json={"status": "ok"})
        )

        response = client.get("/_mgmt/health")

        assert response.status_code == 200
        data = response.json()

        assert data["status"] == "UP"
        assert "child_apis" in data
        assert "lifespan" in data

    def test_openapi_spec(self, client):
        """Test OpenAPI specification endpoint."""
        response = client.get("/api")

        assert response.status_code == 200
        data = response.json()

        assert "openapi" in data
        assert "info" in data
        assert "paths" in data

    def test_docs_endpoint(self, client):
        """Test documentation endpoint."""
        response = client.get("/api.html")

        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    def test_item_endpoints_not_implemented(self, client):
        """Test that item-related endpoints return 404 or appropriate error."""
        # These endpoints should not be available in this API
        response = client.get("/search")
        assert response.status_code == 404

        response = client.post("/search")
        assert response.status_code == 404

        response = client.get("/collections/test-collection")
        assert response.status_code == 404

        response = client.get("/collections/test-collection/items")
        assert response.status_code == 404

        response = client.get("/collections/test-collection/items/test-item")
        assert response.status_code == 404
