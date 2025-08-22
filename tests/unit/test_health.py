import pytest
import respx
from httpx import Response

from stac_fastapi.collection_discovery.core import health_check


class TestHealthCheck:
    """Test cases for health check functionality."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_health_check_all_apis_healthy(self, mock_request):
        """Test health check when all APIs are healthy."""
        respx.get("https://api1.example.com").mock(
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
        respx.get("https://api2.example.com").mock(
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

        result = await health_check(mock_request)

        assert result.status == "UP"
        assert result.lifespan.status == "UP"

        api1_result = result.child_apis["https://api1.example.com"]
        assert api1_result.healthy is True
        assert api1_result.conformance_valid is True
        assert api1_result.has_collection_search is True
        assert api1_result.has_free_text is True

        api2_result = result.child_apis["https://api2.example.com"]
        assert api2_result.healthy is True
        assert api2_result.conformance_valid is True
        assert api2_result.has_collection_search is True
        assert api2_result.has_free_text is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_health_check_some_apis_unhealthy(self, mock_request):
        """Test health check when some APIs are unhealthy."""
        respx.get("https://api1.example.com").mock(
            return_value=Response(500, json={"error": "Server error"})
        )
        respx.get("https://api2.example.com").mock(
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

        result = await health_check(mock_request)

        assert result.status == "UP"
        assert result.lifespan.status == "UP"

        api1_result = result.child_apis["https://api1.example.com"]
        assert api1_result.healthy is False
        assert api1_result.conformance_valid is False

        api2_result = result.child_apis["https://api2.example.com"]
        assert api2_result.healthy is True
        assert api2_result.conformance_valid is True
        assert api2_result.has_collection_search is True
        assert api2_result.has_free_text is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_health_check_all_apis_unhealthy(self, mock_request):
        """Test health check when all APIs are unhealthy."""
        respx.get("https://api1.example.com").mock(
            return_value=Response(500, json={"error": "Server error"})
        )
        respx.get("https://api2.example.com").mock(
            return_value=Response(404, json={"error": "Not found"})
        )

        result = await health_check(mock_request)

        assert result.status == "UP"
        assert result.lifespan.status == "UP"

        api1_result = result.child_apis["https://api1.example.com"]
        assert api1_result.healthy is False
        assert api1_result.conformance_valid is False

        api2_result = result.child_apis["https://api2.example.com"]
        assert api2_result.healthy is False
        assert api2_result.conformance_valid is False

    @pytest.mark.asyncio
    @respx.mock
    async def test_health_check_partial_conformance(self, mock_request):
        """Test health check when APIs have partial conformance."""
        respx.get("https://api1.example.com").mock(
            return_value=Response(
                200,
                json={
                    "conformsTo": [
                        "https://api.stacspec.org/v1.0.0/collection-search"
                        # Missing free-text conformance
                    ]
                },
            )
        )
        respx.get("https://api2.example.com").mock(
            return_value=Response(
                200,
                json={
                    "conformsTo": [
                        "https://api.stacspec.org/v1.0.0/collection-search#free-text"
                        # Missing collection-search conformance
                    ]
                },
            )
        )

        result = await health_check(mock_request)

        assert result.status == "UP"
        assert result.lifespan.status == "UP"

        api1_result = result.child_apis["https://api1.example.com"]
        assert api1_result.healthy is True
        assert api1_result.conformance_valid is False  # Missing free-text
        assert api1_result.has_collection_search is True
        assert api1_result.has_free_text is False

        api2_result = result.child_apis["https://api2.example.com"]
        assert api2_result.healthy is True
        assert api2_result.conformance_valid is False  # Missing collection-search
        assert api2_result.has_collection_search is False
        assert api2_result.has_free_text is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_health_check_no_conformance(self, mock_request):
        """Test health check when APIs have no conformance info."""
        respx.get("https://api1.example.com").mock(
            return_value=Response(200, json={})  # No conformsTo field
        )

        result = await health_check(mock_request)

        assert result.status == "UP"
        assert result.lifespan.status == "UP"

        api1_result = result.child_apis["https://api1.example.com"]
        assert api1_result.healthy is True
        assert api1_result.conformance_valid is False
        assert api1_result.has_collection_search is False
        assert api1_result.has_free_text is False
