import httpx
import pytest
import respx

from stac_fastapi.collection_discovery.llm.location_parser import Geocoder

BASE = "https://geo.example"
CALIFORNIA = [
    {
        "display_name": "California, United States",
        "boundingbox": ["32.5", "42.0", "-124.4", "-114.1"],
        "geojson": {"type": "Polygon", "coordinates": []},
    }
]


@respx.mock
async def test_geocode_returns_west_south_east_north():
    respx.get(f"{BASE}/search").mock(return_value=httpx.Response(200, json=CALIFORNIA))
    result = await Geocoder(BASE).geocode("California")
    assert result is not None
    assert result.bbox == [-124.4, 32.5, -114.1, 42.0]
    assert result.resolved_name == "California, United States"


@respx.mock
async def test_geocode_caches_by_normalized_name():
    route = respx.get(f"{BASE}/search").mock(
        return_value=httpx.Response(200, json=CALIFORNIA)
    )
    geocoder = Geocoder(BASE)
    await geocoder.geocode("California")
    await geocoder.geocode("  california ")
    assert route.call_count == 1


@respx.mock
async def test_geocode_sends_identifying_user_agent():
    route = respx.get(f"{BASE}/search").mock(
        return_value=httpx.Response(200, json=CALIFORNIA)
    )
    await Geocoder(BASE).geocode("California")
    assert "STAC-Collection-Discovery" in route.calls[0].request.headers["user-agent"]


@respx.mock
@pytest.mark.parametrize(
    "payload", [[{"display_name": "X"}], [{"boundingbox": ["a", "b", "c", "d"]}], {}]
)
async def test_geocode_malformed_response_returns_none(payload):
    respx.get(f"{BASE}/search").mock(return_value=httpx.Response(200, json=payload))
    assert await Geocoder(BASE).geocode("Nowhere") is None


@respx.mock
async def test_geocode_http_error_returns_none_and_is_not_cached():
    route = respx.get(f"{BASE}/search").mock(return_value=httpx.Response(500))
    geocoder = Geocoder(BASE)
    assert await geocoder.geocode("California") is None
    assert await geocoder.geocode("California") is None
    assert route.call_count == 2
