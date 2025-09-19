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
        # Mock upstream API conformance endpoints
        respx.get("https://api1.example.com/conformance").mock(
            return_value=Response(
                200,
                json={
                    "conformsTo": [
                        "https://api.stacspec.org/v1.0.0/collection-search",
                        "https://api.stacspec.org/v1.0.0/collection-search#free-text",
                    ]
                },
            )
        )
        respx.get("https://api2.example.com/conformance").mock(
            return_value=Response(
                200,
                json={
                    "conformsTo": [
                        "https://api.stacspec.org/v1.0.0/collection-search",
                        "https://api.stacspec.org/v1.0.0/collection-search#free-text",
                    ]
                },
            )
        )

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
        # Mock upstream API responses
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
            "https://api1.example.com/collections?bbox=-180.0,-90.0,180.0,90.0&limit=5&filter_lang=cql2-text"
        ).mock(return_value=Response(200, json=sample_collections_response))
        respx.get(
            "https://api2.example.com/collections?bbox=-180.0,-90.0,180.0,90.0&limit=5&filter_lang=cql2-text"
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
        assert "upstream_apis" in data
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

    @pytest.mark.asyncio
    @respx.mock
    async def test_landing_page_with_custom_apis(self, client):
        """Test landing page with custom APIs parameter."""
        # Mock upstream API conformance endpoints for custom APIs
        respx.get("https://custom-api1.example.com/conformance").mock(
            return_value=Response(
                200,
                json={
                    "conformsTo": [
                        "https://api.stacspec.org/v1.0.0/collection-search",
                        "https://api.stacspec.org/v1.0.0/collection-search#free-text",
                    ]
                },
            )
        )
        respx.get("https://custom-api2.example.com/conformance").mock(
            return_value=Response(
                200,
                json={
                    "conformsTo": [
                        "https://api.stacspec.org/v1.0.0/collection-search",
                    ]
                },
            )
        )

        response = client.get(
            "/?apis=https://custom-api1.example.com,https://custom-api2.example.com"
        )

        assert response.status_code == 200
        data = response.json()

        assert data["type"] == "Catalog"
        assert "stac_version" in data
        assert "links" in data
        assert "conformsTo" in data

        # Check that custom APIs are mentioned in description
        assert "https://custom-api1.example.com" in data["description"]
        assert "https://custom-api2.example.com" in data["description"]

        # Check that child links point to custom APIs
        child_links = [link for link in data["links"] if link["rel"] == "child"]
        assert len(child_links) == 2

        hrefs = [link["href"] for link in child_links]
        assert "https://custom-api1.example.com" in hrefs
        assert "https://custom-api2.example.com" in hrefs

    @pytest.mark.asyncio
    @respx.mock
    async def test_landing_page_with_single_custom_api(self, client):
        """Test landing page with single custom API parameter."""
        # Mock upstream API conformance endpoint for single custom API
        respx.get("https://single-custom-api.example.com/conformance").mock(
            return_value=Response(
                200,
                json={
                    "conformsTo": [
                        "https://api.stacspec.org/v1.0.0/collection-search",
                    ]
                },
            )
        )

        response = client.get("/?apis=https://single-custom-api.example.com")

        assert response.status_code == 200
        data = response.json()

        # Check that single custom API is mentioned in description
        assert "https://single-custom-api.example.com" in data["description"]

        # Check that only one child link exists
        child_links = [link for link in data["links"] if link["rel"] == "child"]
        assert len(child_links) == 1
        assert child_links[0]["href"] == "https://single-custom-api.example.com"

    @pytest.mark.asyncio
    @respx.mock
    async def test_conformance_with_custom_apis(self, client):
        """Test conformance endpoint with custom APIs parameter."""
        # Mock upstream API conformance endpoints for custom APIs
        respx.get("https://custom-api1.example.com").mock(
            return_value=Response(
                200,
                json={
                    "conformsTo": [
                        "https://api.stacspec.org/v1.0.0/collection-search",
                        "https://api.stacspec.org/v1.0.0/collection-search#free-text",
                    ]
                },
            )
        )
        respx.get("https://custom-api2.example.com").mock(
            return_value=Response(
                200,
                json={
                    "conformsTo": [
                        "https://api.stacspec.org/v1.0.0/collection-search",
                        # Missing free-text conformance
                    ]
                },
            )
        )

        response = client.get(
            "/conformance?apis=https://custom-api1.example.com,https://custom-api2.example.com"
        )

        assert response.status_code == 200
        data = response.json()

        assert "conformsTo" in data
        assert isinstance(data["conformsTo"], list)
        assert len(data["conformsTo"]) > 0

        # Should have intersection of conformance classes
        # Both APIs support collection-search, but only api1 supports free-text
        # So free-text should be excluded from the intersection
        conformance_classes = data["conformsTo"]

        # Check that base conformance classes are present
        assert any("core" in cls for cls in conformance_classes)
        assert any("collections" in cls for cls in conformance_classes)

        # The intersection should only include classes supported by both APIs
        # free-text should NOT be in the result since api2 doesn't support it
        free_text_classes = [cls for cls in conformance_classes if "free-text" in cls]
        assert len(free_text_classes) == 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_conformance_with_single_custom_api(self, client):
        """Test conformance endpoint with single custom API parameter."""
        # Mock upstream API conformance endpoint for single custom API
        respx.get("https://single-custom-api.example.com/conformance").mock(
            return_value=Response(
                200,
                json={
                    "conformsTo": [
                        "https://api.stacspec.org/v1.0.0/collection-search",
                        "https://api.stacspec.org/v1.0.0/collection-search#free-text",
                        "https://api.stacspec.org/v1.0.0/collection-search#sort",
                    ]
                },
            )
        )

        response = client.get("/conformance?apis=https://single-custom-api.example.com")

        assert response.status_code == 200
        data = response.json()

        assert "conformsTo" in data
        assert isinstance(data["conformsTo"], list)
        assert len(data["conformsTo"]) > 0

        # With a single API, all supported conformance classes should be present
        conformance_classes = data["conformsTo"]

        # Should include collection-search extensions supported by the API
        collection_search_classes = [
            cls for cls in conformance_classes if "collection-search" in cls
        ]
        assert len(collection_search_classes) > 0

    @pytest.mark.asyncio
    @respx.mock
    async def test_conformance_with_failing_upstream_api(self, client):
        """Test conformance endpoint when one upstream API fails."""
        # Mock one successful API and one failing API
        respx.get("https://working-api.example.com/conformance").mock(
            return_value=Response(
                200,
                json={
                    "conformsTo": [
                        "https://api.stacspec.org/v1.0.0/collection-search",
                        "https://api.stacspec.org/v1.0.0/collection-search#free-text",
                    ]
                },
            )
        )
        respx.get("https://failing-api.example.com/conformance").mock(
            return_value=Response(500, json={"error": "Internal server error"})
        )

        response = client.get(
            "/conformance?apis=https://working-api.example.com,https://failing-api.example.com"
        )

        assert response.status_code == 200
        data = response.json()

        assert "conformsTo" in data
        assert isinstance(data["conformsTo"], list)
        assert len(data["conformsTo"]) > 0

        # Should still return base conformance classes even if one API fails
        conformance_classes = data["conformsTo"]
        assert any("core" in cls for cls in conformance_classes)
        assert any("collections" in cls for cls in conformance_classes)
