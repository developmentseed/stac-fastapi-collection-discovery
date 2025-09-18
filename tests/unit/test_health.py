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
        respx.get("https://api1.example.com").mock(return_value=Response(200, json={}))
        respx.get("https://api2.example.com").mock(return_value=Response(200, json={}))

        result = await health_check(mock_request)

        assert result.status == "UP"
        assert result.lifespan.status == "UP"

        api1_result = result.upstream_apis["https://api1.example.com"]
        assert api1_result.healthy is True

        api2_result = result.upstream_apis["https://api2.example.com"]
        assert api2_result.healthy is True

    @pytest.mark.asyncio
    @respx.mock
    async def test_health_check_some_apis_unhealthy(self, mock_request):
        """Test health check when some APIs are unhealthy."""
        respx.get("https://api1.example.com").mock(
            return_value=Response(500, json={"error": "Server error"})
        )
        respx.get("https://api2.example.com").mock(return_value=Response(200, json={}))

        result = await health_check(mock_request)

        assert result.status == "UP"
        assert result.lifespan.status == "UP"

        api1_result = result.upstream_apis["https://api1.example.com"]
        assert api1_result.healthy is False

        api2_result = result.upstream_apis["https://api2.example.com"]
        assert api2_result.healthy is True

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

        api1_result = result.upstream_apis["https://api1.example.com"]
        assert api1_result.healthy is False

        api2_result = result.upstream_apis["https://api2.example.com"]
        assert api2_result.healthy is False
